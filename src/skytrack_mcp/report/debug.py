"""Inspect evidence for one mission execution without merging separate runs."""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Any

from skytrack_mcp.config import CLIENT_DATA_DIR
from skytrack_mcp.report.parser import is_synthetic_report

_REPORT_GLOB = "skytrack-mission-report*.json"
_SYNTHETIC_GLOB = "synthetic-mission-report*.json"
_LOG_SUFFIXES = {".log", ".txt", ".out"}


def _timestamp_value(value: Any) -> datetime.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=datetime.timezone.utc)


def _entry_timestamp(entry: dict[str, Any]) -> str | None:
    summary = entry.get("status_summary") or {}
    values = [entry.get("timestamp"), summary.get("end_time"), summary.get("execution_end_time")]
    events = entry.get("execution_events") or []
    values.extend(event.get("timestamp") for event in events if isinstance(event, dict))
    values.extend([summary.get("start_time"), summary.get("execution_start_time")])
    parsed_values = [(parsed, str(value)) for value in values if (parsed := _timestamp_value(value))]
    return max(parsed_values, key=lambda pair: pair[0])[1] if parsed_values else None


def _select_entry(
    report: dict[str, Any], execution_id: str | None
) -> dict[str, Any] | None:
    entries = report.get("execution_report")
    if isinstance(entries, list):
        valid = [entry for entry in entries if isinstance(entry, dict)]
        if execution_id is not None:
            return next(
                (entry for entry in valid if str(entry.get("execution_id", "")) == execution_id),
                None,
            )
        if not valid:
            return None
        stamped = [(entry, _timestamp_value(_entry_timestamp(entry))) for entry in valid]
        with_timestamps = [(entry, stamp) for entry, stamp in stamped if stamp is not None]
        return max(with_timestamps, key=lambda pair: pair[1])[0] if with_timestamps else valid[-1]

    candidate_id = report.get("execution_id") or report.get("selected_execution_id")
    if execution_id is not None and str(candidate_id or "") != execution_id:
        return None
    return report if any(key in report for key in ("execution_events", "waypoints_reached", "execution_status")) else None


def _mission_matches(report: dict[str, Any], mission_id: str) -> bool:
    metadata = report.get("execution_metadata") or {}
    report_mission_id = report.get("mission_id") or metadata.get("mission_id")
    return report_mission_id in (None, "") or str(report_mission_id) == str(mission_id)


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _find_report(
    mission_dir: Path,
    mission_id: str,
    execution_id: str | None,
    *,
    synthetic: bool | None,
) -> tuple[Path, dict[str, Any], dict[str, Any]] | None:
    paths = [*mission_dir.glob(_REPORT_GLOB), *mission_dir.glob(_SYNTHETIC_GLOB)]
    candidates: list[tuple[datetime.datetime, Path, dict[str, Any], dict[str, Any]]] = []
    for path in paths:
        report = _load_json(path)
        if report is None or not _mission_matches(report, mission_id):
            continue
        entry = _select_entry(report, execution_id)
        if entry is None:
            continue
        selected_id = str(entry.get("execution_id", "")) or None
        entry_is_synthetic = is_synthetic_report(
            {**report, "execution_report": [entry]}, path, selected_id
        )
        if synthetic is not None and entry_is_synthetic != synthetic:
            continue
        timestamp = _timestamp_value(_entry_timestamp(entry))
        sort_timestamp = timestamp or datetime.datetime.fromtimestamp(
            path.stat().st_mtime, tz=datetime.timezone.utc
        )
        candidates.append((sort_timestamp, path, report, entry))
    if not candidates:
        return None
    _, path, report, entry = max(candidates, key=lambda item: (item[0], item[1].name))
    return path, report, entry


def _correlated_log_files(logs_dir: Path, execution_id: str | None) -> list[tuple[Path, str]]:
    if not logs_dir.exists() or execution_id is None:
        return []
    results: list[tuple[Path, str]] = []
    for path in sorted(logs_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _LOG_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        markers = list(
            re.finditer(r"(?:execution[_ ]id|exec[_ ]id)\s*[:=]\s*['\"]?([\w-]+)", text, re.IGNORECASE)
        )
        if not markers and execution_id in str(path.relative_to(logs_dir)):
            results.append((path, text))
            continue
        for index, marker in enumerate(markers):
            if marker.group(1) != execution_id:
                continue
            end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
            results.append((path, text[marker.start():end]))
    return results


def _provided_log_for_execution(logs: str | None, execution_id: str | None) -> str:
    if not logs:
        return ""
    if execution_id is None:
        return logs
    markers = list(
        re.finditer(r"(?:execution[_ ]id|exec[_ ]id)\s*[:=]\s*['\"]?([\w-]+)", logs, re.IGNORECASE)
    )
    if not markers:
        return logs
    chunks = []
    for index, marker in enumerate(markers):
        if marker.group(1) == execution_id:
            end = markers[index + 1].start() if index + 1 < len(markers) else len(logs)
            chunks.append(logs[marker.start():end])
    return "\n".join(chunks)


def _collect_findings(
    entry: dict[str, Any],
    supplied_report: dict[str, Any] | None,
    log_sources: list[tuple[str, str]],
    selected_execution_id: str | None,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    def add(code: str, severity: str, message: str, source: str, evidence: Any) -> None:
        findings.append({
            "code": code,
            "severity": severity,
            "message": message,
            "source": source,
            "execution_id": selected_execution_id,
            "evidence": evidence,
        })

    summary = entry.get("status_summary") or {}
    events = entry.get("execution_events") or []
    reached_events = [
        event for event in events
        if isinstance(event, dict) and event.get("event") == "WAYPOINT_REACHED"
    ]
    defined = summary.get("waypoints_defined")
    total = len(defined) if isinstance(defined, list) else summary.get("total_waypoints")
    if total is None and supplied_report:
        total = supplied_report.get("total_planned_waypoints")
    reported_reached = entry.get("waypoints_reached")
    if not isinstance(reported_reached, list) and supplied_report:
        reported_reached = supplied_report.get("waypoints_reached")
    reached_indices = {
        (event.get("data") or {}).get("wp_index")
        for event in reached_events
        if (event.get("data") or {}).get("wp_index") is not None
    }
    if isinstance(reported_reached, list):
        reached_indices.update(
            waypoint.get("wp_index")
            for waypoint in reported_reached
            if isinstance(waypoint, dict) and waypoint.get("wp_index") is not None
        )
    if isinstance(total, int):
        planned_indices = [
            waypoint.get("wp_index", index) if isinstance(waypoint, dict) else index
            for index, waypoint in enumerate(defined)
        ] if isinstance(defined, list) else list(range(total))
        reported_count = entry.get("waypoints_reached_count")
        if reported_count is None and supplied_report:
            reported_count = supplied_report.get("waypoints_reached_count")
        reached_count = (
            len(reached_indices)
            if reached_indices
            else reported_count if isinstance(reported_count, int)
            else len(reported_reached) if isinstance(reported_reached, list)
            else len(reached_events)
        )
        missing = [index for index in planned_indices if index not in reached_indices] if reached_indices else []
        missed_count = max(0, total - reached_count)
        if missed_count:
            message = f"{missed_count} of {total} planned waypoints were not observed as reached."
            evidence = {"planned": total, "reached": reached_count, "missing_indices": missing}
            add("MISSED_WAYPOINTS", "warning", message, "selected_execution_report", evidence)

    for event in events:
        if not isinstance(event, dict):
            continue
        name = str(event.get("event", "")).upper()
        data = event.get("data") or {}
        if (
            "ALTITUDE" in name
            and any(word in name for word in ("VIOLATION", "LIMIT", "BREACH"))
        ) or data.get("altitude_violation") or data.get("altitude_limit_violated"):
            add("ALTITUDE_VIOLATION", "error", "Execution report records an altitude violation.", "selected_execution_report", event)

    battery_values: list[Any] = []

    def find_batteries(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "battery_percentage":
                    battery_values.append(child)
                find_batteries(child)
        elif isinstance(value, list):
            for child in value:
                find_batteries(child)

    find_batteries(entry)
    battery = battery_values[-1] if battery_values else None
    if battery is not None:
        try:
            percentage = float(battery)
        except (TypeError, ValueError):
            percentage = None
        if percentage is not None and percentage <= 0:
            add("BATTERY_DEPLETION", "error", f"Reported remaining battery is {percentage:g}%.", "selected_execution_report", battery)
        elif percentage is not None and percentage <= 20:
            add("LOW_BATTERY", "warning", f"Reported remaining battery is {percentage:g}%.", "selected_execution_report", battery)

    report_findings = (supplied_report or {}).get("diagnostic_findings", [])
    for finding in report_findings if isinstance(report_findings, list) else []:
        if isinstance(finding, dict):
            add(
                str(finding.get("code", "USER_REPORTED_DIAGNOSTIC")),
                str(finding.get("severity", "warning")),
                str(finding.get("message", "User-supplied report contains a diagnostic finding.")),
                "user_supplied_report",
                finding,
            )

    for source, text in log_sources:
        if re.search(r"Traceback \(most recent call last\):", text):
            add(
                "SCRIPT_TRACEBACK",
                "error",
                "A Python traceback was found in logs for the selected execution.",
                source,
                "\n".join(text.strip().splitlines()[-12:]),
            )
        altitude_hit = re.search(r"altitude.{0,40}(?:violation|exceed|below|above|breach)|(?:violation|exceed|below|above|breach).{0,40}altitude", text, re.IGNORECASE)
        if altitude_hit:
            add("ALTITUDE_VIOLATION", "error", "Logs describe an altitude violation.", source, altitude_hit.group(0))
        battery_hit = re.search(r"(?:battery|remaining charge).{0,40}(?:deplet|critical|low|\b[0-9]{1,2}%\b)|(?:deplet|critical|low).{0,40}battery", text, re.IGNORECASE)
        if battery_hit:
            add("BATTERY_DEPLETION", "error", "Logs indicate depleted or critical battery.", source, battery_hit.group(0))

    return findings


def inspect_mission_run_evidence(
    project_id: str,
    mission_id: str,
    execution_id: str | None = None,
    user_supplied_logs: str | None = None,
    user_supplied_report: dict[str, Any] | None = None,
    client_data_dir: Path | None = None,
) -> dict[str, Any]:
    """Inspect one execution's report, media, and diagnostics from its exact mission directory."""
    data_dir = Path(client_data_dir) if client_data_dir is not None else CLIENT_DATA_DIR
    data_root = data_dir.resolve()
    mission_dir = (data_root / f"prj-{project_id}" / f"mis-{mission_id}").resolve()
    if not mission_dir.is_relative_to(data_root):
        raise ValueError("Project and mission IDs must resolve within the ClientData directory.")
    selected_report: dict[str, Any] | None = None
    selected_entry: dict[str, Any] | None = None
    selected_path: Path | None = None
    report_evidence = "MISSING"
    accepted_user_report: dict[str, Any] | None = None

    if user_supplied_report is not None and _mission_matches(user_supplied_report, mission_id):
        candidate_entry = _select_entry(user_supplied_report, execution_id)
        candidate_id = str(candidate_entry.get("execution_id", "")) if candidate_entry else None
        if candidate_entry is not None and (execution_id is None or candidate_id == execution_id):
            selected_report = user_supplied_report
            selected_entry = candidate_entry
            accepted_user_report = user_supplied_report
            report_evidence = (
                "SYNTHETIC"
                if is_synthetic_report(
                    {**user_supplied_report, "execution_report": [candidate_entry]},
                    execution_id=candidate_id,
                )
                else "USER_PROVIDED"
            )

    if selected_entry is None:
        found = _find_report(mission_dir, mission_id, execution_id, synthetic=None)
        if found:
            selected_path, selected_report, selected_entry = found
            entry_id = str(selected_entry.get("execution_id", "")) or None
            report_evidence = (
                "SYNTHETIC"
                if is_synthetic_report(selected_report, selected_path, entry_id)
                else "NATIVE_CORRELATED"
            )

    selected_id = execution_id
    if selected_id is None and selected_entry is not None and selected_entry.get("execution_id") is not None:
        selected_id = str(selected_entry["execution_id"])
    timestamp = _entry_timestamp(selected_entry) if selected_entry else None
    if timestamp is None and selected_report:
        timestamp = selected_report.get("timestamp")

    def inventory(folder: str) -> tuple[list[str], list[str]]:
        directory = mission_dir / "media" / folder
        if not directory.exists():
            return [], []
        files = sorted(path for path in directory.rglob("*") if path.is_file())
        correlated: list[str] = []
        unassigned: list[str] = []
        for path in files:
            relative = path.relative_to(mission_dir).as_posix()
            if selected_id is not None and selected_id in relative:
                correlated.append(relative)
            else:
                unassigned.append(relative)
        return correlated, unassigned

    captures, unassigned_captures = inventory("captures")
    recordings, unassigned_recordings = inventory("recordings")
    log_sources: list[tuple[str, str]] = []
    for path, text in _correlated_log_files(mission_dir / "logs", selected_id):
        log_sources.append((f"local_log:{path.relative_to(mission_dir).as_posix()}", text))
    supplied_text = _provided_log_for_execution(user_supplied_logs, selected_id)
    if supplied_text:
        log_sources.append(("user_supplied_logs", supplied_text))

    diagnostics = _collect_findings(
        selected_entry or {}, accepted_user_report, log_sources, selected_id
    )
    if user_supplied_report is not None and accepted_user_report is None:
        diagnostics.append({
            "code": "USER_REPORT_MISMATCH",
            "severity": "warning",
            "message": "The supplied report does not match the requested mission or execution.",
            "source": "user_supplied_report",
            "execution_id": selected_id,
            "evidence": {
                "requested_mission_id": mission_id,
                "requested_execution_id": execution_id,
            },
        })

    return {
        "project_id": project_id,
        "mission_id": mission_id,
        "mission_directory": str(mission_dir),
        "selected_execution_id": selected_id,
        "timestamp": timestamp,
        "report_evidence": report_evidence,
        "report_file": selected_path.name if selected_path else None,
        "media_inventory": {
            "captures": captures,
            "recordings": recordings,
            "unassigned_captures": unassigned_captures,
            "unassigned_recordings": unassigned_recordings,
            "mission_captures": sorted([*captures, *unassigned_captures]),
            "mission_recordings": sorted([*recordings, *unassigned_recordings]),
        },
        "diagnostic_findings": diagnostics,
    }
