"""Official PDF reports for government-approved assessments (Role 4).

Only assessments with status ``approved`` may be rendered. Each rendering is
preserved as a numbered report version (PDF bytes on disk, metadata on the
assessment record) so earlier official reports remain retrievable for audit.
"""

from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from services import json_store

NAVY = colors.HexColor("#18365b")
GREEN = colors.HexColor("#166534")
LIGHT_GREEN = colors.HexColor("#dcfce7")
LIGHT_GREY = colors.HexColor("#f1f5f9")


def reports_dir() -> Path:
    path = json_store.get_database_dir() / "assessment_reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def report_filename(public_id: str, version: int) -> str:
    safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in public_id)
    return f"{safe}_report_v{version}.pdf"


def _money(value: Any, unit: str) -> str:
    if value is None:
        return "Unknown"
    if unit == "people":
        return f"{float(value):,.0f} people"
    try:
        return f"Rs.{float(value):,.0f}"
    except (TypeError, ValueError):
        return str(value)


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    title = ParagraphStyle("RptTitle", parent=base["Title"], textColor=NAVY, fontSize=18, leading=22)
    h1 = ParagraphStyle("RptH1", parent=base["Heading1"], textColor=NAVY, fontSize=13, leading=16, spaceBefore=10, spaceAfter=6)
    h2 = ParagraphStyle("RptH2", parent=base["Heading2"], textColor=NAVY, fontSize=11, leading=14, spaceBefore=8, spaceAfter=4)
    body = ParagraphStyle("RptBody", parent=base["BodyText"], fontSize=9, leading=13)
    small = ParagraphStyle("RptSmall", parent=base["BodyText"], fontSize=8, leading=11, textColor=colors.HexColor("#475569"))
    cell = ParagraphStyle("RptCell", parent=base["BodyText"], fontSize=8, leading=11)
    banner = ParagraphStyle(
        "RptBanner", parent=base["BodyText"], textColor=colors.white,
        fontSize=11, leading=14, alignment=1, fontName="Helvetica-Bold",
    )
    return {"title": title, "h1": h1, "h2": h2, "body": body, "small": small, "cell": cell, "banner": banner}


def _table(rows: list[list[Any]], widths: list[float], header: bool = True) -> Table:
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, LIGHT_GREY]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ]
    return Table(rows, colWidths=widths, style=TableStyle(style), repeatRows=1 if header else 0)


def _esc(value: Any) -> str:
    return str(value if value is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_approved_report(
    assessment: dict[str, Any],
    current: dict[str, Any],
    report_version: int,
    generated_at: str,
    generated_by: dict[str, str],
) -> bytes:
    """Render the official PDF for an approved assessment. Returns PDF bytes."""
    if assessment.get("status") != "approved":
        raise ValueError("Only approved assessments may be rendered as official reports.")

    ai = assessment.get("aiAssessment") or {}
    decision = assessment.get("decision") or {}
    snapshot = assessment.get("approvedSnapshot") or {}
    public_id = str(assessment.get("publicId") or assessment.get("id") or "")
    styles = _styles()
    story: list[Any] = []

    story.append(
        Table(
            [[Paragraph("GOVERNMENT APPROVED — OFFICIAL REPORT", styles["banner"])]],
            colWidths=[170 * mm],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), GREEN),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]),
        )
    )
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Disaster Assessment, Cost Estimation &amp; Compensation Report", styles["title"]))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        f"Assessment ID <b>{_esc(public_id)}</b> &nbsp;|&nbsp; Assessment version "
        f"<b>{assessment.get('version', 1)}</b> &nbsp;|&nbsp; Report version <b>{report_version}</b>"
        f"<br/>Report generated <b>{_esc(generated_at)}</b> by <b>{_esc(generated_by.get('name', ''))}</b> "
        f"({_esc(generated_by.get('roleName', ''))})"
        f"<br/>Assessment engine <b>{_esc(ai.get('engineVersion', ''))}</b> &nbsp;|&nbsp; "
        f"AI narrative source: {_esc(ai.get('narrativeSource', ''))}",
        styles["small"],
    ))
    story.append(Spacer(1, 3 * mm))

    # -- Disaster & region ---------------------------------------------------
    story.append(Paragraph("1. Disaster &amp; affected region", styles["h1"]))
    detail = ai.get("regionDetail") or {}
    meta_rows = [
        [Paragraph("<b>Field</b>", styles["cell"]), Paragraph("<b>Detail</b>", styles["cell"])],
        [Paragraph("Region", styles["cell"]), Paragraph(_esc(ai.get("regionName", "")), styles["cell"])],
        [Paragraph("Region key / code", styles["cell"]),
         Paragraph(f"{_esc(ai.get('regionKey', ''))} / {_esc(detail.get('code') or '—')}", styles["cell"])],
        [Paragraph("Country / State", styles["cell"]),
         Paragraph(f"{_esc(detail.get('country') or '—')} / {_esc(detail.get('state') or '—')}", styles["cell"])],
        [Paragraph("Hazard", styles["cell"]),
         Paragraph(f"{_esc(ai.get('hazardName', ''))} ({_esc(ai.get('hazardId', ''))})", styles["cell"])],
        [Paragraph("Affected areas", styles["cell"]),
         Paragraph(_esc("; ".join(ai.get("affectedAreas") or []) or "—"), styles["cell"])],
        [Paragraph("Overall confidence", styles["cell"]),
         Paragraph(_esc(ai.get("overallConfidence", "")), styles["cell"])],
        [Paragraph("Assessment created", styles["cell"]),
         Paragraph(f"{_esc(assessment.get('createdAt', ''))} by {_esc(assessment.get('createdByName', ''))}", styles["cell"])],
    ]
    story.append(_table(meta_rows, [45 * mm, 125 * mm]))

    # -- AI assessment & reasoning --------------------------------------------
    story.append(Paragraph("2. AI-generated assessment &amp; reasoning", styles["h1"]))
    story.append(Paragraph(_esc(ai.get("narrative") or ""), styles["body"]))
    story.append(Spacer(1, 2 * mm))
    for i, line in enumerate(ai.get("reasoning") or [], start=1):
        story.append(Paragraph(f"{i}. {_esc(line)}", styles["body"]))
    if ai.get("officerNotes"):
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(f"<b>Requesting officer notes:</b> {_esc(ai['officerNotes'])}", styles["body"]))

    # -- Figures ----------------------------------------------------------------
    story.append(Paragraph("3. Estimated damage &amp; costs (AI vs approved)", styles["h1"]))
    fig_rows: list[list[Any]] = [[
        Paragraph("<b>Item</b>", styles["cell"]),
        Paragraph("<b>AI estimate</b>", styles["cell"]),
        Paragraph("<b>Approved figure</b>", styles["cell"]),
        Paragraph("<b>Confidence</b>", styles["cell"]),
    ]]
    for fig in current.get("figures") or []:
        fig_rows.append([
            Paragraph(_esc(fig.get("label", "")), styles["cell"]),
            Paragraph(_money(fig.get("value"), str(fig.get("unit") or "")), styles["cell"]),
            Paragraph(
                f"<b>{_esc(_money(fig.get('currentValue'), str(fig.get('unit') or '')))}</b>"
                + (" (edited)" if fig.get("edited") else ""),
                styles["cell"],
            ),
            Paragraph(_esc(fig.get("confidence", "")), styles["cell"]),
        ])
    story.append(_table(fig_rows, [62 * mm, 38 * mm, 42 * mm, 28 * mm]))
    totals = current.get("totals") or {}
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        f"<b>Approved totals:</b> damage {_esc(_money(totals.get('damageTotalInr'), 'INR'))}"
        + (" (officer override)" if totals.get("damageTotalOverride") else " (derived)")
        + f" &nbsp;|&nbsp; preparation {_esc(_money(totals.get('preparationInr'), 'INR'))}"
        + f" &nbsp;|&nbsp; recovery {_esc(_money(totals.get('recoveryInr'), 'INR'))}"
        + f" &nbsp;|&nbsp; grand total {_esc(_money(totals.get('grandTotalInr'), 'INR'))}",
        styles["body"],
    ))
    story.append(Paragraph(
        "The indicative relief envelope is a planning figure only; it is not an eligibility "
        "decision, offer, or sanction.",
        styles["small"],
    ))

    # -- Workings -----------------------------------------------------------------
    story.append(Paragraph("4. Calculation, assumptions, sources &amp; explanation", styles["h1"]))
    for fig in current.get("figures") or []:
        story.append(Paragraph(f"<b>{_esc(fig.get('label', ''))}</b> — confidence {_esc(fig.get('confidence', ''))}", styles["h2"]))
        story.append(Paragraph(f"<b>Calculation:</b> {_esc(fig.get('calculation') or '—')}", styles["body"]))
        story.append(Paragraph(f"<b>Explanation:</b> {_esc(fig.get('explanation') or '—')}", styles["body"]))
        assumptions = fig.get("assumptions") or []
        story.append(Paragraph(
            "<b>Assumptions:</b> " + (_esc("; ".join(assumptions)) if assumptions else "—"), styles["body"],
        ))
        sources = fig.get("sources") or []
        story.append(Paragraph(
            "<b>Sources:</b> "
            + (
                _esc("; ".join(f"{s.get('name')}: {s.get('detail')} (at {s.get('fetchedAt')})" for s in sources))
                if sources else "—"
            ),
            styles["body"],
        ))
        if fig.get("calibratedFrom"):
            cal = fig["calibratedFrom"]
            story.append(Paragraph(
                f"<b>Learning calibration:</b> {cal.get('appliedDeltaPct'):+.1f}% applied from "
                f"{cal.get('feedbackCount')} verified corrections "
                f"(median {cal.get('medianDeltaPct'):+.1f}%).",
                styles["body"],
            ))

    # -- Corrections ----------------------------------------------------------------
    story.append(Paragraph("5. Official corrections &amp; justifications", styles["h1"]))
    edits = assessment.get("officialEdits") or []
    if not edits:
        story.append(Paragraph("No corrections. The AI figures were approved unchanged.", styles["body"]))
    else:
        edit_rows: list[list[Any]] = [[
            Paragraph("<b>Field</b>", styles["cell"]),
            Paragraph("<b>AI value</b>", styles["cell"]),
            Paragraph("<b>Approved value</b>", styles["cell"]),
            Paragraph("<b>Officer / time</b>", styles["cell"]),
            Paragraph("<b>Reason</b>", styles["cell"]),
        ]]
        for edit in edits:
            edit_rows.append([
                Paragraph(_esc(edit.get("label") or edit.get("path", "")), styles["cell"]),
                Paragraph(_esc(str(edit.get("oldValue")) if edit.get("oldValue") is not None else "Unknown"), styles["cell"]),
                Paragraph(_esc(str(edit.get("newValue")) if edit.get("newValue") is not None else "Unknown"), styles["cell"]),
                Paragraph(f"{_esc(edit.get('byName', ''))}<br/>{_esc(edit.get('at', ''))}", styles["cell"]),
                Paragraph(_esc(edit.get("reason", "")), styles["cell"]),
            ])
        story.append(_table(edit_rows, [34 * mm, 26 * mm, 30 * mm, 36 * mm, 44 * mm]))

    # -- Approval -------------------------------------------------------------------
    story.append(Paragraph("6. Approval details &amp; history", styles["h1"]))
    story.append(Paragraph(
        f"<b>Decision:</b> {_esc(decision.get('action', ''))} by "
        f"<b>{_esc(decision.get('byName', ''))}</b> at {_esc(decision.get('at', ''))} "
        f"(assessment version {decision.get('version', '')}).<br/>"
        f"<b>Reason:</b> {_esc(decision.get('reason', ''))}",
        styles["body"],
    ))
    story.append(Spacer(1, 2 * mm))
    hist_rows: list[list[Any]] = [[
        Paragraph("<b>Time</b>", styles["cell"]),
        Paragraph("<b>Officer</b>", styles["cell"]),
        Paragraph("<b>Action</b>", styles["cell"]),
        Paragraph("<b>Reason / detail</b>", styles["cell"]),
    ]]
    for entry in assessment.get("approvalHistory") or []:
        hist_rows.append([
            Paragraph(_esc(entry.get("at", "")), styles["cell"]),
            Paragraph(_esc(entry.get("byName", "")), styles["cell"]),
            Paragraph(_esc(entry.get("action", "")), styles["cell"]),
            Paragraph(_esc(entry.get("reason", "")), styles["cell"]),
        ])
    story.append(_table(hist_rows, [38 * mm, 36 * mm, 28 * mm, 68 * mm]))

    # -- Evidence --------------------------------------------------------------------
    story.append(Paragraph("7. Supporting evidence &amp; data sources", styles["h1"]))
    summary = ai.get("evidenceSummary") or {}
    story.append(Paragraph(
        f"Tasks in region: {summary.get('taskCount', 0)} "
        f"({summary.get('submittedTaskCount', 0)} submitted) &nbsp;|&nbsp; "
        f"Field reports: {summary.get('reportCount', 0)} &nbsp;|&nbsp; "
        f"People assisted: {summary.get('peopleAssistedSum', 0)} &nbsp;|&nbsp; "
        f"Verified corrections for hazard: {summary.get('verifiedFeedbackCount', 0)}",
        styles["body"],
    ))
    story.append(Paragraph(
        f"Damage submissions: {summary.get('damageAssessmentCount', 0)} "
        f"&nbsp;|&nbsp; Expense records: {summary.get('expenseCount', 0)} "
        f"(preparedness {_esc(_money(summary.get('observedPreparednessInr'), 'INR'))}, "
        f"recovery {_esc(_money(summary.get('observedRecoveryInr'), 'INR'))}) "
        f"&nbsp;|&nbsp; Evidence attachments: {summary.get('evidenceAttachmentCount', 0)} "
        f"&nbsp;|&nbsp; Photos: {summary.get('photoCount', 0)}",
        styles["body"],
    ))
    if summary.get("regionalPopulationNote"):
        story.append(Paragraph(
            f"<b>Population context:</b> {_esc(summary['regionalPopulationNote'])}",
            styles["body"],
        ))
    if summary.get("gaps"):
        story.append(Paragraph(f"<b>Evidence gaps:</b> {_esc(' '.join(summary['gaps']))}", styles["body"]))
    for excerpt in ai.get("evidenceExcerpts") or []:
        photo_bit = (
            f" [{excerpt.get('photoCount', 0)} photo(s)]"
            if excerpt.get("photoCount")
            else ""
        )
        story.append(Paragraph(
            f"• {_esc(excerpt.get('at', ''))} — {_esc(excerpt.get('byName', ''))}"
            f"{(' @ ' + _esc(excerpt.get('locationNote'))) if excerpt.get('locationNote') else ''}: "
            f"{_esc(excerpt.get('text', ''))}{photo_bit}",
            styles["body"],
        ))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(f"<b>Insurance:</b> {_esc(ai.get('insuranceNotes') or '')}", styles["body"]))
    story.append(Paragraph(f"<b>Disclaimer:</b> {_esc(ai.get('disclaimer') or '')}", styles["small"]))
    story.append(Paragraph(
        f"<b>Snapshot:</b> approved figures frozen at version {snapshot.get('version', '')} on "
        f"{_esc(snapshot.get('approvedAt', ''))}. Historical records are immutable; later engine "
        "updates never alter this report.",
        styles["small"],
    ))

    story.append(HRFlowable(width="100%", thickness=1, color=NAVY))
    story.append(Paragraph(
        f"3P Intelligence — assessment {public_id}, report v{report_version}, generated {generated_at}. "
        "Verify against the stored assessment record before any official action.",
        styles["small"],
    ))

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
        title=f"Government Approved Assessment {public_id}",
        author="3P Intelligence",
    )

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawCentredString(
            A4[0] / 2, 12 * mm,
            f"{public_id} · report v{report_version} · page {doc.page}",
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf


def write_report_file(public_id: str, version: int, pdf: bytes) -> tuple[str, int, str]:
    """Persist one report version. Returns (filename, byte_size, sha256)."""
    filename = report_filename(public_id, version)
    path = reports_dir() / filename
    with open(path, "wb") as handle:
        handle.write(pdf)
    digest = hashlib.sha256(pdf).hexdigest()
    return filename, len(pdf), digest


def read_report_file(filename: str) -> bytes:
    path = reports_dir() / Path(filename).name
    with open(path, "rb") as handle:
        return handle.read()
