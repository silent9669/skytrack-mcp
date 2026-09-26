


# 1. TARGET CAPABILITY

The resulting system must allow an AI agent to receive a natural-language mission assignment such as:

* inspect a specified area;
* fly through specified locations;
* scan a tunnel or structure;
* satisfy altitude/speed/sensor/task constraints;
* avoid known obstacles;
* return home and land;
* execute some SkyTrack-supported mission behavior;

and autonomously perform the complete loop:

UNDERSTAND TASK
→ INSPECT SKYTRACK
→ INSPECT CURRENT WORLD
→ INSPECT VEHICLE / MISSION / ENVIRONMENT
→ BUILD AN INTERNAL MISSION MODEL
→ PLAN A ROUTE
→ STATICALLY VALIDATE ROUTE
→ CREATE OR MODIFY THE SKYTRACK MISSION
→ RUN SIMULATION
→ OBSERVE EXECUTION
→ INSPECT WORLD / PATH / VEHICLE STATE
→ OPEN AND READ MISSION REPORT
→ COMPARE RESULT AGAINST ORIGINAL TASK
→ IDENTIFY FAILURES
→ MODIFY MISSION
→ RE-RUN
→ VERIFY
→ RETURN EVIDENCE-BACKED RESULT

The agent must not simply assume that a mission is correct because the simulator starts or because the path looks visually plausible.

It must verify correctness against the original task.

# 2. DEFAULT SAFETY SCOPE

Target Mission Simulation first.

DO NOT control physical drones, Ground Control Station hardware, or deploy a mission to real hardware as part of this goal.

Any real-hardware functionality discovered during research must be isolated behind an explicit capability boundary and disabled by default.

Do not bypass authentication, licensing, security controls, or operating-system protections.

Use documented/public interfaces, user-accessible local application state, mission files, local services, accessibility interfaces, logs, Docker interfaces, and normal computer interaction.

# 3. IMPORTANT ENGINEERING PRINCIPLE

Do NOT begin by implementing mouse-coordinate automation.

First discover what structured interfaces are actually available.

Use this priority hierarchy:

1. Official SkyTrack APIs / SDKs / CLI interfaces if available.
2. Mission JSON or other supported structured mission formats.
3. Supported project/local application data.
4. Local SkyTrack services or documented local endpoints.
5. Docker/container state and simulator interfaces that are appropriate to access.
6. Application accessibility tree / semantic UI automation.
7. Electron/Chromium automation or CDP if legitimately available.
8. Computer-use keyboard/mouse interaction.
9. Screenshot + visual reasoning as fallback.

Use the highest-level reliable interface available for each operation.

Computer Use is necessary, but should be a fallback or complementary observation/control mechanism rather than the only integration method.

Never depend primarily on hard-coded absolute screen coordinates unless there is no better option.

If coordinate-based interaction is unavoidable, implement:

* window detection;
* resolution/DPI awareness;
* anchor-based calibration;
* visual confirmation;
* retries;
* state verification;
* recovery behavior.

# 4. PHASE A — RESEARCH SKYTRACK BEFORE CODING

Research the CURRENT SkyTrack version and the actual installed environment.

Do not rely on prior assumptions.

Inspect:

* current official SkyTrack documentation;
* current release notes;
* Mission Studio workflow;
* mission JSON support;
* project organization;
* world selection;
* vehicle selection;
* visual mission editor;
* code/JSON editor;
* simulation lifecycle;
* Mission Report;
* Docker requirements;
* Console Mode;
* available keyboard shortcuts;
* available logs;
* available export/import mechanisms;
* available developer or integration interfaces;
* simulator architecture where legitimately observable.

Then inspect the local machine and determine:

* OS and architecture;
* SkyTrack installation location;
* SkyTrack version;
* whether the application is Electron, native, browser-based, or hybrid;
* SkyTrack processes;
* child processes;
* local ports owned by SkyTrack;
* Docker containers created by SkyTrack;
* relevant mounted volumes;
* logs;
* mission/project storage;
* accessible configuration;
* accessibility tree availability;
* whether any local structured interface exists;
* whether the mission JSON can be safely manipulated outside the GUI;
* whether world/environment metadata can be accessed structurally;
* whether simulation state can be observed structurally.

Do not modify proprietary binaries.

Document discoveries in:

docs/research.md

For each possible integration surface record:

* interface;
* capability;
* reliability;
* latency;
* maintainability;
* version sensitivity;
* read/write scope;
* risks;
* whether it will be used.

Create:

docs/integration-decision.md

with an explicit decision matrix explaining why each MCP capability uses its selected integration method.

Do not continue blindly if your initial architecture assumptions are disproved.

Adapt based on evidence.

# 5. PHASE B — UNDERSTAND THE MISSION DATA MODEL

Discover and document the actual SkyTrack mission representation.

Determine, when possible:

* mission JSON schema;
* mission metadata;
* actions / behaviors;
* waypoint representation;
* coordinate system;
* coordinate frame;
* altitude semantics;
* speed semantics;
* takeoff;
* landing;
* return-to-home;
* loiter;
* task actions;
* payload actions;
* sensors;
* vehicle configuration;
* world selection;
* mission ordering;
* transitions;
* validation constraints.

Build a typed internal canonical model independent from UI automation.

Example conceptual objects:

Mission
MissionStep
Waypoint
Pose
Vehicle
World
Task
PayloadAction
SensorRequirement
SimulationState
MissionReport
Constraint
ValidationIssue

Do NOT invent SkyTrack fields.

Only map fields confirmed through documentation, exported examples, application behavior, or observed schemas.

Unknown fields should remain explicitly unknown.

Create version-aware parsers/serializers where needed.

# 6. ARCHITECTURE

Use clean separation of concerns.

A suggested layout is:

src/
mcp/
adapters/
skytrack/
ui/
accessibility/
simulator/
docker/
mission/
world/
route/
simulation/
report/
diagnostics/
vision/
common/

skills/
evals/
tests/
fixtures/
docs/
scripts/

The exact architecture may change based on research.

The system should contain at least these conceptual layers:

A. SkyTrack Adapter Layer
Responsible for talking to SkyTrack using the best available interfaces.

B. Observation Layer
Responsible for obtaining reliable application/world/mission/simulation state.

C. Mission Model Layer
Normalizes SkyTrack mission structures.

D. Route Analysis Layer
Performs geometry/path/constraint checks when sufficient information exists.

E. Computer Use Layer
Provides semantic UI interaction and fallback control.

F. Simulation Runner
Controls simulation lifecycle and detects completion/failure.

G. Mission Report Parser
Extracts structured result information.

H. MCP Layer
Exposes carefully designed primitives to agents.

I. Skill Layer
Teaches the agent how and when to combine those primitives.

J. Evaluation Harness
Runs repeatable end-to-end tests.

# 7. MCP IMPLEMENTATION

Use the CURRENT stable official Model Context Protocol SDK available at implementation time.

Check official MCP documentation before choosing SDK/version.

Prefer local stdio transport initially unless another transport has a concrete advantage.

Support clean startup/shutdown.

Never write debugging text to stdout if stdout is being used as the MCP protocol channel.

Use structured logging.

Every tool should have:

* precise description;
* typed input schema;
* typed/structured output where useful;
* deterministic semantics where possible;
* explicit timeout;
* useful error codes;
* actionable error message;
* relevant state/evidence;
* safe retry behavior.

Avoid giant ambiguous tools.

Expose atomic primitives plus a small number of useful deterministic composite operations.

# 8. REQUIRED MCP CAPABILITY GROUPS

Exact tool names may be improved during implementation, but equivalent capabilities must exist.

## Environment / application

skytrack_status
skytrack_launch
skytrack_focus
skytrack_get_version
skytrack_get_context
skytrack_healthcheck

The context should include information such as:

* application running;
* active project;
* active mission;
* selected world;
* selected vehicle;
* simulation state;
* Docker/runtime health.

## Projects / missions

skytrack_list_projects
skytrack_list_missions
skytrack_open_mission
skytrack_create_mission
skytrack_clone_mission
skytrack_import_mission
skytrack_export_mission

## Mission structured access

skytrack_get_mission
skytrack_get_mission_json
skytrack_validate_mission
skytrack_patch_mission
skytrack_set_mission
skytrack_save_mission

Prefer patch-style modifications where practical rather than replacing an entire mission blindly.

Before destructive changes, preserve a recoverable snapshot.

## World/environment

skytrack_list_worlds
skytrack_select_world
skytrack_get_world_context
skytrack_inspect_world
skytrack_capture_world

`skytrack_inspect_world` should return the richest reliable representation possible.

Depending on discoveries this may include:

* coordinate frame;
* world bounds;
* spawn/home position;
* known structures;
* known obstacles;
* traversable regions;
* relevant points of interest;
* available environment metadata;
* confidence/source of each observation.

Do not fabricate precise geometry from screenshots when precise geometry is unavailable.

## Vehicle

skytrack_list_vehicles
skytrack_select_vehicle
skytrack_get_vehicle_context

Expose known relevant properties when available.

## UI / computer use

ui_snapshot
ui_find
ui_click
ui_type
ui_key
ui_drag
ui_scroll
ui_wait_for
ui_get_state

Prefer semantic target descriptions over raw x/y coordinates.

A UI snapshot should ideally contain:

* screenshot;
* active window;
* accessibility elements if available;
* important visible text;
* viewport dimensions;
* timestamp.

## Camera / viewport

skytrack_camera_reset
skytrack_camera_orbit
skytrack_camera_pan
skytrack_camera_zoom
skytrack_focus_region

These can be implemented using normal application controls if no structured camera API exists.

## Simulation

skytrack_simulation_start
skytrack_simulation_pause
skytrack_simulation_resume
skytrack_simulation_restart
skytrack_simulation_stop
skytrack_simulation_state
skytrack_simulation_wait
skytrack_simulation_observe

Observation should collect the strongest available evidence, such as:

* state;
* current mission step;
* vehicle position when available;
* errors;
* logs;
* screenshots;
* timing;
* simulator termination state.

## Reports

skytrack_report_open
skytrack_report_read
skytrack_report_export

Parse Mission Report into structured data where possible.

Do not rely only on screenshots if textual/structured report content is accessible.

## Diagnostics

skytrack_logs
skytrack_docker_status
skytrack_diagnostics
skytrack_recover

Recovery should handle common states such as:

* SkyTrack not running;
* Docker unavailable;
* simulation stuck;
* modal dialog;
* wrong panel;
* lost window focus;
* stale mission;
* report not generated;
* mission editor closed;
* world not loaded.

# 9. MCP RESOURCES

Expose useful relatively-static/read-only knowledge as MCP resources where appropriate.

Examples:

skytrack://docs/operator-guide
skytrack://schema/mission
skytrack://worlds
skytrack://vehicles
skytrack://examples/missions
skytrack://errors/catalog
skytrack://capabilities
skytrack://current/mission
skytrack://current/report

Only expose resources that are actually useful and reliable.

# 10. MCP PROMPTS

Where supported by target MCP clients, implement useful prompts such as:

skytrack-solve-mission
skytrack-inspect-world
skytrack-debug-mission
skytrack-review-route
skytrack-explain-report

The mission-solving prompt should orchestrate the full Observe → Plan → Execute → Verify workflow but should NOT hide underlying tools from the model.

# 11. BUILD A COMPLETE SKYTRACK SKILLBOOK

MCP tools alone are not sufficient.

Create a high-quality skillbook teaching an agent how to operate SkyTrack effectively.

Create separate skills instead of one huge instruction file.

At minimum:

skills/skytrack-operator/
skills/skytrack-task-understanding/
skills/skytrack-world-inspection/
skills/skytrack-route-planning/
skills/skytrack-mission-authoring/
skills/skytrack-computer-use/
skills/skytrack-simulation/
skills/skytrack-report-analysis/
skills/skytrack-mission-verification/
skills/skytrack-recovery/

Each skill should include:

* purpose;
* trigger conditions;
* assumptions;
* prerequisites;
* relevant MCP tools;
* normal workflow;
* decision rules;
* evidence requirements;
* failure modes;
* recovery strategy;
* stop conditions;
* examples.

Do not put vague advice such as “inspect carefully.”

Define operational procedures.

# 12. CORE AGENT OPERATING LOOP

The skillbook should teach this exact conceptual loop.

## STEP 1 — Parse the assignment

Extract:

* mission objective;
* mandatory actions;
* start/end requirements;
* locations;
* ordering;
* altitude constraints;
* speed constraints;
* world constraints;
* sensor requirements;
* payload/task requirements;
* coverage requirements;
* prohibited behavior;
* success conditions;
* ambiguous requirements.

Create a `MissionRequirements` object.

Do not start editing until the requirements are explicitly represented.

## STEP 2 — Observe current SkyTrack state

Inspect:

* active project;
* active mission;
* world;
* vehicle;
* current JSON;
* simulator readiness;
* Docker status.

Do not assume a blank starting state.

## STEP 3 — Inspect the world

Attempt structured inspection first.

Then inspect map/3D viewport visually where necessary.

Use multiple views when useful:

* overview;
* top-down;
* oblique;
* close-up;
* route area.

Identify relevant landmarks, corridors, obstacles, start position, and target regions.

Record evidence and confidence.

## STEP 4 — Build an internal world model

Represent only what is known.

Separate:

FACT
DERIVED
VISUAL ESTIMATE
UNKNOWN

Never treat a visual estimate as exact coordinate geometry.

## STEP 5 — Plan mission

Translate requirements into a mission strategy.

For path missions reason about:

* required sequence;
* waypoint count;
* altitude transitions;
* obstacle clearance;
* unnecessary distance;
* turns;
* approach direction;
* takeoff;
* task execution;
* return;
* landing;
* vehicle/sensor constraints.

Prefer simple robust routes over unnecessarily complicated routes.

## STEP 6 — Static validation

Before simulation check everything that can be checked without running.

Examples:

* mission schema validity;
* missing fields;
* invalid ordering;
* waypoint order;
* obvious segment-obstacle intersections when geometry exists;
* altitude violations;
* impossible transitions;
* required task absent;
* missing return/landing behavior;
* unsupported vehicle/sensor configuration;
* duplicate or unreasonable waypoints.

Produce structured validation results.

## STEP 7 — Author mission

Use structured mission editing whenever possible.

Use UI editing when needed.

After editing:

READ THE MISSION BACK.

Never assume a write operation succeeded.

Compare actual mission state against intended mission state.

## STEP 8 — Preflight

Confirm:

* correct world;
* correct vehicle;
* correct mission;
* Docker/runtime healthy;
* simulator ready;
* no blocking dialogs;
* mission saved.

Capture evidence.

## STEP 9 — Run simulation

Start the mission.

Observe execution.

Do not immediately jump to the final report.

Capture relevant state during execution if available.

Detect:

* crash;
* stuck state;
* failure to take off;
* wrong waypoint;
* wrong task behavior;
* timeout;
* simulator error;
* unexpected landing;
* route divergence.

## STEP 10 — Inspect mission report

Read the Mission Report.

Extract actual outcome into structured data.

## STEP 11 — Compare result with original assignment

Create a verification matrix:

Requirement
Expected
Observed
Evidence
Status
Confidence

Statuses:

PASS
FAIL
UNKNOWN

Never turn UNKNOWN into PASS.

## STEP 12 — Repair

If any meaningful requirement is FAIL:

diagnose root cause;
make the minimum useful change;
re-run static validation;
re-run simulation;
re-read report;
re-verify.

Avoid random waypoint tweaking without a diagnosis.

## STEP 13 — Final verification

Only declare success when:

* mission representation is valid;
* simulation completed acceptably;
* report was inspected;
* all mandatory assignment constraints have PASS evidence;
* no unresolved critical UNKNOWN remains.

# 13. ROUTE-PLANNING SKILL

Build route planning as reasoning supported by deterministic helpers, not pure LLM guessing.

Implement geometry utilities where meaningful:

* Euclidean distance;
* 2D/3D segment length;
* route total length;
* bounding boxes;
* point/segment distance;
* line-segment intersection;
* obstacle inflation / safety margin when geometry is known;
* waypoint clearance;
* path sampling;
* altitude checks;
* duplicate waypoint detection;
* abrupt altitude-transition checks.

If sufficiently precise world geometry becomes available, consider implementing appropriate graph/path algorithms such as:

* visibility graph;
* A*;
* grid search;
* waypoint graph search;

but DO NOT implement sophisticated pathfinding merely for appearance.

Use it only if it materially improves actual SkyTrack mission solving.

Separate:

geometric path generation

from:

mission semantics.

A geometrically short path can still be a bad mission.

# 14. WORLD INSPECTION SKILL

The agent must be able to understand a SkyTrack world rather than blindly edit coordinates.

Implement an inspection procedure that can:

1. reset camera;
2. obtain overview;
3. identify home/start;
4. identify mission-relevant area;
5. inspect candidate route;
6. zoom/rotate/pan if necessary;
7. capture evidence;
8. cross-check visual information with structured world data when available.

If screenshots are required, provide them to the agent in a useful way.

Do not reduce a 3D world to a single screenshot if multiple views are required to understand it.

# 15. COMPUTER-USE ROBUSTNESS

All UI automation must be state-aware.

Bad:

click(1213, 742)
sleep(2)
click(803, 665)

Better:

locate/open Build Mission;
verify expected panel;
locate JSON/editor element;
perform action;
wait for expected state;
verify result.

Every critical UI action should have postcondition checks.

Create reusable semantic actions.

Avoid arbitrary sleeps where event/state waits are possible.

Implement bounded retries.

On repeated failure collect:

* screenshot;
* accessibility snapshot;
* current state;
* application logs;
* relevant Docker state.

Return useful diagnostics.

# 16. REPORT ANALYSIS

Mission Report analysis must not be an afterthought.

Discover what information Mission Report exposes.

Build a parser/extractor where practical.

Normalize report output.

The verification system should be able to answer:

* Did the mission complete?
* What sequence occurred?
* Were required tasks executed?
* Were errors reported?
* Did the drone terminate in the expected state?
* Does execution support the assignment requirements?

Where a report cannot establish a requirement, use simulation evidence or mission state.

Do not claim a report proves something it does not measure.

# 17. OBSERVABILITY

Implement structured logs for the MCP.

Suggested fields:

timestamp
operation
tool
mission
world
attempt
duration
result
error_code

Generate an operation/session ID for complex workflows.

Allow diagnostics to be correlated across:

MCP
SkyTrack
Docker/simulator
UI automation

Do not log secrets or authentication tokens.

# 18. ERROR TAXONOMY

Create structured error codes instead of generic exceptions.

Examples:

SKYTRACK_NOT_RUNNING
SKYTRACK_NOT_READY
DOCKER_NOT_RUNNING
SIMULATOR_NOT_READY
MISSION_NOT_FOUND
MISSION_INVALID
MISSION_WRITE_FAILED
WORLD_NOT_FOUND
UI_TARGET_NOT_FOUND
UI_STATE_MISMATCH
SIMULATION_TIMEOUT
SIMULATION_FAILED
REPORT_NOT_AVAILABLE
REPORT_PARSE_FAILED
UNSUPPORTED_SKYTRACK_VERSION
CAPABILITY_UNAVAILABLE

Errors should tell the agent what can reasonably be tried next.

# 19. TESTING

Build tests at several levels.

## Unit tests

Test:

* mission parser;
* mission serializer;
* validation;
* geometry;
* report parsing;
* error handling;
* schemas.

## Contract tests

Test every MCP tool schema and response shape.

## Integration tests

Test SkyTrack adapter operations against the installed environment where possible.

## UI tests

Test semantic UI operations without assuming one fixed screen geometry.

## End-to-end mission evaluations

This part is mandatory.

Create representative evaluation missions using the worlds/features actually available in the installed SkyTrack version.

At minimum attempt to cover:

EVAL 1:
Simple waypoint mission.

EVAL 2:
Mission requiring meaningful environment/world inspection.

EVAL 3:
Mission with multiple constraints, such as route + altitude + task/action + return/landing.

EVAL 4:
Intentionally invalid or failing mission which the agent must diagnose and repair.

EVAL 5:
UI recovery case, such as wrong panel/state or simulation restart.

For each EVAL record:

* natural-language assignment;
* parsed requirements;
* initial state;
* generated/modified mission;
* static validation;
* simulation result;
* mission report;
* requirement-by-requirement verification;
* final status.

Prefer repeatable deterministic evals.

# 20. VERIFY THROUGH MCP INSPECTOR

Test the final MCP server with the official MCP Inspector or current equivalent official tooling.

Verify:

* server connects;
* capabilities are advertised correctly;
* tools list correctly;
* input schemas are correct;
* invalid inputs are rejected cleanly;
* resources can be read;
* prompts work where supported;
* tool outputs are model-friendly;
* server survives failed tool calls;
* no protocol corruption occurs.

# 21. AGENT-LEVEL EVALUATION

Testing individual tools is not enough.

Use a real capable agent connected to the MCP if the environment allows it.

Give the agent only:

* mission assignment;
* SkyTrack skillbook;
* MCP access.

Then test whether it can independently perform:

understand
→ inspect
→ plan
→ edit
→ simulate
→ inspect report
→ repair
→ verify.

Observe where it becomes confused.

Improve:

* tool names;
* descriptions;
* return structures;
* skill instructions;
* error messages;

until the interaction is natural.

The MCP should be optimized for an AI agent, not merely for a human developer reading APIs.

# 22. DOCUMENTATION DELIVERABLES

Produce:

README.md

docs/
architecture.md
research.md
integration-decision.md
skytrack-capabilities.md
mission-model.md
mcp-tools.md
computer-use.md
world-inspection.md
route-planning.md
simulation.md
report-verification.md
troubleshooting.md
eval-results.md

Include installation and configuration instructions.

A fresh developer should be able to:

clone repository;
install dependencies;
configure it;
start MCP;
open MCP Inspector;
successfully call SkyTrack tools.

Prefer a small number of obvious commands.

For example:

install
test
lint
start
inspect
eval

Use the package manager/tooling appropriate to the final technology choice.

# 23. README MUST INCLUDE A REAL EXAMPLE

Include a complete example such as:

User:
"Build a mission in the current world that takes off, visits A, then B, performs task X, returns home, lands, and verify it."

Then demonstrate conceptually how the agent uses:

SkyTrack context
→ world inspection
→ mission construction
→ validation
→ simulation
→ report
→ verification.

Do not fabricate actual values in documentation; use real captured eval data or clearly-marked illustrative placeholders.

# 24. VERSION RESILIENCE

SkyTrack may change.

Centralize UI selectors and version-specific behavior.

Implement capability detection where useful.

Avoid spreading SkyTrack-version assumptions throughout the codebase.

If a feature is not available in the installed version, return:

CAPABILITY_UNAVAILABLE

rather than pretending it worked.

Create a compatibility layer if multiple observed versions need support.

# 25. PERFORMANCE

Do not make the agent take screenshots unnecessarily.

Prefer structured observation when possible.

Avoid repeatedly launching SkyTrack or recreating Docker environments.

Cache static information carefully, but refresh dynamic information such as:

simulation state;
active mission;
report;
current UI.

# 26. SECURITY

Do not expose arbitrary shell execution through the MCP unless absolutely necessary.

Do not expose unrestricted filesystem access.

Scope file access to required SkyTrack/project paths where possible.

Validate paths.

Validate tool inputs.

Do not leak auth tokens, cookies, credentials, or unrelated user information.

# 27. IMPLEMENTATION QUALITY

The result must be maintainable.

Require:

* typed code where appropriate;
* minimal duplication;
* modular adapters;
* useful comments for non-obvious behavior;
* no giant god-class;
* no hard-coded personal paths;
* configuration through environment/config files;
* automated formatting/linting;
* automated tests;
* deterministic schemas.

Do not overengineer abstractions before discovering real requirements.

# 28. DEFINITION OF DONE

This goal is complete ONLY when all of the following are true:

[ ] Current SkyTrack environment has been researched.

[ ] Integration decisions are documented with evidence.

[ ] MCP server starts reliably.

[ ] MCP can detect SkyTrack and simulator readiness.

[ ] MCP can inspect current application context.

[ ] MCP can obtain mission information.

[ ] MCP can create/modify a mission.

[ ] MCP can inspect/select worlds where supported.

[ ] MCP can inspect/select vehicles where supported.

[ ] MCP can operate required SkyTrack UI when structured interfaces are insufficient.

[ ] MCP can start/restart/observe a simulation.

[ ] MCP can obtain/read Mission Report.

[ ] MCP can capture visual evidence when required.

[ ] Mission validation utilities exist.

[ ] Route-analysis utilities exist where justified.

[ ] Complete SkyTrack skillbook exists.

[ ] Agent has an explicit Observe → Plan → Execute → Verify → Repair loop.

[ ] MCP tools have robust schemas/errors/timeouts.

[ ] MCP Inspector verification passes.

[ ] Unit tests pass.

[ ] Integration tests pass where the environment supports them.

[ ] At least several representative SkyTrack end-to-end evals have been executed.

[ ] At least one intentionally broken mission has been diagnosed and repaired.

[ ] Final evaluation evidence is recorded.

[ ] README setup works from a clean shell/environment as closely as practical.

[ ] No mandatory workflow depends purely on hard-coded screen coordinates if a better interface exists.

[ ] No success is declared solely because the simulation started.

[ ] Final mission success is backed by evidence against the original assignment.

# 29. EXECUTION POLICY FOR THIS GOAL

Work autonomously.

Do not stop after research and give me a plan.

Do not stop after scaffolding the MCP.

Do not stop after implementing the first successful tool.

Do not ask me to manually perform steps that you can perform using your available browser, terminal, filesystem, computer-use, screenshot, coding, or testing capabilities.

When you encounter uncertainty:

inspect;
experiment safely;
measure;
read documentation;
test hypotheses;
record conclusions.

If multiple implementations are possible, test the most promising one rather than speculating indefinitely.

If something cannot be automated, first exhaust reasonable structured access, accessibility, UI automation, and observation approaches.

If a limitation is genuinely unavoidable, document:

* what was attempted;
* evidence;
* why it failed;
* effect on capability;
* best fallback.

Do not claim functionality without testing it.

# 30. CONTINUOUS VERIFICATION RULE

After every major implementation milestone, test the actual feature before building more layers on top of it.

Recommended sequence:

research
→ minimal SkyTrack read access
→ verify
→ minimal SkyTrack action
→ verify
→ mission read/write
→ verify
→ simulation control
→ verify
→ report access
→ verify
→ world inspection
→ verify
→ MCP exposure
→ verify
→ skillbook
→ autonomous E2E eval
→ fix weaknesses
→ final regression.

Do not build the entire system against mocked assumptions and test SkyTrack only at the end.

# 31. FINAL RESPONSE

When the work is genuinely complete, return a concise engineering handoff containing:

1. Architecture implemented.
2. Integration methods selected and why.
3. MCP capabilities/tools implemented.
4. Skillbook implemented.
5. Tests executed.
6. End-to-end SkyTrack missions executed.
7. Failures discovered and fixed.
8. Known limitations.
9. Exact commands to install/start/test/evaluate.
10. Key repository paths.
11. Evidence that the system satisfies the Definition of Done.

Do not provide an optimistic completion statement without test evidence.

The objective is not to create “an MCP for SkyTrack.”

The objective is to create a reliable agent operating layer that allows an AI system to understand a SkyTrack mission problem, inspect the simulated environment, construct and modify missions, operate SkyTrack, run simulations, inspect outcomes, compare those outcomes to the original requirements, repair failures, and converge on a verified solution with minimal human intervention.
