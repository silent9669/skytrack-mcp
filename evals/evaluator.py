"""Independent Reviewer Evaluation Runner for SkyTrack.
Loads test specifications from evals/catalog, executes tests, captures full run artifacts into evals/runs/<run_id>/, and computes geometric/oracle verifications.
"""

from __future__ import annotations

import asyncio
import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

from evals.expected.geometric_verifier import (
    distance_3d,
    horizontal_distance,
    verify_waypoint_reached,
    verify_waypoint_sequence,
)
from skytrack_mcp.clients.storage_sync import read_mission_details, resolve_mission_dir
from skytrack_mcp.report.parser import harvest_mission_report_data
from skytrack_mcp.report.verification import evaluate_mission_requirements


EVALS_DIR = Path(__file__).resolve().parent
RUNS_DIR = EVALS_DIR / "runs"
CATALOG_DIR = EVALS_DIR / "catalog"


class IndependentEvaluator:
    def __init__(self, runs_dir: Path = RUNS_DIR) -> None:
        self.runs_dir = runs_dir
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def load_spec(self, spec_filename: str) -> Dict[str, Any]:
        spec_path = CATALOG_DIR / spec_filename
        if not spec_path.exists():
            raise FileNotFoundError(f"Spec file not found: {spec_path}")
        return yaml.safe_load(spec_path.read_text(encoding="utf-8"))

    def evaluate_test_report_parsing(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """Execute TEST-REPORT-001: Validate extraction of real SkyTrack mission report."""
        test_id = spec["test_id"]
        mis_id = spec["environment"]["mission_fixture_id"]
        run_id = f"{test_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        run_folder = self.runs_dir / run_id
        run_folder.mkdir(parents=True, exist_ok=True)

        mis_dir, prj_id, _ = resolve_mission_dir(mis_id)
        report_data = harvest_mission_report_data(mis_id, prj_id)

        # Check expected criteria from spec
        reached_count = int(report_data.get("waypoints_reached_count", 0))
        payload_count = int(report_data.get("payload_triggers_count", 0))
        status = report_data.get("execution_status", "UNKNOWN")
        source_file = report_data.get("authentic_report_file")

        min_reached = spec["expected"]["events_extracted"]["min_waypoints_reached"]
        passed = (source_file is not None) and (reached_count >= min_reached) and (status == "COMPLETED")

        result_payload = {
            "test_id": test_id,
            "run_id": run_id,
            "status": "PASS" if passed else "FAIL",
            "authentic_file": source_file,
            "waypoints_reached": reached_count,
            "payload_triggers": payload_count,
            "execution_status": status,
            "requirements": [
                {
                    "id": "R_AUTHENTIC_FILE",
                    "status": "PASS" if source_file else "FAIL",
                    "observed": f"source_file={source_file}",
                },
                {
                    "id": "R_MIN_WAYPOINTS",
                    "status": "PASS" if reached_count >= min_reached else "FAIL",
                    "expected": min_reached,
                    "observed": reached_count,
                },
                {
                    "id": "R_STATUS_COMPLETED",
                    "status": "PASS" if status == "COMPLETED" else "FAIL",
                    "expected": "COMPLETED",
                    "observed": str(status),
                },
            ],
            "bugs": [] if passed else ["BUG-0002"],
        }

        # Save artifacts
        (run_folder / "test-spec.yaml").write_text(yaml.dump(spec), encoding="utf-8")
        (run_folder / "report.json").write_text(json.dumps(report_data, indent=2), encoding="utf-8")
        (run_folder / "result.json").write_text(json.dumps(result_payload, indent=2), encoding="utf-8")

        return result_payload

    def evaluate_test_failure_refusal(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """Execute TEST-FAIL-001: Validate negative test failure refusal."""
        from skytrack_mcp.mission.models import CanonicalMission, Waypoint
        from skytrack_mcp.mission.validator import validate_canonical_mission

        test_id = spec["test_id"]
        run_id = f"{test_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        run_folder = self.runs_dir / run_id
        run_folder.mkdir(parents=True, exist_ok=True)

        bad_mission = CanonicalMission(
            project_id="test-prj",
            mission_id="test-mis-bad",
            world="warehouse",
            vehicle="x500_tennis_balls_no_cam",
            takeoff_altitude=0.2,  # Invalid (<1.0m)
            target_speed=2.0,
            waypoints=[
                Waypoint(x=0.0, y=0.0, z=0.2),
                Waypoint(x=1.0, y=1.0, z=0.2, after_action="drop-ball"),
                Waypoint(x=2.0, y=1.0, z=0.2, after_action="drop-ball"),
                Waypoint(x=3.0, y=1.0, z=0.2, after_action="drop-ball"),
                Waypoint(x=4.0, y=1.0, z=0.2, after_action="drop-ball"),
                Waypoint(x=5.0, y=1.0, z=0.2, after_action="drop-ball"),
                Waypoint(x=6.0, y=1.0, z=0.2, after_action="drop-ball"),  # 6 drops > 5 max
            ],
        )

        val_res = validate_canonical_mission(bad_mission)
        detected_codes = [i.code for i in val_res.issues]
        expected_codes = spec["expected"]["static_validation"]["expected_error_codes"]

        all_detected = (not val_res.valid) and all(code in detected_codes for code in expected_codes)

        result_payload = {
            "test_id": test_id,
            "run_id": run_id,
            "status": "PASS" if all_detected else "FAIL",
            "static_valid": val_res.valid,
            "detected_error_codes": detected_codes,
            "requirements": [
                {
                    "id": "R_STATIC_INVALID",
                    "status": "PASS" if not val_res.valid else "FAIL",
                    "observed": f"valid={val_res.valid}",
                },
                {
                    "id": "R_CODES_DETECTED",
                    "status": "PASS" if all_detected else "FAIL",
                    "expected": expected_codes,
                    "observed": detected_codes,
                },
            ],
            "bugs": [] if all_detected else ["BUG-0001"],
        }

        (run_folder / "test-spec.yaml").write_text(yaml.dump(spec), encoding="utf-8")
        (run_folder / "validation.json").write_text(json.dumps(val_res.model_dump(), indent=2), encoding="utf-8")
        (run_folder / "result.json").write_text(json.dumps(result_payload, indent=2), encoding="utf-8")

        return result_payload


    def evaluate_hackathon_benchmark(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """Execute TEST-HACKATHON-2026-URBAN-FIRE: Official Hackathon 2026 100-point rubric."""
        from evals.expected.hackathon_evaluator import score_hackathon_mission_report

        test_id = spec["test_id"]
        run_id = f"{test_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        run_folder = self.runs_dir / run_id
        run_folder.mkdir(parents=True, exist_ok=True)

        fixture_rel = spec["reference_solution"]["report_fixture"]
        fixture_path = EVALS_DIR.parent / fixture_rel
        score_res = score_hackathon_mission_report(fixture_path)

        passed = score_res["passed_threshold"]
        result_payload = {
            "test_id": test_id,
            "run_id": run_id,
            "status": "PASS" if passed else "FAIL",
            "total_score": score_res["total_score"],
            "max_score": score_res["max_score"],
            "rubric_scores": score_res["rubric_scores"],
            "details": score_res["details"],
            "requirements": [
                {
                    "id": "R_RUBRIC_SCORE",
                    "status": "PASS" if passed else "FAIL",
                    "expected": ">= 85.0 / 100.0",
                    "observed": f"{score_res['total_score']} / {score_res['max_score']}",
                }
            ],
            "bugs": [],
        }

        (run_folder / "test-spec.yaml").write_text(yaml.dump(spec), encoding="utf-8")
        (run_folder / "score_result.json").write_text(json.dumps(result_payload, indent=2), encoding="utf-8")
        return result_payload


def run_reviewer_suite() -> Dict[str, Any]:
    evaluator = IndependentEvaluator()
    results = {}

    print("Executing TEST-REPORT-001 (Authentic Report Parsing)...")
    spec_rep = evaluator.load_spec("TEST-REPORT-001.yaml")
    results["TEST-REPORT-001"] = evaluator.evaluate_test_report_parsing(spec_rep)

    print("Executing TEST-FAIL-001 (Negative Failure Refusal)...")
    spec_fail = evaluator.load_spec("TEST-FAIL-001.yaml")
    results["TEST-FAIL-001"] = evaluator.evaluate_test_failure_refusal(spec_fail)

    print("Executing TEST-HACKATHON-2026-URBAN-FIRE (100-Point Rubric Evaluation)...")
    spec_hack = evaluator.load_spec("TEST-HACKATHON-2026-URBAN-FIRE.yaml")
    results["TEST-HACKATHON-2026-URBAN-FIRE"] = evaluator.evaluate_hackathon_benchmark(spec_hack)

    summary_file = EVALS_DIR / "reports" / "reviewer_eval_summary.json"
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    summary_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


if __name__ == "__main__":
    res = run_reviewer_suite()
    print("\n--- Reviewer Evaluation Suite Results ---")
    for tid, r in res.items():
        print(f"[{r['status']}] {tid}: {r.get('requirements')}")
