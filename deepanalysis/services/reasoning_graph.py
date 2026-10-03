"""
Reasoning-graph assembly for the frontend (vis-network).

Two paths:
1. If explicit ReasoningNode/ReasoningEdge rows exist for the incident's
   DeepAnalysisResult, return those.
2. Otherwise fall back to `build_reasoning_graph_from_signals`, which builds a
   uniform graph on the fly from ScreeningSignal / TranscriptFlag /
   FakeScreenshotDetection / IdentityFingerprint.

Stage-2 nodes are ALWAYS present. When Stage 2 did not run (the video stayed
clean at Stage 1), they appear with status "not_applicable" rather than being
omitted, so the frontend always renders a consistent structure.
"""
from deepanalysis.models import ReasoningNode
from screening.models import ScreeningSignal

# Risk threshold separating a "triggered" verdict from a clean one.
RISK_THRESHOLD = 50.0

NodeType = ReasoningNode.NodeType
NodeStatus = ReasoningNode.Status

SYNTHESIS_ID = "synthesis"
VERDICT_ID = "verdict"

# Canonical Stage-2 nodes (always shown, even if Stage 2 didn't run).
STAGE2_NODES = [
    ("s2_transcript", "Анализ транскрипта"),
    ("s2_fake_screenshot", "Детекция поддельных скриншотов"),
    ("s2_identity", "Кросс-платформенная личность"),
]

# Russian labels for the Stage-1 screening modules (fallback to the raw code).
MODULE_LABELS_RU = {
    "metadata": "Метаданные",
    "social_context": "Социальный контекст",
    "quick_audio": "Быстрый аудио-анализ",
    "frame_analysis": "Анализ кадров",
    "adversarial": "Противодействие",
}


def _node(node_id, node_type, label, status, score_contribution, timestamp_sec,
          explanation):
    return {
        "id": node_id,
        "type": node_type,
        "label": label,
        "status": status,
        "score_contribution": float(score_contribution),
        "timestamp_sec": timestamp_sec,
        "explanation": explanation,
    }


def _edge(from_id, to_id, weight=1.0):
    return {"from": from_id, "to": to_id, "weight": float(weight)}


def _verdict_block(risk_score):
    risk_score = float(risk_score)
    return {
        "risk_score": risk_score,
        "label": "триггерный" if risk_score >= RISK_THRESHOLD else "не триггерный",
        "threshold": RISK_THRESHOLD,
    }


def get_reasoning_graph(incident):
    """Return the full graph dict {nodes, edges, verdict} for an incident.

    Prefers an explicit, persisted graph; falls back to building one from the
    available signals.
    """
    dar = getattr(incident, "deep_analysis_result", None)

    if dar is not None and dar.reasoning_nodes.exists():
        nodes = [
            _node(
                n.node_key, n.node_type, n.label, n.status,
                n.score_contribution, n.timestamp_sec, n.explanation,
            )
            for n in dar.reasoning_nodes.all()
        ]
        edges = [
            _edge(e.from_node.node_key, e.to_node.node_key, e.weight)
            for e in dar.reasoning_edges.select_related("from_node", "to_node")
        ]
        risk_score = dar.risk_score
    else:
        graph = build_reasoning_graph_from_signals(incident)
        nodes, edges = graph["nodes"], graph["edges"]
        risk_score = dar.risk_score if dar is not None else incident.risk_score

    return {"nodes": nodes, "edges": edges, "verdict": _verdict_block(risk_score)}


def build_reasoning_graph_from_signals(incident):
    """Build a uniform reasoning graph on the fly from available signals.

    Used when no explicit ReasoningNode/Edge rows exist. Always emits the full
    structure: Stage-1 module nodes, Stage-2 nodes (not_applicable if Stage 2
    didn't run), a synthesis node and a verdict node.
    """
    video = incident.video
    screening = getattr(video, "screening_result", None)
    dar = getattr(incident, "deep_analysis_result", None)

    nodes = []
    edges = []

    # --- Stage 1: one node per screening module -----------------------------
    signals_by_module = {}
    if screening is not None:
        signals_by_module = {s.module: s for s in screening.signals.all()}

    for module_value, module_label in ScreeningSignal.Module.choices:
        node_id = f"s1_{module_value}"
        label_ru = MODULE_LABELS_RU.get(module_value, module_label)
        signal = signals_by_module.get(module_value)
        if signal is None:
            nodes.append(_node(
                node_id, NodeType.STAGE1_SIGNAL, label_ru,
                NodeStatus.NOT_APPLICABLE, 0.0, None,
                "Модуль не дал сигнала.",
            ))
        else:
            triggered = signal.is_triggered
            nodes.append(_node(
                node_id, NodeType.STAGE1_SIGNAL, label_ru,
                NodeStatus.TRIGGERED if triggered else NodeStatus.CLEAN,
                signal.confidence if triggered else 0.0,
                signal.detected_at_timestamp_sec,
                f"{label_ru}: уверенность {signal.confidence:.2f}.",
            ))
        edges.append(_edge(node_id, SYNTHESIS_ID))

    # --- Stage 2: gather artifacts to decide if it ran ----------------------
    transcript_flags = []
    fake_screenshots = []
    identity_link_count = 0
    if dar is not None:
        for transcript in dar.transcripts.all():
            transcript_flags.extend(transcript.flags.all())
        fake_screenshots = list(dar.fake_screenshots.all())
        identity_link_count = video.identity_links.count()

    stage2_ran = bool(transcript_flags or fake_screenshots or identity_link_count)

    if not stage2_ran:
        for node_id, label in STAGE2_NODES:
            nodes.append(_node(
                node_id, NodeType.STAGE2_SIGNAL, label,
                NodeStatus.NOT_APPLICABLE, 0.0, None,
                "Этап 2 не запускался (видео чистое на Этапе 1).",
            ))
            edges.append(_edge(node_id, SYNTHESIS_ID))
    else:
        nodes.append(_stage2_transcript_node(transcript_flags))
        nodes.append(_stage2_fake_screenshot_node(fake_screenshots))
        nodes.append(_stage2_identity_node(identity_link_count))
        for node_id, _ in STAGE2_NODES:
            edges.append(_edge(node_id, SYNTHESIS_ID))

    # --- Synthesis + verdict -----------------------------------------------
    risk_score = float(dar.risk_score if dar is not None else incident.risk_score)
    triggered = risk_score >= RISK_THRESHOLD
    status = NodeStatus.TRIGGERED if triggered else NodeStatus.CLEAN

    nodes.append(_node(
        SYNTHESIS_ID, NodeType.SYNTHESIS, "Синтез", status,
        risk_score, None, "Агрегированный риск по сигналам Этапов 1 и 2.",
    ))
    nodes.append(_node(
        VERDICT_ID, NodeType.VERDICT, "Вердикт", status,
        risk_score, None,
        f"Риск {risk_score:.1f} при пороге {RISK_THRESHOLD:.0f}.",
    ))
    edges.append(_edge(SYNTHESIS_ID, VERDICT_ID))

    return {"nodes": nodes, "edges": edges}


def _stage2_transcript_node(flags):
    if flags:
        severity = max(f.severity for f in flags)
        start = min((f.start_sec for f in flags if f.start_sec is not None),
                    default=None)
        return _node(
            "s2_transcript", NodeType.STAGE2_SIGNAL, "Анализ транскрипта",
            NodeStatus.TRIGGERED, severity, start,
            f"Помечено подозрительных фраз: {len(flags)}.",
        )
    return _node(
        "s2_transcript", NodeType.STAGE2_SIGNAL, "Анализ транскрипта",
        NodeStatus.CLEAN, 0.0, None, "Подозрительных фраз не найдено.",
    )


def _stage2_fake_screenshot_node(detections):
    fakes = [d for d in detections if d.is_fake]
    if fakes:
        confidence = max(d.confidence for d in fakes)
        ts = min((d.frame_timestamp_sec for d in fakes
                  if d.frame_timestamp_sec is not None), default=None)
        return _node(
            "s2_fake_screenshot", NodeType.STAGE2_SIGNAL,
            "Детекция поддельных скриншотов", NodeStatus.TRIGGERED, confidence, ts,
            f"Обнаружено поддельных скриншотов: {len(fakes)}.",
        )
    return _node(
        "s2_fake_screenshot", NodeType.STAGE2_SIGNAL,
        "Детекция поддельных скриншотов", NodeStatus.CLEAN, 0.0, None,
        "Поддельных скриншотов не обнаружено.",
    )


def _stage2_identity_node(link_count):
    if link_count:
        return _node(
            "s2_identity", NodeType.STAGE2_SIGNAL, "Кросс-платформенная личность",
            NodeStatus.TRIGGERED, 0.0, None,
            f"Кросс-платформенных связей личности: {link_count}.",
        )
    return _node(
        "s2_identity", NodeType.STAGE2_SIGNAL, "Кросс-платформенная личность",
        NodeStatus.CLEAN, 0.0, None, "Кросс-платформенных связей не найдено.",
    )
