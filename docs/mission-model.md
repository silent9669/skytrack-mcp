# SkyTrack Mission Data Model Specification

## 1. Coordinate Frames & Conventions

SkyTrack operates across two primary coordinate conventions:
1. **Local ENU (East-North-Up):**
   - **X:** East (positive East, negative West) in meters.
   - **Y:** North (positive North, negative South) in meters.
   - **Z:** Up (positive altitude above launch, negative down) in meters.
   - **Usage:** SkyTrack Map UI, `plan.json`, Path Planner API (`:20007`), and MCP tool parameters.
2. **Local NED (North-East-Down):**
   - **X:** North in meters.
   - **Y:** East in meters.
   - **Z:** Down in meters (altitude is negative Z).
   - **Usage:** PX4 Autopilot internals and wire frame sent to Mission Computer.
3. **Conversion Formula:**
   $$\text{NED} = (Y_{\text{ENU}}, X_{\text{ENU}}, -Z_{\text{ENU}})$$
   $$\text{ENU} = (Y_{\text{NED}}, X_{\text{NED}}, -Z_{\text{NED}})$$

## 2. Canonical Mission Model (`CanonicalMission`)

Defined in `src/skytrack_mcp/mission/models.py`:

```python
class CanonicalMission(BaseModel):
    project_id: str
    mission_id: str
    name: str = "Untitled Mission"
    world: str = "default"
    vehicle: str = "x500_livox_mid_360"
    code_mode: bool = False
    takeoff_altitude: float = 2.5
    target_speed: float = 2.0
    safety_option: Literal["avoid", "brake", "off"] = "avoid"
    end_action: Literal["rtl", "land"] = "rtl"
    spawn_location: List[float] = [0.0, 0.0, 0.0]
    waypoints: List[Waypoint] = []
    raw_actions: List[Dict[str, Any]] = []
    no_fly_zones: List[NoFlyZoneVolume] = []
    python_script: Optional[str] = None
```

## 3. Storage Formats

### `mission.json` (Metadata)
```json
{
  "world": "warehouse",
  "vehicle": "x500_tennis_balls_no_cam",
  "codeMode": false,
  "takeoffAltitude": 3.5,
  "targetSpeed": 2.0,
  "safetyOption": "avoid",
  "end": {
    "id": "uuid-here",
    "type": "rtl"
  }
}
```

### `plan.json` (Visual Sequences)
```json
{
  "spawnLocation": [0.0, 0.0, 0.0],
  "sequences": [
    {
      "id": "uuid-seq",
      "type": "route",
      "targetSpeed": 2.0,
      "actions": [
        { "id": "act-1", "type": "navigate", "data": [2.63, -1.0, 3.5] },
        { "id": "act-2", "type": "navigate", "data": [2.63, -7.59, 3.5] },
        { "id": "act-3", "type": "drop-ball" }
      ]
    }
  ]
}
```

### `script.py` (ROS 2 Autonomy Script)
```python
from typing import Any, Iterator
from local_planner import boot_drone, takeoff, fly_to, land

def scenario(ctx: Any) -> Iterator[Any]:
    yield takeoff(alt_m=3.5)
    yield fly_to(north=-1.0, east=2.63, alt_m=3.5)
    yield fly_to(north=-7.59, east=2.63, alt_m=3.5)
    yield land()

scenario.requires_senses = ["pose", "obstacle", "status"]

def main() -> None:
    with boot_drone() as drone:
        drone.fly(scenario)
        drone.run()
```
