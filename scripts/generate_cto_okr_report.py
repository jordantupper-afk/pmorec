#!/usr/bin/env python3
"""
Generate a biweekly CTO report for Developer Platform OKRs/Initiatives.

The input snapshot must come from the Coda source-of-truth page and be saved
as JSON. This script enforces a biweekly cadence starting from a configured
start date (default: 2026-04-10).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from collections import Counter
from statistics import mean
from typing import Any


DEFAULT_CODA_URL = (
    "https://coda.io/d/Developer-Platform-Mission_dLGZ7ZRwER_/"
    "2026-Developer-Platforms-OKRs-Initiatives_suSYCzE2#_lusqZqZ0"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate biweekly CTO OKR and initiatives status report."
    )
    parser.add_argument(
        "--current",
        required=True,
        help="Path to current Coda snapshot JSON.",
    )
    parser.add_argument(
        "--previous",
        help="Path to previous Coda snapshot JSON (optional).",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write markdown report.",
    )
    parser.add_argument(
        "--report-date",
        default=dt.date.today().isoformat(),
        help="Report date in YYYY-MM-DD. Defaults to today.",
    )
    parser.add_argument(
        "--start-date",
        default="2026-04-10",
        help="Biweekly start date in YYYY-MM-DD. Defaults to 2026-04-10.",
    )
    parser.add_argument(
        "--required-source-url",
        default=DEFAULT_CODA_URL,
        help="Required Coda URL to enforce source-of-truth.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Generate report even if date is off biweekly cadence.",
    )
    return parser.parse_args()


def read_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def is_due(report_date: dt.date, start_date: dt.date) -> bool:
    if report_date < start_date:
        return False
    return (report_date - start_date).days % 14 == 0


def norm_status(value: str) -> str:
    v = (value or "").strip().lower()
    mapping = {
        "green": "on_track",
        "on track": "on_track",
        "on_track": "on_track",
        "yellow": "at_risk",
        "at risk": "at_risk",
        "at_risk": "at_risk",
        "red": "off_track",
        "off track": "off_track",
        "off_track": "off_track",
        "blocked": "off_track",
        "done": "on_track",
        "complete": "on_track",
        "completed": "on_track",
    }
    return mapping.get(v, v.replace(" ", "_") if v else "unknown")


def pct(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def risk_band(score: int) -> str:
    if score >= 16:
        return "critical"
    if score >= 12:
        return "high"
    if score >= 8:
        return "medium"
    return "low"


def as_id_map(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item.get("id")): item for item in items if item.get("id") is not None}


def ensure_source_of_truth(
    current: dict[str, Any], required_source_url: str | None
) -> None:
    if not required_source_url:
        return
    source_url = str(current.get("metadata", {}).get("source_url", "")).strip()
    if not source_url:
        raise SystemExit(
            "Snapshot metadata.source_url is missing. "
            "Report must be based on the Coda source of truth."
        )
    if required_source_url not in source_url:
        raise SystemExit(
            "Snapshot metadata.source_url does not match required Coda URL.\n"
            f"Expected to include: {required_source_url}\n"
            f"Found: {source_url}"
        )


def compute_metrics(snapshot: dict[str, Any]) -> dict[str, Any]:
    okrs = snapshot.get("okrs", [])
    initiatives = snapshot.get("initiatives", [])
    risks = snapshot.get("risks", [])

    okr_statuses = [norm_status(x.get("status", "")) for x in okrs]
    init_statuses = [norm_status(x.get("status", "")) for x in initiatives]

    status_counter = Counter(okr_statuses)
    init_counter = Counter(init_statuses)

    okr_progresses = [pct(x.get("progress")) for x in okrs]
    init_progresses = [pct(x.get("progress")) for x in initiatives]
    overall_progress = round(mean(okr_progresses), 1) if okr_progresses else 0.0
    initiative_progress = round(mean(init_progresses), 1) if init_progresses else 0.0

    scored_risks: list[dict[str, Any]] = []
    risk_bands = Counter()
    for r in risks:
        sev = int(r.get("severity", 0) or 0)
        lik = int(r.get("likelihood", 0) or 0)
        score = sev * lik
        band = risk_band(score)
        risk_bands[band] += 1
        scored_risks.append({**r, "score": score, "band": band})

    scored_risks.sort(key=lambda x: x["score"], reverse=True)

    return {
        "okrs": okrs,
        "initiatives": initiatives,
        "risks": scored_risks,
        "okr_status_counter": status_counter,
        "initiative_status_counter": init_counter,
        "risk_bands": risk_bands,
        "overall_progress": overall_progress,
        "initiative_progress": initiative_progress,
    }


def derive_changes(
    current: dict[str, Any], previous: dict[str, Any] | None
) -> dict[str, Any]:
    if not previous:
        return {
            "metric_deltas": [],
            "wins": [],
            "issues": [],
            "major_changes": [],
        }

    curr_okr = as_id_map(current.get("okrs", []))
    prev_okr = as_id_map(previous.get("okrs", []))
    curr_init = as_id_map(current.get("initiatives", []))
    prev_init = as_id_map(previous.get("initiatives", []))
    curr_risk = as_id_map(current.get("risks", []))
    prev_risk = as_id_map(previous.get("risks", []))

    wins: list[str] = []
    issues: list[str] = []
    major_changes: list[str] = []

    for okr_id, okr in curr_okr.items():
        if okr_id not in prev_okr:
            major_changes.append(f"New OKR added: {okr.get('name', okr_id)}")
            continue
        prev = prev_okr[okr_id]
        curr_status = norm_status(okr.get("status", ""))
        prev_status = norm_status(prev.get("status", ""))
        curr_progress = pct(okr.get("progress"))
        prev_progress = pct(prev.get("progress"))
        delta = curr_progress - prev_progress

        if delta >= 10:
            wins.append(
                f"{okr.get('name', okr_id)} improved by {delta:.1f} pts "
                f"({prev_progress:.1f}% -> {curr_progress:.1f}%)."
            )
        if curr_status == "off_track":
            issues.append(f"{okr.get('name', okr_id)} is off track.")
        if curr_status != prev_status:
            major_changes.append(
                f"OKR status changed: {okr.get('name', okr_id)} "
                f"({prev_status} -> {curr_status})."
            )

    for init_id, init in curr_init.items():
        if init_id not in prev_init:
            major_changes.append(f"New initiative added: {init.get('name', init_id)}")
            continue
        prev = prev_init[init_id]
        curr_status = norm_status(init.get("status", ""))
        prev_status = norm_status(prev.get("status", ""))
        if curr_status != prev_status:
            major_changes.append(
                f"Initiative status changed: {init.get('name', init_id)} "
                f"({prev_status} -> {curr_status})."
            )
        if curr_status == "off_track":
            issues.append(f"Initiative at risk: {init.get('name', init_id)}.")

    for risk_id, risk in curr_risk.items():
        sev = int(risk.get("severity", 0) or 0)
        lik = int(risk.get("likelihood", 0) or 0)
        score = sev * lik
        if score >= 16:
            issues.append(f"Critical risk: {risk.get('title', risk_id)} (score={score}).")
        if risk_id not in prev_risk:
            major_changes.append(f"New risk logged: {risk.get('title', risk_id)}")

    metric_deltas = []
    for key, label in [
        ("okrs", "Total OKRs"),
        ("initiatives", "Total Initiatives"),
        ("risks", "Total Risks"),
    ]:
        curr_count = len(current.get(key, []))
        prev_count = len(previous.get(key, []))
        metric_deltas.append(
            {"metric": label, "previous": prev_count, "current": curr_count}
        )

    return {
        "metric_deltas": metric_deltas,
        "wins": sorted(set(wins)),
        "issues": sorted(set(issues)),
        "major_changes": sorted(set(major_changes)),
    }


def build_decision_log(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []

    for init in metrics["initiatives"]:
        if init.get("decision_required"):
            decisions.append(
                {
                    "type": "initiative",
                    "name": init.get("name", "Unknown"),
                    "owner": init.get("owner", "Unassigned"),
                    "decision": init.get("decision_summary", "Decision details missing"),
                    "due": init.get("decision_due", "TBD"),
                }
            )

    for risk in metrics["risks"]:
        if risk.get("decision_required"):
            decisions.append(
                {
                    "type": "risk",
                    "name": risk.get("title", "Unknown"),
                    "owner": risk.get("owner", "Unassigned"),
                    "decision": risk.get("decision_summary", "Decision details missing"),
                    "due": risk.get("decision_due", "TBD"),
                }
            )

    def due_key(item: dict[str, Any]) -> tuple[int, str]:
        due = str(item.get("due", "TBD"))
        if due == "TBD":
            return (1, due)
        return (0, due)

    decisions.sort(key=due_key)
    return decisions


def render_pie(title: str, entries: dict[str, int]) -> str:
    safe_entries = {k: v for k, v in entries.items() if v > 0}
    if not safe_entries:
        safe_entries = {"none": 1}
    lines = ["```mermaid", f"pie title {title}"]
    for key, value in safe_entries.items():
        label = key.replace("_", " ").title()
        lines.append(f'  "{label}" : {value}')
    lines.append("```")
    return "\n".join(lines)


def render_report(
    report_date: dt.date,
    current: dict[str, Any],
    metrics: dict[str, Any],
    changes: dict[str, Any],
) -> str:
    meta = current.get("metadata", {})
    period = meta.get("period", "H1")
    source_url = meta.get("source_url", "N/A")
    prepared_by = meta.get("prepared_by", "Program Management")

    okr_count = len(metrics["okrs"])
    init_count = len(metrics["initiatives"])
    risk_count = len(metrics["risks"])
    off_track = metrics["okr_status_counter"].get("off_track", 0)
    critical_risks = metrics["risk_bands"].get("critical", 0)

    summary_lines = [
        f"- **Period:** {period}",
        f"- **Overall OKR Progress:** {metrics['overall_progress']:.1f}%",
        f"- **At-risk signal:** {off_track} off-track OKR(s), {critical_risks} critical risk(s)",
        f"- **Report prepared by:** {prepared_by}",
    ]

    decision_log = build_decision_log(metrics)

    top_risks = metrics["risks"][:8]
    at_risk_inits = [
        i
        for i in metrics["initiatives"]
        if norm_status(i.get("status", "")) in {"at_risk", "off_track"}
    ][:10]

    lines: list[str] = []
    lines.append(f"# Developer Platform OKR Update - {report_date.isoformat()}")
    lines.append("")
    lines.append(f"**Source of truth:** {source_url}")
    lines.append("")
    lines.append("## Executive Summary")
    lines.extend(summary_lines)
    lines.append("")
    lines.append("## KPI Snapshot")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    lines.append(f"| Total OKRs | {okr_count} |")
    lines.append(f"| Total Initiatives | {init_count} |")
    lines.append(f"| Total Risks | {risk_count} |")
    lines.append(f"| Avg OKR Progress | {metrics['overall_progress']:.1f}% |")
    lines.append(f"| Avg Initiative Progress | {metrics['initiative_progress']:.1f}% |")
    lines.append("")

    if changes["metric_deltas"]:
        lines.append("### Changes Since Last Update")
        lines.append("")
        lines.append("| Metric | Previous | Current | Delta |")
        lines.append("|---|---:|---:|---:|")
        for delta in changes["metric_deltas"]:
            d = int(delta["current"]) - int(delta["previous"])
            lines.append(
                f"| {delta['metric']} | {delta['previous']} | {delta['current']} | {d:+d} |"
            )
        lines.append("")

    lines.append("## OKR Health")
    lines.append("")
    lines.append(render_pie("OKR Status Distribution", dict(metrics["okr_status_counter"])))
    lines.append("")
    lines.append("| OKR | Owner | Status | Progress | Confidence |")
    lines.append("|---|---|---|---:|---:|")
    for okr in metrics["okrs"]:
        lines.append(
            "| {name} | {owner} | {status} | {progress:.1f}% | {confidence} |".format(
                name=okr.get("name", ""),
                owner=okr.get("owner", ""),
                status=norm_status(okr.get("status", "")).replace("_", " "),
                progress=pct(okr.get("progress")),
                confidence=okr.get("confidence", "n/a"),
            )
        )
    lines.append("")

    lines.append("## Initiative Callouts (At Risk / Off Track)")
    lines.append("")
    lines.append("| Initiative | OKR | Owner | Status | Progress | Next Milestone |")
    lines.append("|---|---|---|---|---:|---|")
    for init in at_risk_inits:
        lines.append(
            "| {name} | {okr} | {owner} | {status} | {progress:.1f}% | {milestone} |".format(
                name=init.get("name", ""),
                okr=init.get("okr_id", ""),
                owner=init.get("owner", ""),
                status=norm_status(init.get("status", "")).replace("_", " "),
                progress=pct(init.get("progress")),
                milestone=init.get("next_milestone", "TBD"),
            )
        )
    if not at_risk_inits:
        lines.append("| None | - | - | - | - | - |")
    lines.append("")

    lines.append("## Risk Profile")
    lines.append("")
    lines.append(render_pie("Risk Exposure Bands", dict(metrics["risk_bands"])))
    lines.append("")
    lines.append("| Risk | Owner | Severity | Likelihood | Score | Band | Status | Mitigation |")
    lines.append("|---|---|---:|---:|---:|---|---|---|")
    for risk in top_risks:
        lines.append(
            "| {title} | {owner} | {sev} | {lik} | {score} | {band} | {status} | {mitigation} |".format(
                title=risk.get("title", ""),
                owner=risk.get("owner", ""),
                sev=risk.get("severity", 0),
                lik=risk.get("likelihood", 0),
                score=risk.get("score", 0),
                band=risk.get("band", ""),
                status=risk.get("status", ""),
                mitigation=risk.get("mitigation", ""),
            )
        )
    if not top_risks:
        lines.append("| None | - | - | - | - | - | - | - |")
    lines.append("")

    lines.append("## Decisions Required")
    lines.append("")
    lines.append("| Type | Topic | Owner | Decision Needed | Due |")
    lines.append("|---|---|---|---|---|")
    for d in decision_log:
        lines.append(
            f"| {d['type']} | {d['name']} | {d['owner']} | {d['decision']} | {d['due']} |"
        )
    if not decision_log:
        lines.append("| None | - | - | - | - |")
    lines.append("")

    lines.append("## Major Callouts")
    lines.append("")
    lines.append("### Wins")
    if changes["wins"]:
        for win in changes["wins"][:10]:
            lines.append(f"- {win}")
    else:
        lines.append("- No major wins were automatically detected.")
    lines.append("")

    lines.append("### Issues")
    if changes["issues"]:
        for issue in changes["issues"][:10]:
            lines.append(f"- {issue}")
    else:
        lines.append("- No major issues were automatically detected.")
    lines.append("")

    lines.append("### Major Changes")
    if changes["major_changes"]:
        for change in changes["major_changes"][:15]:
            lines.append(f"- {change}")
    else:
        lines.append("- No major structural changes were detected.")
    lines.append("")

    lines.append("## Notes")
    lines.append(
        "- This report is auto-generated from the Coda snapshot for this cycle."
    )
    lines.append(
        "- Program Manager should review and adjust narrative before sending to CTO."
    )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()

    report_date = parse_date(args.report_date)
    start_date = parse_date(args.start_date)

    if not args.force and not is_due(report_date, start_date):
        print(
            "Not a scheduled biweekly date. "
            f"Start={start_date.isoformat()}, report_date={report_date.isoformat()}."
        )
        return 0

    current = read_json(args.current)
    previous = read_json(args.previous) if args.previous and os.path.exists(args.previous) else None

    ensure_source_of_truth(current, args.required_source_url)

    metrics = compute_metrics(current)
    changes = derive_changes(current, previous)
    report = render_report(report_date, current, metrics, changes)

    output_dir = os.path.dirname(args.output) or "."
    os.makedirs(output_dir, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"Report generated: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
