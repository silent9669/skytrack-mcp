# SkyTrack Report Verification & Evidence Engine

## 1. Post-Flight Report Harvesting
Following touchdown, `harvest_flight_report` collects data from multiple disparate sources:
- Media directory: `ClientData/prj-.../mis-.../media/captures/` and `recordings/`.
- Logs directory: `ClientData/prj-.../mis-.../logs/` (PX4 `.ulg` flight logs).
- Autonomy container: Execution stdout/stderr from `/tmp/skytrack_mcp_user_script.log`.
- MAVLink bridge: Terminal position, battery consumed, and flight modes.

## 2. Requirement Verification Matrix
The verification engine cross-checks harvested data against initial requirements:

```json
{
  "mission_id": "01M39QD97035MQVDQ52129D4WJ",
  "overall_status": "PASS",
  "summary": "Verification PASS: 3/3 requirements verified successfully.",
  "items": [
    {
      "requirement_name": "Safe Landing",
      "mandatory": true,
      "expected": "ON_GROUND",
      "observed": "Drone landed safely on ground",
      "evidence": "telemetry.landed_state == 'ON_GROUND'",
      "status": "PASS",
      "confidence": "HIGH"
    }
  ]
}
```

## 3. Strict Verification Rules
- **Rule of Truth:** A mission is NEVER marked `PASS` if any mandatory item is `FAIL` or `UNKNOWN`.
- **Evidence Trail:** Every verdict links directly to telemetry fields, file paths, or parsed log output.
