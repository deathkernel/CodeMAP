"""Architecture, quality, and security reporting endpoints."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.services.code_index import _database_path

router = APIRouter(prefix="/api/reports", tags=["reports"])


class ReportRequest(BaseModel):
    result: dict[str, Any]


class SnapshotRequest(BaseModel):
    result: dict[str, Any]


def _report_summary(result: dict[str, Any]) -> dict[str, Any]:
    bug_stats = result.get("bug_stats") or {}
    severity = bug_stats.get("by_severity") or {}
    health = result.get("architecture_health") or {}
    stats = result.get("stats") or {}
    return {
        "repository": str(result.get("repository") or "Unknown repository"),
        "files": int(stats.get("files_analyzed", len(result.get("nodes") or [])) or 0),
        "dependencies": int(stats.get("dependencies_found", len(result.get("edges") or [])) or 0),
        "health_score": int(health.get("health_score", 0) or 0),
        "health_grade": str(health.get("health_grade") or "unknown"),
        "bugs_total": int(bug_stats.get("total", len(result.get("bug_findings") or [])) or 0),
        "bugs_high": int(severity.get("high", 0) or 0),
        "bugs_medium": int(severity.get("medium", 0) or 0),
        "bugs_low": int(severity.get("low", 0) or 0),
        "circular_groups": len((result.get("architecture_insights") or {}).get("circular_dependencies") or []),
        "high_risk_modules": int((health.get("health_stats") or {}).get("high_risk_modules", 0) or 0),
    }


@router.post("/architecture.pdf")
async def export_architecture_pdf(request: ReportRequest):
    """Generate a downloadable architecture, code-quality, and security PDF."""
    result = request.result
    summary = _report_summary(result)
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=17 * mm,
        bottomMargin=17 * mm,
        title=f"CodeMap Report - {summary['repository']}",
        author="CodeMap",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ReportTitle", parent=styles["Title"], alignment=TA_CENTER,
        textColor=colors.HexColor("#26345a"), spaceAfter=5 * mm,
    ))
    styles.add(ParagraphStyle(
        name="SectionHeading", parent=styles["Heading2"],
        textColor=colors.HexColor("#26345a"), spaceBefore=5 * mm, spaceAfter=2 * mm,
    ))
    styles.add(ParagraphStyle(
        name="SmallCell", parent=styles["BodyText"], fontSize=8, leading=10,
    ))
    story = [
        Paragraph("CodeMap Repository Report", styles["ReportTitle"]),
        Paragraph(escape(summary["repository"]), styles["Heading2"]),
        Paragraph(
            f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} · "
            f"Branch: {escape(str(result.get('default_branch') or 'N/A'))}",
            styles["Normal"],
        ),
        Spacer(1, 4 * mm),
        Paragraph("Architecture overview", styles["SectionHeading"]),
    ]

    metrics = [
        ["Files analyzed", "Dependencies", "Health score", "Circular groups"],
        [str(summary["files"]), str(summary["dependencies"]),
         f"{summary['health_score']}/100 ({summary['health_grade']})",
         str(summary["circular_groups"])],
    ]
    metric_table = Table(metrics, colWidths=[40 * mm, 40 * mm, 55 * mm, 40 * mm])
    metric_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8edf7")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#26345a")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(metric_table)

    advanced = result.get("advanced_architecture") or {}
    frameworks = advanced.get("frameworks") or []
    story.append(Paragraph("Frameworks and entry points", styles["SectionHeading"]))
    story.append(Paragraph(
        "Detected frameworks: " + (", ".join(escape(str(item)) for item in frameworks) or "None detected"),
        styles["BodyText"],
    ))
    entry_points = advanced.get("entry_points") or (result.get("architecture_insights") or {}).get("entry_points") or []
    if entry_points:
        rows = [["Path", "Reason"]]
        rows.extend([
            [Paragraph(escape(str(item.get("path", "")), styles["SmallCell"]),
             Paragraph(escape(str(item.get("reason", item.get("framework", ""))), styles["SmallCell"]))]
            for item in entry_points[:40]
        ])
        table = Table(rows, colWidths=[75 * mm, 100 * mm], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8edf7")),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(table)
    else:
        story.append(Paragraph("No entry-point candidates detected.", styles["BodyText"]))

    story.append(Paragraph("Code quality and security", styles["SectionHeading"]))
    story.append(Paragraph(
        f"Potential findings: {summary['bugs_total']} total · "
        f"{summary['bugs_high']} high · {summary['bugs_medium']} medium · {summary['bugs_low']} low",
        styles["BodyText"],
    ))
    story.append(Paragraph(
        f"High-risk modules: {summary['high_risk_modules']}",
        styles["BodyText"],
    ))
    findings = result.get("bug_findings") or []
    if findings:
        rows = [["Severity", "Finding", "Location", "Recommendation"]]
        for item in findings[:150]:
            rows.append([
                Paragraph(escape(str(item.get("severity", "")).upper()), styles["SmallCell"]),
                Paragraph(escape(str(item.get("title", item.get("rule_id", "")))), styles["SmallCell"]),
                Paragraph(escape(f"{item.get('path', '')}:{item.get('line', '')}"), styles["SmallCell"]),
                Paragraph(escape(str(item.get("recommendation", ""))), styles["SmallCell"]),
            ])
        table = Table(rows, colWidths=[18 * mm, 43 * mm, 48 * mm, 66 * mm], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8edf7")),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(table)
        if len(findings) > 150:
            story.append(Paragraph(
                f"Showing 150 of {len(findings)} findings. Export JSON for the complete analysis.",
                styles["Italic"],
            ))
    else:
        story.append(Paragraph("No potential findings were returned by the static scanner.", styles["BodyText"]))

    health = result.get("architecture_health") or {}
    risk_factors = health.get("risk_factors") or []
    story.append(Paragraph("Architecture risk factors", styles["SectionHeading"]))
    if risk_factors:
        story.extend(Paragraph("• " + escape(str(item)), styles["BodyText"]) for item in risk_factors[:30])
    else:
        story.append(Paragraph("No architecture risk factors were reported.", styles["BodyText"]))

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        "Methodology note: CodeMap uses static heuristics and pattern-based checks. "
        "Findings and architecture indicators are candidates for human review, not proof "
        "of an exploitable vulnerability or a complete architectural specification.",
        styles["SmallCell"],
    ))
    document.build(story)
    buffer.seek(0)
    filename = "codemap-report.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/snapshots")
async def save_report_snapshot(request: SnapshotRequest):
    """Persist a compact analysis snapshot for before/after comparison."""
    result = request.result
    project_id = str(result.get("project_id") or "")
    if not project_id or len(project_id) > 128:
        raise HTTPException(status_code=400, detail="A valid project ID is required.")
    summary = _report_summary(result)
    snapshot_id = uuid.uuid4().hex
    created_at = datetime.now(timezone.utc).isoformat()
    connection = sqlite3.connect(_database_path(), timeout=30)
    try:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS code_report_snapshots ("
            "snapshot_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, created_at TEXT NOT NULL, "
            "summary_json TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO code_report_snapshots (snapshot_id, project_id, created_at, summary_json) "
            "VALUES (?, ?, ?, ?)",
            (snapshot_id, project_id, created_at, json.dumps(summary)),
        )
        connection.commit()
    finally:
        connection.close()
    return {"snapshot_id": snapshot_id, "project_id": project_id, "created_at": created_at, "summary": summary}


@router.get("/compare/{project_id}")
async def compare_report_snapshots(project_id: str):
    """Compare the two most recent saved analysis snapshots for one project."""
    if not project_id or len(project_id) > 128:
        raise HTTPException(status_code=400, detail="Invalid project ID.")
    connection = sqlite3.connect(_database_path(), timeout=30)
    try:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS code_report_snapshots ("
            "snapshot_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, created_at TEXT NOT NULL, "
            "summary_json TEXT NOT NULL)"
        )
        rows = connection.execute(
            "SELECT snapshot_id, created_at, summary_json FROM code_report_snapshots "
            "WHERE project_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 2",
            (project_id,),
        ).fetchall()
    finally:
        connection.close()
    if len(rows) < 2:
        raise HTTPException(status_code=409, detail="Save at least two report snapshots to compare.")
    after = json.loads(rows[0][2])
    before = json.loads(rows[1][2])
    numeric_fields = [
        "files", "dependencies", "health_score", "bugs_total", "bugs_high",
        "bugs_medium", "bugs_low", "circular_groups", "high_risk_modules",
    ]
    changes = {
        field: {"before": before.get(field, 0), "after": after.get(field, 0),
                "delta": after.get(field, 0) - before.get(field, 0)}
        for field in numeric_fields
    }
    return {
        "project_id": project_id,
        "before": {"snapshot_id": rows[1][0], "created_at": rows[1][1], "summary": before},
        "after": {"snapshot_id": rows[0][0], "created_at": rows[0][1], "summary": after},
        "changes": changes,
        "note": "Positive bug and risk deltas mean more reported issues; a positive health-score delta means a higher heuristic score.",
    }
