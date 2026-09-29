# SkyTrack MCP Release Evidence Integrity Design

**Date:** 2026-09-27
**Status:** Draft for user review

## 1. Purpose

Correct two independently confirmed release-readiness gaps in the existing SkyTrack MCP flows:

1. World discovery and SDF inspection can prefer packaged files over the running Gazebo container, or hide runtime-only worlds, without indicating which source supplied the geometry.
2. Mission report verification can present mission-wide media and harvest-time telemetry as evidence for a selected execution, including fabricated defaults when observations are absent.

The changes are intended to make evidence provenance visible and to preserve `UNKNOWN` when the selected execution cannot be verified. They do not diagnose the PX4/Gazebo startup failure or perform any live simulator operation.

## 2. Scope and constraints

### In scope

- Runtime-first SDF resolution, union world discovery, and explicit source/match metadata.
- Selected-execution identity in harvested reports.
- Neutral handling of absent execution status and telemetry fields.
- Separation of current telemetry snapshots and mission-wide media inventory from execution-linked evidence.
- Fail-closed capture, payload, battery-margin, and overall-verdict behavior.
- Regression tests for these behaviors using fixtures and mocks only.

### Out of scope

- Changing mission serialization or GCS action translation, including relayed action-loss findings; those require separate scope and design approval.
- Reworking collision-freedom evidence contracts or adding cryptographic attestation to native reports.
- Adding a new telemetry or capture producer, starting/restarting containers, dispatching a mission, merging/tagging, or releasing.
- Treating the suspected PX4 model-name mismatch as a confirmed simulator root cause.

### Safety and release constraints

All verification is local and non-live. No flight or simulator lifecycle tool is to be invoked for these changes. PR #1 remains draft. No merge, tag, or release is permitted without passing CI and mission-linked native execution evidence; this work itself does not produce that flight evidence.

A first release may be a stable MVP; complete feature parity with the SkyTrack app is not a prerequisite. **Proposed MVP boundary for review:** include project listing; mission read/create for an existing project; authoring a new visual route; world and vehicle inspection; static validation and collision checks only when geometry is complete; and report reading that preserves `UNKNOWN`. Exclude generic edits to existing missions, unsupported action types, and live dispatch until the safety and evidence gates below are met. Before a release-readiness claim, provide a read-only capability matrix mapping app workflows to MCP tools and underlying API behavior, with covered, partial, unsupported, and lossy paths called out. Define and test the promised MVP workflows, and document unsupported capabilities rather than implying parity.

A read-only static review confirmed adjacent lossy paths outside this spec: canonical serialization rebuilds a plan from waypoints and their `after_action` fields rather than preserving `raw_actions`, while `patch_mission` always saves that serialization; and standalone GCS translation has no mapping for some UI actions (including snapshot, video-recording, and spray start/stop types). These findings confirm local code-path loss, not the downstream GCS or live-flight effect. Until separately fixed and covered by regression tests, an MVP should exclude generic edits that round-trip existing missions through this serializer and should not advertise unsupported standalone actions as executable. Documentation alone is insufficient while those MCP tools remain callable: before release, unsafe patches must be preserved correctly or rejected before saving, and unsupported actions must be rejected before submitting an incomplete GCS payload. Whether to implement those safeguards or exclude/disable affected tool paths requires a separate approved design. This spec does not fix those paths.

The current wait-and-execute helper checks telemetry connectivity and polls for landing, but does not enforce active world/vehicle match, grounded/disarmed state, or adequate battery, and does not return the dispatch execution ID. Therefore live dispatch is excluded from the proposed first MVP until those safety checks, execution-ID linkage, and mission-linked native evidence are addressed through a separate approved design. Because the dispatch tools remain callable, documentation-only exclusion is not a sufficient safety control: the MVP release must disable or guard those entry points until the required preflight is enforced. This is a repository-code finding; no live dispatch or backend behavior was tested.

## 3. SDF discovery and source provenance

### Discovery

`list_gazebo_worlds()` will return the deduplicated packaged world names plus names found in the running Gazebo container. If the container is not running, Docker is unavailable, or runtime discovery fails, packaged names remain available as the offline fallback. Runtime-only names must not be hidden merely because packaged SDFs exist.

### Selection and fallback

For a requested world, try the SDF in the running Gazebo container before a same-named packaged copy. If the runtime container is unavailable or the requested runtime SDF cannot be read, fall back to the packaged file. If neither source contains it, preserve the existing not-found error behavior.

### Provenance fields

Inspection and parsed-world results will expose:

- `sdf_source`: `runtime_container` or `packaged_cache`.
- `runtime_world_match`: if `sdf_source` is `packaged_cache`, the value is always `null`, regardless of runtime identity. If `sdf_source` is `runtime_container`, the value is `true` when at least one runtime identity is available and all available Gazebo/PX4 world identities equal the requested world; `false` if any available identity disagrees; otherwise `null`.

The field describes a match of reported runtime identity and selected source. It does not assert that Gazebo loaded byte-for-byte identical SDF contents if a file changed after process startup. A packaged fallback is never labeled as runtime geometry.

## 4. Report evidence provenance

### Selected execution and status

The harvested report will include the resolved `execution_id`, whether explicitly requested or selected by the existing latest-entry behavior. Resolve execution status from that selected entry's own status or status summary. Use top-level `execution_metadata.status` only if the report format explicitly correlates it to the selected execution; otherwise represent selected status as `UNKNOWN`, never infer `COMPLETED`. Top-level duration, world, and vehicle fields likewise are not selected-execution evidence unless explicitly correlated.

Native-report selection remains in place. Classification must apply to the selected execution entry, not only to the first entry in a multi-execution file. A selected entry is eligible for execution evidence only if it is not marked synthetic by the existing filename, metadata, or entry-level signature checks; otherwise its evidence is unavailable and verification is `UNKNOWN`. The `authentic` label continues to mean the project's current file/record matching heuristic, not cryptographic attestation.

### Telemetry snapshot versus execution evidence

Harvest-time MAVLink telemetry remains available as a current snapshot and is labeled as such in structured and Markdown report output. Add a snapshot provenance label and an `observed_at` value only when supplied by the telemetry source; the report-generation timestamp is not a substitute. Snapshot values are not execution-end evidence unless the source includes an explicit correlation to the selected execution.

Missing telemetry fields remain unavailable: battery is `null`; landed state and flight mode are `UNKNOWN`; armed state is `null`. Execution status must not synthesize `100%`, `ON_GROUND`, `HOLD`, or disarmed state.

`battery_margin` verification will use only a finite battery value in the inclusive range 0–100 that is explicitly tied to the selected execution's terminal evidence. Preserve the existing comparison: a correlated, valid value greater than or equal to the requirement's configured minimum passes; a lower value fails. Preserve the existing configured/default minimum; this design changes evidence provenance, not threshold semantics. The current parser has no confirmed source for an execution-linked terminal sample, so the requirement remains `UNKNOWN` until such evidence exists. A current live battery snapshot may still be shown separately.

### Capture inventory versus selected-execution captures

For compatibility, `media_output.captures` and `media_output.captures_count` remain a mission-folder inventory and are explicitly not execution evidence. Add a nullable execution-scoped capture count/list derived only from recognized capture events in the selected non-synthetic execution that identify corresponding files.

Resolve each event's file reference beneath the mission's capture directory; reject absolute paths and paths that escape that directory. Count only distinct, regular, non-empty files with a supported image extension and matching format signature. This dependency-free signature check rejects empty files and obvious non-images; it is not full image decoding or cryptographic integrity validation. Deduplicate repeated references to the same normalized file.

The verifier will use only execution-scoped capture evidence. Sufficient valid linked artifacts can establish `PASS`; ignore invalid, stale, or unlinked files when counting. If the valid linked count is below the requirement, return `UNKNOWN` unless the selected execution is accompanied by a completeness contract. The current report format/parser has no such contract, so this scope does not invent a completeness field or claim capture shortfall `FAIL`; adding a producer contract is deferred to a separately approved design. An empty event list alone is not proof of zero captures, and mission-folder inventory is never a fallback. No producer-side manifest or new image-decoding dependency is added in this scope.

### Payload events

Payload verification requires events from the selected non-synthetic execution. Sufficient distinct qualifying events can establish `PASS`. An absent report, absent event stream, or incomplete event record is `UNKNOWN`, not an inferred zero or verified shortfall. The current report format/parser has no recognized event-completeness contract; therefore this scope does not invent a completeness field or claim payload shortfall `FAIL`. A future producer contract establishing completeness requires a separate approved design. An empty event list alone does not establish completeness. Direct helper dictionaries with counts but no authentic execution provenance cannot establish `PASS`.

When both `PAYLOAD_TRIGGER` and `BALL_DROP` events describe a physical drop, correlate them using their shared event/action identifier when present and count that physical action once. If available data cannot establish whether records overlap or represent distinct drops, return `UNKNOWN`. This scope does not add drop-location tolerance or change producer-side event formats.

### Limitations of the reviewed fixture and current parser

The reviewed evaluation fixture, `evals/fixtures/hackathon-2026/sample-answer-report.json`, has no event-completeness marker, capture event/file reference, or execution-terminal battery sample. Its `BALL_DROP` event contains coordinates and a timestamp but no action identifier. It can exercise conservative `UNKNOWN` behavior for absent capture/battery evidence and an unproven payload shortfall; it cannot demonstrate capture or battery `PASS`, and it must not be presented as native integration or flight evidence. Positive capture verification is possible only for a selected native entry that actually contains a recognized file reference and a corresponding artifact. The current parser has no execution-correlated terminal battery source, so battery-margin requirements remain `UNKNOWN` for current output. No producer-side change is included here; resolving that evidence gap requires a separately reviewed design.

The parser does not currently establish capture- or payload-stream completeness, and no formal raw execution-report schema defining such a signal was found during this review. Do not infer completeness from `COMPLETED`/`Succeeded`, a `MISSION_END` event, an empty event list, or the presence of some events. Under the current format, insufficient capture or payload evidence is `UNKNOWN`; `FAIL` for either shortfall is deferred until a producer contract is separately designed and approved. This scope does not add or assume an unvalidated completeness field.

### Overall verdict

- `FAIL` if any mandatory requirement is a verified `FAIL`, or if the requirements list is empty (preserving current empty-input behavior).
- `UNKNOWN` if there is no mandatory verified failure but a mandatory requirement is `UNKNOWN`, or if the input contains only optional requirements and therefore has no mandatory evidence basis.
- `PASS` only when at least one mandatory requirement exists and every mandatory requirement is `PASS`.
- Optional item verdicts remain visible but do not block an otherwise supported mandatory `PASS`.

## 5. Compatibility

Preserve existing tool signatures and report fields where practical. Add the selected execution ID and separate nullable execution-evidence fields rather than repurposing mission-wide inventory fields. Keep existing current telemetry values available but label their scope; verification must not use uncorrelated snapshot fields as execution evidence. Any changed summary text must make clear that the aggregate verdict is based on mandatory requirements, while individual optional results remain itemized.

## 6. Verification plan

All tests use temporary directories, fixtures, and mocks; none start containers or call live flight endpoints.

### SDF tests

- Same-name live SDF takes precedence over packaged SDF and reports `runtime_container`.
- Runtime-only world names appear in the union.
- Missing/stopped runtime falls back to packaged discovery and SDF content with `packaged_cache` provenance.
- Missing SDF in both sources preserves the not-found error.
- Runtime identity mismatch is `false`; unavailable identity or packaged fallback is `null`. A `true` result means reported world identities match the requested world, not byte-for-byte SDF identity.

### Report tests

- A multi-entry report whose top-level status/world/vehicle/duration is not correlated to the selected entry cannot supply those selected-execution facts. Missing selected-entry status remains `UNKNOWN`; missing battery/landed/flight/armed telemetry is not synthesized. Snapshot provenance is separate from report generation time, and `observed_at` is emitted only when supplied by telemetry.
- Selected execution ID is included in both explicit-ID and latest-entry selection. A synthetic marker on a later selected entry prevents that entry from being treated as authentic even when an earlier entry appears native.
- Current telemetry snapshot remains displayable but cannot satisfy `battery_margin`; only selected-execution terminal evidence can pass/fail it. Boundary tests cover equal-threshold pass, below-threshold fail, and invalid/non-finite/out-of-range values yielding `UNKNOWN`.
- Stale or unlinked mission-folder captures remain inventory only. Linked artifacts count only for their matching execution; absolute/traversing paths, empty files, unsupported extensions, and mismatched image signatures are ignored. Duplicate references count once. Enough valid linked artifacts can pass; below-threshold or absent evidence from the current format yields `UNKNOWN`. Tests do not claim full image decoding or assert shortfall `FAIL` without an approved producer completeness contract.
- Absent or incomplete payload evidence yields `UNKNOWN`; enough distinct linked native events can pass; a below-threshold count in the current format remains `UNKNOWN`. Mixed event types are deduplicated by shared action ID or yield `UNKNOWN` when overlap cannot be resolved. Do not invent completeness fields in test fixtures.
- Aggregate verdict matrix covers mandatory pass/fail/unknown, optional fail/unknown, optional-only input, and empty input.

### Release checks

Run targeted report and world tests, the full non-live test suite, critical Ruff checks, package build, and installed-wheel smoke test. Report exact commands and outcomes. Keep the PR draft, and do not claim native flight evidence from fixtures or tests. Separately publish the read-only app-to-MCP capability matrix before making an MVP release-readiness claim; it must distinguish verified behavior from unsupported, partial, lossy, and unverified paths. A green test suite alone does not close the reported mission-serialization/GCS action-loss questions or satisfy the native-evidence gate.

## 7. Acceptance criteria

1. World discovery includes runtime-only worlds and packaged fallback remains usable offline.
2. Same-name runtime SDFs are preferred, and response metadata does not misrepresent packaged geometry as runtime geometry.
3. Missing or uncorrelated telemetry and media cannot produce execution-evidence `PASS` results.
4. `UNKNOWN` remains distinct from verified `FAIL` in item and overall results under the rules above.
5. Regression tests and release checks pass without starting the simulator or dispatching a mission.
