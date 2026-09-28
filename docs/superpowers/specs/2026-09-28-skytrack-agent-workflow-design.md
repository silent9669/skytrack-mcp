# SkyTrack Agent Workflow and Distributable MCP Design

**Date:** 2026-09-28

**Status:** Independent reviewer approved; awaiting user review; not approved for implementation
**Supersedes:** `2026-09-28-skytrack-app-bridge-design.md` and its pending implementation plan `2026-09-28-skytrack-mission-authoring.md`. Those documents remain as historical records and must not be implemented as-is.

## Purpose

Provide a distributable, cross-platform SkyTrack MCP and a globally installable Claude Code plugin that lets coding agents work on the exact existing SkyTrack mission selected by the user: inspect it, author or revise Plan and Python Code representations, save and verify the result, read its native reports and media, and—only when the user explicitly requests debugging—diagnose a specific run and prepare the same mission for the user to rerun.

The user, not the agent, starts and operates every simulation. The MCP is not a flight-control product. It does not dispatch, pause, resume, start, stop, restart, recover, or observe an active simulation in the default distribution.

The same general-purpose MCP supports future SkyTrack assignments. Challenge-specific rules, including the 2026 semifinal, are optional rule packs rather than assumptions embedded in generic mission authoring or storage behavior.

## User-Approved Direction and Defaults

- One per-user Claude Code plugin installation should work across that user's projects on a machine. Claude Code receives the complete skill/plugin experience. OpenCode and Codex need the host-neutral MCP core in v1, configured through their own MCP settings.
- The MCP is installed and run locally alongside SkyTrack Desktop and the coding host on macOS or Linux. Mission storage and native reports remain in the user's App-managed workflow; selecting Cloud changes simulation compute, not the mission's authoring datastore.
- Prefer reliable App-owned files or interfaces. If they are insufficient, an experimental adapter to SkyTrack App internals is acceptable only with exact running-build verification, explicit unsupported status, fail-closed behavior, and no silent Local/Cloud fallback.
- Reuse the user's existing SkyTrack Desktop login/session. Do not ask for a second token, print credentials, persist credentials in MCP-owned files, or log authentication headers.
- Use sensible defaults. Ask only when a material permission or architecture decision is needed. Ask before creating a mission when the requested mission does not exist.
- The user runs simulations. The agent may debug only after an explicit user request describing the problem. After diagnosis, it may edit/save/read back/validate the same mission and hand it back for a user-operated rerun.
- Use the organizer-provided SkyTrack perception model and user-authorized post-processing; do not train, fine-tune, or replace the model. Prefer the App catalogue. If absent, the agent may install/configure it from a user-provided, hash-verified package through a documented/supported setup path before the user-run simulation. Cloud model execution is not proven by catalogue visibility alone; do not invent an upload path.

## Scope

### Goals

1. Install and run the MCP without a developer-specific absolute path on macOS and Linux.
2. Resolve the exact project and mission using project-name and mission-name context, disambiguating duplicates with stable IDs before mutation.
3. Read, author, and persist Plan and Code independently without lossy conversion, silent mode changes, or selecting a most-recent mission by default.
4. Save through the most reliable available App-managed file/API surface, retain a recoverable snapshot, read the artifact back, and compare its identity, mode, content, and revision/hash with the intended write.
5. Refresh the App after a save only through a verified reliable interface. Otherwise tell the user which exact mission/revision to reopen and how to verify it.
6. Read native reports, logs, images, and video for the selected mission and an exact run; accept user-supplied logs/reports/media when local native evidence is unavailable.
7. On explicit debug requests only, select the specified run or—when no run ID is supplied—the most recent run for the exact mission; state the selected run ID and timestamp, diagnose from its evidence, and prepare the same mission for the user's rerun.
8. Use configured coding-host models for reasoning. Keep AI that controls mission perception separate from the coding-host LLM and use only documented SkyTrack model/service contracts.
9. Represent uncertainty honestly: file saved, SDK-compatible, model available, App-compatible, user-run required, native evidence present, and contest eligibility are distinct statuses.
10. Package a global Claude Code plugin with a naturally discoverable SkyTrack skill, optional explicit `/skytrack` entrypoint, and no unsafe automatic hooks, while exposing the same host-neutral stdio MCP to OpenCode and Codex.

### Non-goals

- Starting, dispatching, controlling, pausing, resuming, monitoring, restarting, stopping, or recovering a simulation or vehicle.
- Requiring Docker, MAVLink, or a running simulator for mission-file authoring or report analysis.
- Creating a new mission without the user's approval.
- Using the MCP as a separate Cloud mission datastore or inventing Cloud model upload behavior.
- Reproducing a SkyTrack App internal API as an officially supported integration. Any internal adapter remains experimental and version-pinned.
- Automatically diagnosing every new report/run, transmitting media to a model outside the explicit debug flow, or publicly sharing missions/reports.
- Treating a sample stress detector as a disease detector, a static validator result as runtime proof, or Variant A evidence as proof of Variant B performance.
- Inspecting, importing, inferring, or testing against Variant B private maps, Ground Truth, seeds, evaluator internals, or other judge-only material.

## System Architecture

### Layer 1: Host-neutral Python MCP core

The existing Python stdio MCP remains the cross-host core. It owns typed tools for mission discovery/resolution, read/write/read-back, validation, report/media ingestion, and evidence analysis. It does not own a simulator control path in the default published tool surface.

The core discovers the local SkyTrack Desktop data root through supported environment/configuration and per-OS locations, rather than a hardcoded developer home. Storage paths are an implementation detail behind a platform adapter. OpenCode, Codex, and Claude Code launch the same packaged console entrypoint.

### Layer 2: Claude Code global plugin

A distributable Claude Code plugin bundles:

- a root plugin manifest and `.mcp.json` using a plugin-relative `${CLAUDE_PLUGIN_ROOT}` wrapper/entrypoint rather than a checkout-specific path;
- a naturally discoverable `skytrack` skill for relevant natural-language requests, with an optional `/skytrack` entrypoint for explicit invocation;
- no hooks in v1 unless a specific, material need is approved. Any future hook must be cheap, read-only, safe on every matching lifecycle event, and must not assume it runs only for SkyTrack tasks.

Plugin hooks and MCP startup are independent of skill invocation. Neither may trigger simulation, mission creation, implicit debugging, external sharing, or App runtime changes. The Claude plugin is installed at user scope; it does not require repository-local configuration in every project.

### Layer 3: SkyTrack App integration

Use this resolution order:

1. App-managed mission files and any reliable App-owned, externally callable interface verified for the installed build.
2. If those are insufficient, an experimental version-pinned adapter to private App internals, isolated behind a capability interface.
3. If the adapter cannot prove compatibility, identity, or operation semantics, fall back to a manual instruction for the user—not a different backend or inferred mission.

Before any App-facing read/write/refresh operation through the experimental adapter, verify both the running process build identity and installed bundle identity against an explicit supported-build profile. UI labels alone, the MCP's current hardcoded version, and caller-supplied `backend` arguments are not authoritative. Unknown or mismatched builds disable that capability. Keep runtime selection metadata separate from mission storage. Never change the App's Local/Cloud setting and never silently route to the other runtime.

App-version reporting currently conflicts across sources (the MCP reports 1.2.2, a bundle inspection reported 1.2.5, and the App UI screenshot reported 1.2.6). Version detection is therefore a required capability check, not a best-effort informational label.

The user's App session supplies authentication. The adapter must not bypass App permissions, create or export a separate credential, or expose secrets in tool results/logs. The current login/session identity and target project edit permission must be verified before writes. Filesystem writability or possession of a cached mission file is not proof of SkyTrack edit permission; if the supported file/API surface cannot verify authorization, allow reads only and report `PERMISSION_UNVERIFIED` until a verified App capability is available.

## Mission Identity and Authoring

### Exact target resolution

- Read the requested project and mission by their user-visible names, returning stable `project_id` and `mission_id` values.
- If names are duplicated or the App's selected item conflicts with the requested pair, show the candidates and ask the user to disambiguate before any write.
- If a named mission is missing, ask before creating it. Do not select the most recently modified mission or substitute a similar name.
- Any mutation, debug repair, report association, or read-back is scoped to the exact resolved project/mission pair. Editing an existing shared mission is allowed only when the App grants edit rights; if a judge/submission snapshot is immutable, do not bypass the lock or claim the submitted revision changed.

### Independent Plan and Code representations

- Plan mode preserves the complete raw `plan.json` and `mission.json` documents, including multiple sequences, standalone/attached actions, IDs, and unknown metadata. A transformation that cannot preserve the source shape must refuse before writing.
- Code mode preserves `script.py` exactly and maintains `mission.json` `codeMode=true`. Code saves must not flatten or replace the Plan representation. Plan edits must not remove or rewrite Code.
- The agent may choose or switch Plan/Code mode when the user's task requires it. Before switching, snapshot both representations and ensure the inactive representation can be preserved; set mode metadata consistently, read the App state back, and report the switch and any refresh requirement. If the conversion is lossy, permissions are unclear, or the App cannot preserve the inactive representation, stop and ask rather than silently destroy work.
- Each write is atomic or recoverable, keeps a pre-write snapshot, reports partial failures, and performs exact read-back before returning success. Read-back identity and content mismatch is a failed write.

### App refresh and handoff

Attempt refresh only via a supported and build-verified interface. If unavailable, return a clear user step: reopen the exact mission in SkyTrack Desktop and confirm the displayed project, mission, mode, and saved revision. A successful filesystem write alone is not evidence that the UI loaded it.

## SDK and AI Model Workflow

### Pinned public SDK reference

The public reference snapshot used for code generation and static compatibility checks is `GetSkyTrack/skytrack-autonomy-example` commit `bb0f5ba611c59cd68d32d1fe04b40765836a1b33`, not a moving `develop` branch. This is an examples/docs repository, not proof of the `local_planner` or `skytrack_autonomy` version installed in the user's App runtime. Track source-reference alignment separately from installed-runtime compatibility: probe the installed library/App build where accessible; otherwise report runtime compatibility as `UNKNOWN`. Keep the source commit and any installed version/build evidence in the MCP reference metadata.

Documented imports include `Detector` and `Sprayer` from `skytrack_autonomy`; `CameraSense`, `VideoRecorder`, `Snapshot`, and `boot_drone` from `local_planner`. Validation must check import provenance and mission wiring, not merely identifier/call names. The current MCP's Level 4 template does not actually wire a Detector despite advertising one; its Detector signature is a placeholder; and its current AST validator accepts the public contest example as `valid: true` without flagging the missing Detector/model operation. Those behaviors are not acceptable evidence of contest readiness.

### Separate coding model and vehicle model

- **Coding-host model:** the configured model used by Claude Code/OpenCode/Codex to inspect requirements, author code, and analyze user-authorized report/media evidence. The MCP does not add a new LLM credential or bypass the host's model/security settings.
- **SkyTrack perception model:** a model registered/available in the selected SkyTrack App simulation runtime. Its name, class list, artifact provenance/hash, expected input/output, runtime availability, and App build compatibility are reported separately from coding-host model configuration.

### Organizer-provided stress model

The public pinned contest package (manifest version `1.0.0`) declares ONNX detector `det-h2026-v26n-b-fp32-640`, input size 640×640, and the single class `stressed`. At the pinned repository commit, the verified ZIP SHA-256 is `18e86fda14a9d914aff7915c9c3da67b1a92103c92537c944bf2089f4f814f0e` and the ONNX SHA-256 is `6352161daca9e52ac6ef35916ef584062c8b8cb24c7915155ce6b21b910ee58f`. The repository root is Apache-2.0 but the package has no separate model notice, so model-weight redistribution rights are not inferred from the code license. Prefer the model already shown in the user's App catalogue/Plan AI Flow over a separate download/install.

The public Local package setup is documented in the contest README: the zip is placed in the persistent Local model volume and the mission registers the model in the detector catalogue before boot. If the model is absent, the agent may install/configure a verified user-provided package through this supported Local path when that is part of the user's task; verify its hash and catalogue entry before handing off for the user's run. Never download/install during flight or train/fine-tune/replace the organizer model. This does not prove Cloud model ingress or judge clean-runtime portability. Do not invent a Cloud upload path or claim Cloud availability from catalogue visibility. If Cloud runtime availability cannot be verified, report `MODEL_NOT_AVAILABLE`/`UNKNOWN` for that runtime and continue with supported authoring or manual setup guidance.

### Code Mode perception path

For a Code Mode mission that uses the documented organizer model:

1. Use the exact documented Detector API; add the required camera sense; check request acceptance and wait non-blockingly with a bounded timeout, keeping control scheduling responsive.
2. Correlate results to a new request and a fresh camera frame. `Detector.count` can distinguish a completed request from stale `last_result`; `CameraSense.seq` reports new frames. Prefer a source-frame ID when the runtime exposes one. Otherwise, only associate a detection with a bounded hover/straight-leg observation when frame and pose timestamps/latency support a documented error bound, or run the same official ONNX model on an exact captured frame with its paired pose. If neither path can bound projection error for the current runtime, report perception provenance as `UNKNOWN` and do not spray from that result.
3. Treat outputs as image-pixel bounding boxes, not ground polygons. Project only with the public camera intrinsics, camera-to-body offset, pose/orientation, and NED/ENU mapping, carrying uncertainty and rejecting missing/stale pose/frame/calibration.
4. Validate world/safety policy against both detection geometry and the nozzle footprint before spray. The valve's asynchronous acceptance/settled state must be checked; spray is off for transit, turns, uncertainty, and unverified geometry.
5. Generate only the output/report artifacts specified by the current authorized scenario pack. Do not hardcode the prior public contest's `stress_area.json` as a generic or current-semifinal contract.

The previous public example's HSV yellow mask is an illustrative baseline only, not a published fixed threshold and not proof of B generalization. The semifinal brief says disease, stress, and healthy signals may overlap, publishes no fixed colour threshold, and directs teams to use colour, texture, local context, and current-run observations. The public organizer model's manifest names its single class `stressed`; the MCP must use that model and may add non-training image/geometry post-processing over current-run observations. Do not fine-tune, retrain, or replace the organizer model. Do not relabel its `stressed` output as a disease classification or claim B accuracy/generalization absent judge evidence. The lack of a second public model is not a generic MCP release blocker.

The App's Plan AI Flow currently shows the organizer stress model in its catalogue, but the flow was reported as unassigned and untested. Catalogue visibility, flow assignment, successful inference, and report evidence are distinct capability states. Plan AI Flow and Code Mode are separate integration paths: success in one does not establish the other. This spec does not require additional model training or fine-tuning; use the organizer model with permitted post-processing.

### Scenario-specific rule packs

The MCP core is task-agnostic. A contest pack may encode published A constraints, model/output contracts, required native evidence, team naming, and eligibility checks. For the 2026 semifinal, the currently authorized materials are the published brief and pinned public repository; do not assume an additional email package is available. The brief references a starter kit whose separate output schema is not present in those materials, so do not assume the prior public example's `stress_area.json` applies. Keep only that scenario's report/output status `UNKNOWN` until the schema can be verified against an actual user-run native report or another authorized published App contract. This does not block the general MCP, model discovery/setup, or unrelated authoring workflows. No B-private inputs are allowed in the pack, fixtures, or evaluations.

#### 2026 semifinal pack acceptance gates

The eventual semifinal pack must map to the published brief and verifiable App/report evidence, not hardcode private answer data. Treat any schema not defined in the brief or public repo as `UNKNOWN` until a user-run native report or authorized App contract verifies it:

- Required environment is An Giang (outdoor), all 130 cultivated parcels (about 28.65 ha), one X500 Nozzle system with Camera, Default spawn, and the required SkyTrack Desktop version. The public brief states Desktop 1.2.0 or later; the actual selected build must still be checked.
- Flight must remain at or below 40 m AGL, and valid spray must be at or below 20 m AGL. AGL is terrain-relative along the complete route, including takeoff, transit, return, and descent; missing terrain/pose certainty is `UNKNOWN`, not `PASS`.
- The drone body must maintain at least 5 m from residential boundaries. Route clearance must account for the vehicle footprint and localization uncertainty. Entry into the 5 m buffer is permitted only to approach and land at an installed charging pad; spraying any residential area or its buffer is always prohibited. The exception is not permission to overfly or enter residential structures.
- The four stated pad centers are CS1 `(0.00, 0.00, 0.0)`, CS2 `(329.32, -234.73, -1.0)`, CS3 `(356.43, -654.32, 0.0)`, and CS4 `(41.72, -582.67, -1.1)` in local ENU metres; touchdown must be within 3 m. A full charge supports at most 15 simulated flight minutes; the full mission is limited to 90 minutes from the first run command. Charging is unlimited. The process must use Mission Break to pause and land at a valid pad, then wait for manual user resume after recharge. A generic Pause or scripted assumption is not equivalent.
- Any invalid landing, flight above the 40 m AGL ceiling, residential/no-fly violation, or runtime above 90 minutes invalidates that run and zeros all machine metrics. Preflight must fail/return `UNKNOWN` if geometry, terrain, pad identity, or Mission Break/manual-resume behavior is not established from the selected App/runtime contract.
- Variant A eligibility requires an exact native report identifying the matching run, the required team-name prefix on both Project and Mission, and a shared mission judges can copy/open and rerun without post-deadline manual team/configuration changes. The submission PDF is a separate qualitative requirement; the machine score is based on three Variant B runs and their per-metric medians (30 Coverage, 12 Detection, 28 Spray; 30 qualitative points are assessed separately).
- A is for eligibility, not target coordinates or ground truth. The disease/stress distribution changes in B and remains private. Tests may use authorized A references and synthetic distribution shifts only; do not use fixed A disease/stress coordinates as labels or claim B generalization.

## Reports, Media, and Explicit Debugging

### Read-only report workflow

Read native App-managed reports, events, logs, images, and video for the exact mission/run. Prefer an explicit run ID. When the user explicitly asks for debugging and gives no run ID, select the most recent run belonging to the exact mission; state the run ID and timestamp before analysis. Never combine evidence from different runs.

If the native report or local media is unavailable, ask for/upload only the specific user-provided report, log, image, or video needed. Label user-provided evidence with its source and provenance; do not relabel synthetic or unverified material as native.

### Debug workflow

Debugging is invoked only by an explicit user request that describes a problem (for example, “hãy debug…”). Then:

1. Resolve the exact mission and report/run; report its timestamp/run ID.
2. Read only evidence attached to that mission/run and any material the user supplied for the request. The user authorizes sending that run's selected report/log/image/video to the configured coding-host model for analysis; do not send it elsewhere or publish it.
3. Diagnose and edit/save the same mission, preserving the non-target Plan/Code representation and respecting App edit permissions. If the mission is an immutable judge/submission snapshot, do not bypass the lock or claim the submitted revision changed; hand back the diagnosis and explain the restriction.
4. Snapshot, read back, mode-aware validate, and report changes and limitations.
5. Hand off for the user to run the repaired mission. Do not dispatch, observe, or automatically debug the rerun.

There is no automatic report polling, log scraping, proactive diagnosis, or media upload outside this explicit flow.

## Simulation and Safety Boundary

The default distributed MCP/plugin must not register agent-callable tools for simulation dispatch, UAV flight control, stack lifecycle/recovery, or closed-loop run observation. This includes current `execute_route_mission`, `execute_uav_python_script`, `run_mission_and_wait_completion`, `control_uav_flight`, and simulation start/stop/restart/recovery tools. They must not remain visible in the default plugin merely because a skill says not to call them. User-run reports are ingested read-only, except for explicit debug repair of the mission artifact as specified above.

No hook, skill, MCP startup event, model call, or debug action may start a simulation. Any future user-requested MCP execution/control feature requires a separate design and permission review; it is outside this specification.

## Validation and Capability/Evidence States

Do not collapse status into a single `valid: true`. Return distinct, machine-readable states at minimum:

- `target_resolution`: `EXACT`, `AMBIGUOUS`, `MISSING`, `UNAVAILABLE`, or `PERMISSION_DENIED`.
- `edit_authorization`: `VERIFIED`, `DENIED`, or `UNVERIFIED`; local filesystem writability alone must never produce `VERIFIED`.
- `persistence`: `SAVED_AND_READ_BACK`, `MISMATCH`, `PARTIAL_FAILURE`, or `NOT_SAVED`, with snapshot/revision/hash where available.
- `mode_integrity`: Plan/Code metadata and active representation agree, or a precise blocker.
- `syntax`: parse result for Code.
- `sdk_reference_alignment`: `REFERENCE_MATCH`, `UNKNOWN`, or `INCOMPATIBLE` against the pinned examples/docs commit.
- `installed_sdk_compatibility`: `INSTALLED_RUNTIME_VERIFIED`, `UNKNOWN`, or `INCOMPATIBLE` based on the actual App/runtime package version or a successful user-run report; reference alignment alone is not installed-runtime proof.
- `model_availability`: exact SkyTrack model/class and artifact identity in the selected runtime; `AVAILABLE`, `NOT_AVAILABLE`, or `UNKNOWN`.
- `perception_provenance`: request/frame/pose correlation and coordinate projection are supported/verified or `UNKNOWN`.
- `safety_policy`: rule-pack checks are `PASS`, `FAIL`, or `UNKNOWN`; missing world/terrain/geometry cannot pass.
- `app_compatibility`: process build and installed bundle match a verified adapter profile or are unsupported.
- `simulation`: always `USER_RUN_REQUIRED` in v1; it is never an MCP dispatch result.
- `report_evidence`: `NATIVE_CORRELATED`, `USER_PROVIDED`, `SYNTHETIC`, `MISSING`, or `UNVERIFIED`, with exact mission/run identity when available.
- `contest_eligibility`: only verifiable after all published requirements and native A evidence are checked; B score/generalization remains `UNKNOWN` until judges run B.

## Packaging and Installation

- Package the Python MCP as a normal installable console application using the existing `pyproject.toml` entry point; the Claude plugin must not reference `/Users/...`, a checkout path, or a per-project virtual environment.
- Bundle the MCP config and platform-aware launcher with the global Claude Code plugin. Use plugin-relative paths. Because the plugin manifest has no declarative macOS/Linux conditional path, use a small runtime OS-discovery wrapper rather than hardcoding macOS paths.
- Install the plugin at Claude Code user scope so it is available across the user's projects on one machine. Let the `skytrack` skill be naturally discoverable for relevant requests, with the optional `/skytrack` entrypoint; omit hooks unless a safe need is independently justified.
- Publish direct stdio MCP setup instructions for OpenCode and Codex; do not promise Claude plugin/skill/hook parity there in v1.
- Discover SkyTrack Desktop data roots and running/installed build identities per OS. Do not require AppleScript, `ioreg`, `/Users/...`, or `~/Library/...` on Linux; do not make macOS APIs mandatory for core mission storage.

## Testing Strategy

### Offline unit and contract tests

- Exact project+mission name resolution, duplicate-name disambiguation, stable-ID verification, missing-mission approval path, and no most-recent fallback.
- Plan/Code round trips with multi-sequence plans, standalone actions, IDs, and unknown metadata; snapshots and read-back hashes; failure-before-mutation; mode switching preserves both representations.
- App integration adapter fixtures for process/bundle identity, supported build profiles, permission denial, exact selection, refresh success, and drift/unknown fail-closed behavior. No auth material in results/logs.
- MCP exposes no dispatch/control/stack lifecycle/recovery tools in the default plugin profile.
- Natural-language skill discovery and the optional `/skytrack` entrypoint work; hooks are omitted by default and any approved hook is read-only/safe on every lifecycle event. Plugin install is independent of project cwd; launcher resolves macOS/Linux without a developer path.
- Pinned upstream import/API/template fixtures; tests must catch the current Level 4 Detector omission, wrong imports, missing model wiring, stale result use, unbounded wait, invalid box-to-ENU conversions, and absence/incorrect format of required scenario output.
- Model setup tests verify the pinned/user-provided artifact hash and manifest before Local installation; Cloud availability is reported as `UNKNOWN` unless proven by the selected runtime. No training or model replacement path is offered.
- Report/media ingestion tests prove exact mission/run separation, latest-run fallback scoped to one mission, run ID/timestamp reporting, and correct provenance labels.
- Scenario pack tests use only public/authorized A fixtures or synthetic shifted data. Never inspect/use Variant B artifacts or judge-only data.

### App/manual validation (user-operated)

The user may manually verify save-refresh behavior and run missions in SkyTrack Desktop. The MCP does not trigger these runs. A user-provided native report/media can then validate App behavior and current scenario requirements. A Local success is useful but does not prove Cloud model availability; Cloud claims require a Cloud-origin native report. No claim of B performance can be made before judge evaluation.

## Phased Delivery and Dependencies

1. **Package and read-only core:** replace developer-local MCP paths; add cross-platform data-root discovery and read-only exact mission identity resolution; keep simulation/control excluded.
2. **App identity, compatibility, and authorization gate:** use App-owned files/interfaces first; establish session identity, exact project/mission edit permission, process/bundle compatibility for any internal adapter, and verified write semantics. If authorization or compatibility cannot be proven, keep the capability read-only and report `PERMISSION_UNVERIFIED` or `APP_COMPATIBILITY_UNKNOWN`.
3. **Mission authoring integrity:** enable lossless Plan/Code writes only after Phase 2 gates; snapshot, preserve the inactive representation, read back exact content/mode, and provide a verified refresh or user reopen handoff.
4. **Report/debug workflow:** add explicit user-triggered run selection, native report/media ingestion, same-mission repair subject to edit rights, and user-rerun handoff.
5. **Claude Code plugin:** add global user-scope plugin manifest, bundled MCP config/launcher, naturally discoverable skill plus optional `/skytrack` entrypoint, and only necessary safe hooks; document OpenCode/Codex core setup.
6. **AI model and scenario support:** pin the SDK reference, use the App catalogue model first, allow verified setup from a user-provided package through supported paths, implement Code Mode detection-to-world/spray post-processing without training or replacing the model, and gate model availability per user-selected runtime. Keep the semifinal output schema `UNKNOWN` until verified against an actual user-run native report or an authorized published App contract; this does not block generic MCP features.

Each phase requires its own implementation task, tests, and review. No phase authorizes simulation execution, Cloud runtime changes, or public sharing.

## Open Blockers and Risks

- The App's reported/UI/bundle/MCP versions have conflicted; a trustworthy process+bundle identity probe and compatibility matrix must be built before private adapter operations are enabled.
- The installed App's Plan AI Flow now displays the organizer stress model, but a successful run/report has not been observed. Catalogue visibility is not inference proof.
- The public Local zip install procedure is documented. Cloud model availability, mission-share portability, and clean judge runtime model staging are unverified and must not be assumed.
- The semifinal brief references an organizer starter kit, but the separate kit/output schema is not among the authorized materials currently available. Do not assume the prior public contest guide's `stress_area.json` schema applies; verify through an actual user-run native report or another authorized published App contract. This scenario-specific uncertainty does not block generic MCP authoring/report/debug features.
- The public Detector API does not expose a source-frame ID in the documented result. The implementation must verify a bounded hover/frame/pose time alignment or run the same official ONNX model on a specifically captured frame; if neither provides a defensible error bound, mark that detection `UNKNOWN` and do not spray from it.
- The public model manifest labels its output `stressed`, while the semifinal's target union includes disease and stress. Permitted post-processing may be evaluated against authorized A evidence, but do not relabel the model output as a disease classification or claim a disease/B score without supporting evidence. This is a capability-evidence limitation, not a requirement to train or source a replacement model.
- Geometry/terrain coverage of the An Giang world and all route/spray-body buffers must be validated from authorized A resources. The MCP's packaged `competition.sdf` is a different small test world, not An Giang.
- Private adapters may break with App updates. They are explicitly experimental, version-pinned, never silently fall back, and require a fresh review when the build changes.

## Historical Documents

- `2026-09-28-skytrack-app-bridge-design.md` captured the earlier no-bridge design boundary. Its original rationale remains useful, but its no-adapter non-goal and Local-run option are superseded here.
- `2026-09-28-skytrack-mission-authoring.md` captured a Phase-1 implementation plan that included Local execution and omitted the distributable plugin, report/media debug flow, current model interface, and cross-platform App adapter. Do not execute it as-is; a new implementation plan must be written from this reviewed design after approval.
