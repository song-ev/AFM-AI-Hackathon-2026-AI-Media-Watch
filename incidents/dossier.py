"""
"Собрать досье" — generate a court/operations-ready PDF dossier for an incident.

A single self-contained ReportLab document gathering everything the analyst and
the recipient (law enforcement / platform trust-&-safety) need: the verdict and
risk score, a contribution chart, the account & video metadata, geolocation,
the new analysis categories (payment identifiers, casino brands/links, decoded
QR codes, audio forensics, comment-section накрутка), suspicious transcript
phrases, extracted screenshots, promo codes / Telegram links and the SHA-256
chain of custody.

Cyrillic-safe: registers DejaVuSans (shipped with matplotlib) so Russian text
renders. Charts are drawn with matplotlib (Agg) and embedded as PNG. Frame
screenshots are embedded only when the file exists locally (the media store is
shared and may be absent on a given host) — otherwise a note is shown.
"""
from __future__ import annotations

import io
import logging
import os

from django.utils import timezone

logger = logging.getLogger(__name__)

_FONT_REGISTERED = False
_FONT_NAME = "DejaVuSans"
_FONT_BOLD = "DejaVuSans-Bold"

# Brand palette.
_NAVY = "#0f172a"
_RED = "#dc2626"
_AMBER = "#f59e0b"
_GREEN = "#16a34a"
_SLATE = "#475569"


def _ensure_font():
    """Register a Unicode TTF with ReportLab (idempotent)."""
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    import matplotlib

    ttf_dir = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")
    regular = os.path.join(ttf_dir, "DejaVuSans.ttf")
    bold = os.path.join(ttf_dir, "DejaVuSans-Bold.ttf")
    pdfmetrics.registerFont(TTFont(_FONT_NAME, regular))
    if os.path.exists(bold):
        pdfmetrics.registerFont(TTFont(_FONT_BOLD, bold))
    else:  # fall back to regular as "bold"
        pdfmetrics.registerFont(TTFont(_FONT_BOLD, regular))
    _FONT_REGISTERED = True


def _risk_color(score: float) -> str:
    if score >= 60:
        return _RED
    if score >= 35:
        return _AMBER
    return _GREEN


# ---------------------------------------------------------------------------
# Charts (matplotlib -> PNG bytes)
# ---------------------------------------------------------------------------
def _risk_gauge_png(score: float) -> io.BytesIO:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(3.2, 1.9), subplot_kw={"aspect": "equal"})
    color = _risk_color(score)
    frac = max(0.0, min(1.0, score / 100.0))
    ax.pie(
        [frac, 1 - frac], colors=[color, "#e2e8f0"], startangle=90,
        counterclock=False, wedgeprops={"width": 0.32},
    )
    ax.text(0, 0, f"{score:.0f}", ha="center", va="center",
            fontsize=26, fontweight="bold", color=color)
    ax.text(0, -0.38, "из 100", ha="center", va="center", fontsize=9, color=_SLATE)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight", transparent=True)
    plt.close(fig)
    buf.seek(0)
    return buf


def _breakdown_png(items: list[tuple[str, float]]) -> io.BytesIO | None:
    if not items:
        return None
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    items = sorted(items, key=lambda kv: kv[1])[-10:]
    labels = [k if len(k) <= 42 else k[:41] + "…" for k, _ in items]
    values = [v for _, v in items]
    fig, ax = plt.subplots(figsize=(6.6, max(1.6, 0.45 * len(items))))
    ax.barh(range(len(items)), values, color=_NAVY)
    ax.set_yticks(range(len(items)))
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel("Вклад в риск-скор", fontsize=8)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Document builder
# ---------------------------------------------------------------------------
def build_incident_dossier(incident) -> bytes:
    """Render the incident dossier and return PDF bytes."""
    _ensure_font()
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        HRFlowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    video = incident.video
    account = video.social_account
    dar = getattr(incident, "deep_analysis_result", None)

    styles = getSampleStyleSheet()
    for s in styles.byName.values():
        s.fontName = _FONT_NAME
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontName=_FONT_BOLD,
                        fontSize=20, textColor=colors.HexColor(_NAVY), spaceAfter=4)
    sub = ParagraphStyle("sub", parent=styles["Normal"], fontSize=9,
                         textColor=colors.HexColor(_SLATE), alignment=TA_CENTER)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName=_FONT_BOLD,
                        fontSize=13, textColor=colors.HexColor(_NAVY),
                        spaceBefore=14, spaceAfter=6)
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=9.5, leading=13)
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8,
                           textColor=colors.HexColor(_SLATE))

    story: list = []

    def section(title: str):
        story.append(Paragraph(title, h2))
        story.append(HRFlowable(width="100%", thickness=0.6,
                                color=colors.HexColor("#cbd5e1"), spaceAfter=6))

    def kv_table(rows: list[tuple[str, str]], col0=4.2 * cm):
        data = [[Paragraph(f"<b>{k}</b>", small), Paragraph(v or "—", body)] for k, v in rows]
        t = Table(data, colWidths=[col0, None])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#e2e8f0")),
        ]))
        return t

    # ---- Header -----------------------------------------------------------
    story.append(Paragraph("ДОСЬЕ ПО ИНЦИДЕНТУ", h1))
    story.append(Paragraph(
        f"AI Media Watch · Агентство по финансовому мониторингу РК · "
        f"инцидент #{incident.id} · сформировано "
        f"{timezone.localtime(timezone.now()):%Y-%m-%d %H:%M}", sub))
    story.append(Spacer(1, 0.4 * cm))

    # ---- Verdict + gauge --------------------------------------------------
    risk = float(incident.risk_score or 0.0)
    status_label = {
        "pending_review": "На рассмотрении", "confirmed": "Подтверждён",
        "false_positive": "Ложное срабатывание", "borderline": "Пограничный",
    }.get(incident.status, incident.status)
    verdict = "ТРИГГЕРНЫЙ КОНТЕНТ" if risk >= 60 else (
        "ТРЕБУЕТ ПРОВЕРКИ" if risk >= 35 else "НИЗКИЙ РИСК")
    gauge = Image(_risk_gauge_png(risk), width=3.6 * cm, height=2.1 * cm)
    verdict_cell = [
        Paragraph(f"<b>Вывод системы:</b> {verdict}", body),
        Paragraph(f"<b>Статус аналитика:</b> {status_label}", body),
        Paragraph(f"<b>Приоритет:</b> {incident.priority_score:.1f}", body),
    ]
    vt = Table([[gauge, verdict_cell]], colWidths=[4.2 * cm, None])
    vt.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story.append(vt)

    if incident.summary_text:
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph(f"<b>Резюме.</b> {incident.summary_text}", body))

    # ---- Account & video --------------------------------------------------
    section("Объект мониторинга")
    posted = video.posted_at.strftime("%Y-%m-%d %H:%M") if video.posted_at else "—"
    story.append(kv_table([
        ("Платформа", video.platform.name if video.platform_id else "—"),
        ("Аккаунт", f"@{account.username} ({account.display_name})".strip()),
        ("Подписчиков", f"{account.followers_count:,}".replace(",", " ")),
        ("Ссылка на видео", video.url),
        ("Опубликовано", posted),
        ("В розыске (watchlist)",
         "да — " + (account.watchlist_reason or "") if account.is_watchlisted else "нет"),
        ("Описание", (video.caption or "")[:600]),
    ]))

    # ---- Geo --------------------------------------------------------------
    if video.geo_source and video.geo_source != "none":
        section("Геолокация")
        story.append(kv_table([
            ("Место", video.geo_label or "—"),
            ("Регион", video.geo_region or "—"),
            ("Страна", video.geo_country or "—"),
            ("Источник", video.get_geo_source_display()),
            ("Достоверность", f"{video.geo_confidence:.0%}"),
        ]))

    # ---- Risk breakdown chart --------------------------------------------
    breakdown_items: list[tuple[str, float]] = []
    if dar is not None:
        for node in dar.reasoning_nodes.all():
            if node.node_type in ("stage1_signal", "stage2_signal") and (
                node.score_contribution or 0
            ) > 0:
                breakdown_items.append((node.label, float(node.score_contribution)))
    chart = _breakdown_png(breakdown_items)
    if chart is not None:
        section("Факторы риска")
        story.append(Image(chart, width=15.5 * cm,
                           height=15.5 * cm * (max(1.6, 0.45 * min(10, len(breakdown_items))) / 6.6)))

    # ---- Categories -------------------------------------------------------
    cats = _collect_categories(video)
    if cats:
        section("Результаты анализа по категориям")
        for block in cats:
            story.append(Paragraph(f"<b>{block['title']}</b>", body))
            for line in block["lines"]:
                story.append(Paragraph(f"• {line}", small))
            story.append(Spacer(1, 0.15 * cm))

    # ---- Transcript flags -------------------------------------------------
    flags = []
    if dar is not None:
        for tr in dar.transcripts.all():
            flags.extend(tr.flags.all())
    if flags:
        section("Подозрительные фразы (транскрипт)")
        data = [[Paragraph("<b>Время</b>", small), Paragraph("<b>Фраза</b>", small),
                 Paragraph("<b>Категория</b>", small)]]
        for f in flags[:25]:
            ts = f"{f.start_sec:.0f}с" if getattr(f, "start_sec", None) is not None else "—"
            data.append([Paragraph(ts, small), Paragraph(f.phrase, small),
                         Paragraph(f.category, small)])
        t = Table(data, colWidths=[2 * cm, None, 3.5 * cm])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ]))
        story.append(t)

    # ---- Screenshots ------------------------------------------------------
    _append_screenshots(story, video, section, Image, Paragraph, Table,
                        TableStyle, Spacer, small, cm, colors)

    # ---- Promo / Telegram -------------------------------------------------
    promos = list(incident.promo_codes.all())
    tg = list(incident.telegram_links.all())
    if promos or tg:
        section("Извлечённые артефакты")
        if promos:
            story.append(Paragraph(
                "<b>Промокоды:</b> " + ", ".join(p.code for p in promos), body))
        if tg:
            story.append(Paragraph(
                "<b>Telegram:</b> " + ", ".join(l.url for l in tg), small))

    # ---- Evidence chain ---------------------------------------------------
    evidence = list(incident.evidence_entries.all())
    section("Цепочка доказательств (chain of custody)")
    if not evidence:
        story.append(Paragraph("Записи цепочки доказательств отсутствуют.", small))
    else:
        data = [[Paragraph("<b>Тип</b>", small), Paragraph("<b>SHA-256</b>", small),
                 Paragraph("<b>Собрано</b>", small)]]
        for e in evidence:
            data.append([Paragraph(e.file_type, small),
                         Paragraph(e.sha256_hash, small),
                         Paragraph(e.collected_at.strftime("%Y-%m-%d %H:%M"), small)])
        t = Table(data, colWidths=[2.4 * cm, None, 3.2 * cm])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ]))
        story.append(t)

    story.append(Spacer(1, 0.5 * cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cbd5e1")))
    story.append(Paragraph(
        "Документ сформирован автоматически системой AI Media Watch. Содержит "
        "результаты алгоритмического анализа и не является окончательным "
        "юридическим заключением. Для процессуальных действий требуется "
        "верификация аналитиком АФМ.", small))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, title=f"Досье инцидента #{incident.id}",
        leftMargin=1.6 * cm, rightMargin=1.6 * cm,
        topMargin=1.4 * cm, bottomMargin=1.4 * cm,
    )
    doc.build(story)
    buf.seek(0)
    return buf.getvalue()


def _collect_categories(video) -> list[dict]:
    """Human-readable summaries of the new analysis categories for the PDF."""
    screening = getattr(video, "screening_result", None)
    if screening is None:
        return []
    out: list[dict] = []
    for s in screening.signals.all():
        ro = s.raw_output or {}
        if s.module == "payment" and s.is_triggered:
            ids = ro.get("identifiers") or ro.get("payment_identifiers") or []
            lines = [str(x) for x in ids][:15] or ["обнаружены платёжные реквизиты"]
            out.append({"title": "Платёжные реквизиты", "lines": lines})
        elif s.module == "brand_link" and s.is_triggered:
            lines = []
            if ro.get("brands"):
                lines.append("Бренды: " + ", ".join(ro["brands"]))
            if ro.get("gambling_terms"):
                lines.append("Термины: " + ", ".join(ro["gambling_terms"][:12]))
            for l in ro.get("suspicious_links", [])[:8]:
                lines.append(f"Ссылка: {l.get('domain', l.get('url', ''))} "
                             f"({', '.join(l.get('reasons', []))})")
            for q in ro.get("qr_codes", [])[:6]:
                link = q.get("link") or {}
                extra = f" → {link.get('domain')}" if link else ""
                lines.append(f"QR-код: {q.get('data', '')[:80]}{extra}")
            out.append({"title": "Казино-бренды, ссылки и QR-коды",
                        "lines": lines or ["обнаружены индикаторы азартных игр"]})
        elif s.module == "audio_forensics" and s.is_triggered:
            lines = []
            if "voice_assessment" in ro:
                lines.append(str(ro["voice_assessment"]))
            for k in ("language", "synthetic_voice_indicator", "pressure_level"):
                if k in ro:
                    lines.append(f"{k}: {ro[k]}")
            out.append({"title": "Аудио-форензика",
                        "lines": lines or ["обнаружены аномалии в речи"]})
        elif s.module == "social_context" and ro.get("total_comments"):
            mi = ro.get("manipulation_index", 0)
            lines = [
                ro.get("verdict", ""),
                f"Индекс накрутки: {mi:.0%}; ботов: {ro.get('bot_count', 0)}/"
                f"{ro.get('total_comments', 0)}; "
                f"тональность +{ro.get('sentiment', {}).get('positive', 0)} / "
                f"−{ro.get('sentiment', {}).get('negative', 0)}",
            ]
            for c in ro.get("bot_comments", [])[:3]:
                lines.append(f"Бот: «{c.get('text', '')[:90]}»")
            for c in ro.get("skeptic_comments", [])[:3]:
                lines.append(f"Реальный пользователь: «{c.get('text', '')[:90]}»")
            out.append({"title": "Комментарии: тональность и накрутка",
                        "lines": [l for l in lines if l]})
    return out


def _append_screenshots(story, video, section, Image, Paragraph, Table,
                        TableStyle, Spacer, small, cm, colors):
    frames = list(video.extracted_frames.all()[:6])
    existing = [f for f in frames if f.file_path and os.path.exists(f.file_path)]
    if not frames:
        return
    section("Скриншоты из видео")
    if not existing:
        story.append(Paragraph(
            "Кадры извлекались, но файлы недоступны на этом узле (общее "
            "медиа-хранилище). В материалах дела они доступны по цепочке "
            "доказательств.", small))
        return
    row, cells = [], []
    for f in existing:
        try:
            img = Image(f.file_path, width=5.0 * cm, height=3.0 * cm, kind="proportional")
        except Exception as exc:  # noqa: BLE001 - broken image, skip
            logger.debug("dossier frame skip %s: %s", f.file_path, exc)
            continue
        cells.append([img, Paragraph(f"t={f.timestamp_sec:.0f}с", small)])
        if len(cells) == 3:
            row.append(cells)
            cells = []
    if cells:
        row.append(cells)
    for r in row:
        t = Table([[c[0] for c in r], [c[1] for c in r]])
        t.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
        story.append(t)
        story.append(Spacer(1, 0.2 * cm))
