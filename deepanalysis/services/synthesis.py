import json
import logging
from django.conf import settings
from django.utils import timezone
from deepanalysis.models import DeepAnalysisResult, ReasoningNode, ReasoningEdge
from incidents.models import Incident, PromoCode, TelegramLink
from ingestion.models import Video
import re

logger = logging.getLogger(__name__)

def compute_risk_score(video: Video, deep_analysis_result: DeepAnalysisResult) -> dict:
    """
    Computes the risk score by aggregating all Stage 1 and Stage 2 signals.
    Returns {"score": float, "breakdown": dict}
    """
    score = 0.0
    breakdown = {}
    # Track what fired so we can recognise a *confirmed* illegal-gambling promo
    # (named casino brand / QR + corroboration) and floor its score, instead of
    # letting the additive model dilute a blatant casino down to ~65-70.
    explicit_gambling = False   # named brand / betting QR / ≥3 gambling terms
    triggered_modules = set()
    transcript_strong = False

    # 1. Stage 1 signals. Strong, specific categories weigh more than generic
    # keyword/metadata hits.
    module_weights = {
        "payment": 25,       # a concrete payment identifier is highly actionable
        "brand_link": 22,    # named casino brand / betting link / on-screen QR
        "audio_forensics": 20,  # synthetic voice / high-pressure delivery
        "frame_analysis": 15,
        "quick_audio": 15,
        "metadata": 12,
        "social_context": 15,
    }
    module_labels = {
        "payment": "Этап 1: платёжные реквизиты",
        "brand_link": "Этап 1: бренд казино / ссылка / QR",
        "audio_forensics": "Этап 1: аудио-форензика",
    }
    if hasattr(video, 'screening_result'):
        for sig in video.screening_result.signals.all():
            if sig.is_triggered:
                triggered_modules.add(sig.module)
                if sig.module == "adversarial":
                    bonus = sig.raw_output.get("risk_score_bonus", 0)
                    score += bonus
                    breakdown["Этап 1: противодействие (adversarial)"] = bonus
                elif sig.module == "social_context":
                    # Weight by the manipulation/накрутка index: a section that
                    # is largely astroturfed is a strong fraud indicator, a lone
                    # skeptic comment is weaker.
                    ro = sig.raw_output or {}
                    mi = float(ro.get("manipulation_index", 0) or 0)
                    pts = int(round(10 + 20 * mi))
                    score += pts
                    label = "Этап 1: накрутка комментариев / тональность"
                    breakdown[label] = pts
                elif sig.module == "brand_link":
                    # Named casino brand or several explicit gambling terms is a
                    # near-certain illegal-gambling indicator → strong weight.
                    ro = sig.raw_output or {}
                    strong = bool(ro.get("brands")) or len(ro.get("gambling_terms", [])) >= 3 \
                        or bool(ro.get("qr_codes"))
                    explicit_gambling = explicit_gambling or strong
                    pts = 50 if strong else 22
                    score += pts
                    breakdown["Этап 1: бренд казино / ссылка / QR"] = pts
                else:
                    pts = module_weights.get(sig.module, 15)
                    score += pts
                    label = module_labels.get(
                        sig.module, f"Этап 1: сигнал «{sig.module}»"
                    )
                    breakdown[label] = pts
                    
    # 2. Transcript flags (E1)
    first_transcript = deep_analysis_result.transcripts.first()
    if first_transcript:
        for flag in first_transcript.flags.all():
            if flag.severity >= 3:
                score += 20
                breakdown["Этап 2: транскрипт (важность 3+)"] = 20
                transcript_strong = True
            elif flag.severity == 2:
                score += 10
                breakdown["Этап 2: транскрипт (важность 2)"] = 10
                transcript_strong = True
            else:
                score += 5
                breakdown["Этап 2: транскрипт (важность 1)"] = 5

    # 3. Fake Screenshot (E2)
    fake_screens = deep_analysis_result.fake_screenshots.filter(is_fake=True)
    if fake_screens.exists():
        score += 30
        breakdown["Этап 2: поддельный скриншот"] = 30

    # 4. Identity Link (E3) "Recidivist"
    identity_links = video.identity_links.all()
    if identity_links.exists():
        for id_link in identity_links:
            fp = id_link.identity_fingerprint
            linked_videos = Video.objects.filter(
                identity_links__identity_fingerprint=fp
            ).exclude(id=video.id)
            if linked_videos.exists():
                confirmed_incidents = Incident.objects.filter(
                    video__in=linked_videos,
                    status=Incident.Status.CONFIRMED
                )
                if confirmed_incidents.exists():
                    score += 40
                    breakdown["Этап 2: повторная личность (рецидив)"] = 40
                    break
                
    # 5. Confidence floor for confirmed illegal gambling.
    # A named casino brand / betting QR is a near-certain illegal-gambling
    # indicator. On its own it warrants a high score; corroborated by a second
    # independent signal (payment details, synthetic/high-pressure audio,
    # strong transcript flag, fake payout screenshot, or a recidivist identity)
    # it is effectively confirmed. We raise the score to a floor so a blatant
    # casino lands in the 80-90+ band instead of being diluted by the additive
    # model. The floor never lowers a score; we only add the gap as a bonus.
    if explicit_gambling:
        corroborators = sum([
            "payment" in triggered_modules,
            "audio_forensics" in triggered_modules,
            transcript_strong,
            fake_screens.exists(),
            "Этап 2: повторная личность (рецидив)" in breakdown,
        ])
        floor = 90.0 if corroborators >= 1 else 75.0
        if score < floor:
            bonus = round(floor - score, 1)
            breakdown["Подтверждённый нелегальный гэмблинг (порог уверенности)"] = bonus
            score = floor

    # Normalize
    score = min(score, 100.0)

    return {"score": score, "breakdown": breakdown}

def build_and_save_reasoning_graph(video: Video, deep_analysis_result: DeepAnalysisResult, risk_data: dict) -> tuple[list, list]:
    """
    Materializes the ReasoningNode and ReasoningEdge records in DB.
    """
    nodes = []
    edges = []

    # Idempotent rebuild: drop any nodes/edges from a previous (failed or
    # concurrent) run so the unique (deep_analysis_result, node_key) constraint
    # can't be violated on a re-run.
    deep_analysis_result.reasoning_edges.all().delete()
    deep_analysis_result.reasoning_nodes.all().delete()

    synthesis_node = ReasoningNode.objects.create(
        deep_analysis_result=deep_analysis_result,
        node_key="synthesis",
        node_type=ReasoningNode.NodeType.SYNTHESIS,
        status=ReasoningNode.Status.TRIGGERED,
        label="Мультимодальный синтез",
        explanation="Агрегированы все мультимодальные сигналы.",
        score_contribution=risk_data["score"],
    )
    nodes.append(synthesis_node)

    threshold = getattr(settings, "RISK_SCORE_VERDICT_THRESHOLD", 60.0)
    verdict_label = "триггерный контент" if risk_data["score"] >= threshold else "не триггерный контент"

    verdict_node = ReasoningNode.objects.create(
        deep_analysis_result=deep_analysis_result,
        node_key="verdict",
        node_type=ReasoningNode.NodeType.VERDICT,
        status=ReasoningNode.Status.TRIGGERED if risk_data["score"] >= threshold else ReasoningNode.Status.CLEAN,
        label="Итоговый вердикт",
        explanation=f"Риск-скор: {risk_data['score']}. Вывод: {verdict_label}.",
        score_contribution=risk_data["score"],
    )
    nodes.append(verdict_node)

    ReasoningEdge.objects.create(
        deep_analysis_result=deep_analysis_result,
        from_node=synthesis_node,
        to_node=verdict_node,
        weight=1.0,
    )

    for idx, (source_desc, contribution) in enumerate(risk_data["breakdown"].items()):
        node = ReasoningNode.objects.create(
            deep_analysis_result=deep_analysis_result,
            node_key=f"signal_{idx}",
            node_type=ReasoningNode.NodeType.STAGE2_SIGNAL,
            status=ReasoningNode.Status.TRIGGERED,
            label=source_desc,
            explanation=f"Сработал. Вклад: +{contribution}.",
            score_contribution=float(contribution),
        )
        nodes.append(node)

        edge = ReasoningEdge.objects.create(
            deep_analysis_result=deep_analysis_result,
            from_node=node,
            to_node=synthesis_node,
            weight=contribution / max(1.0, risk_data["score"]),
        )
        edges.append(edge)
        
    return nodes, edges

def generate_incident_summary(transcript_text: str, risk_data: dict) -> str:
    """
    Generate a 2-3 sentence Russian incident summary via the configured LLM.

    Uses the unified LLM client (core.llm). Fail-loud: raises
    ModuleDependencyError if no backend is configured, so the caller records a
    step error and leaves the summary blank instead of persisting a fabricated
    placeholder.
    """
    from core.llm import call_llm

    prompt = (
        f"Создай краткое резюме из 2-3 предложений на русском языке для инцидента "
        f"с риском {risk_data['score']}/100. "
        f"Найденные триггеры: {list(risk_data['breakdown'].keys())}. "
        f"Часть транскрипта: {transcript_text[:1000]}"
    )
    return call_llm(
        prompt,
        system=(
            "Ты аналитик финансового регулятора Казахстана. Пиши кратко, по-русски, "
            "по делу, без воды."
        ),
        max_tokens=200,
        module="summary",
    )

def extract_promos_and_links(incident: Incident, text: str, source: str):
    """
    Extracts promo codes and telegram links from text via regex.
    """
    tg_pattern = r"(https?://t\.me/[a-zA-Z0-9_]+|@([a-zA-Z0-9_]{5,}))"
    tg_matches = set(re.findall(tg_pattern, text))
    for match in tg_matches:
        url = match[0] if match[0].startswith("http") else f"https://t.me/{match[0][1:]}"
        TelegramLink.objects.get_or_create(
            incident=incident,
            url=url,
            defaults={"extracted_from": source}
        )
        
    promo_pattern = r"(?i)(промокод|код|promo)[:\s]*([A-Z0-9]{4,15})"
    promo_matches = set(re.findall(promo_pattern, text))
    for _, code in promo_matches:
        PromoCode.objects.get_or_create(
            incident=incident,
            code=code.upper(),
            defaults={"extracted_from": source}
        )
