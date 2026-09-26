"""Automated Evaluation Harness for SkyTrack Mission Studio Agent.
Executes EVAL 1 through EVAL 5 and records comprehensive evidence into docs/eval-results.md.
"""

from __future__ import annotations

import asyncio
import datetime
import json
from pathlib import Path
from typing import Any, Callable, Dict, List

from skytrack_mcp.report.verification import MissionVerificationMatrix, VerificationStatus


class EvalResult:
    def __init__(
        self,
        eval_id: str,
        title: str,
        assignment: str,
        requirements: List[Dict[str, Any]],
        initial_state: Dict[str, Any],
        generated_mission: Dict[str, Any],
        validation_result: Dict[str, Any],
        simulation_result: Dict[str, Any],
        report: Dict[str, Any],
        verification_matrix: MissionVerificationMatrix,
    ) -> None:
        self.eval_id = eval_id
        self.title = title
        self.assignment = assignment
        self.requirements = requirements
        self.initial_state = initial_state
        self.generated_mission = generated_mission
        self.validation_result = validation_result
        self.simulation_result = simulation_result
        self.report = report
        self.verification_matrix = verification_matrix
        self.success = verification_matrix.overall_status == VerificationStatus.PASS

    def to_markdown(self) -> str:
        matrix_rows = []
        for item in self.verification_matrix.items:
            matrix_rows.append(
                f"| {item.requirement_name} | {item.expected} | {item.observed} | `{item.evidence}` | **{item.status.value}** | {item.confidence} |"
            )
        matrix_table = (
            "| Requirement | Expected | Observed | Evidence | Status | Confidence |\n"
            "|---|---|---|---|---|---|\n" + "\n".join(matrix_rows)
        )

        return f"""## {self.eval_id}: {self.title}

- **Status:** **{'PASSED (100% Verified)' if self.success else 'FAILED'}**
- **Assignment:** "{self.assignment}"
- **Simulation World:** `{self.generated_mission.get('world')}`
- **Vehicle Model:** `{self.generated_mission.get('vehicle')}`
- **Waypoints Planned:** {len(self.generated_mission.get('waypoints', []))}

### 1. Requirements & Static Validation
- **Static Validation Valid:** `{self.validation_result.get('valid')}`
- **Detected Issues Count:** {len(self.validation_result.get('issues', []))}

### 2. Simulation Execution
- **Execution Status:** `{self.simulation_result.get('status')}`
- **Reported Outcome:** `{self.simulation_result.get('response', {}).get('message', 'Executed')}`

### 3. Requirement-by-Requirement Verification Matrix
{matrix_table}

---
"""


class EvalHarness:
    def __init__(self, output_markdown_path: Path) -> None:
        self.output_path = Path(output_markdown_path)
        self.results: List[EvalResult] = []

    def record_result(self, result: EvalResult) -> None:
        self.results.append(result)

    def write_report(self) -> None:
        now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        passed_count = sum(1 for r in self.results if r.success)
        total_count = len(self.results)

        header = f"""# SkyTrack Autonomous Agent — End-to-End Evaluation Results

**Test Date:** `{now_str}`
**Evaluation Suite:** 5 Mandatory Scenarios (EVAL 1 - EVAL 5)
**Overall Result:** **{passed_count}/{total_count} Evaluated Missions PASSED**

---

"""
        body = "\n".join(r.to_markdown() for r in self.results)
        self.output_path.write_text(header + body, encoding="utf-8")
