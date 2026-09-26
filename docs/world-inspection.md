# SkyTrack 3D World Inspection & Analysis

## 1. 3D Gazebo SDF Geometry Engine
SkyTrack 3D simulation environments are defined as SDFormat files (`.sdf`). Rather than relying on AI visual estimation from 2D screenshots, the MCP server parses physical collision geometries directly:
- **Collision Shapes Extracted:**
  * Box collisions: `<box><size>sx sy sz</size></box>`
  * Cylinder collisions: `<cylinder><radius>r</radius><length>l</length></cylinder>`
  * Sphere collisions: `<sphere><radius>r</radius></sphere>`
- **Pose Concatenation:** Model-level poses are concatenated with link and collision local poses, including yaw angle transformation.

## 2. 2D Top-Down Occupancy Slices
To provide model-friendly environmental awareness, `inspect_world_map` takes a flight altitude slice $z$ and projects all active obstacles into an ASCII occupancy grid:
```text
Top-Down Map Slice at z=3.5m | X (East): [-10.0m .. +10.0m], Y (North): [+10.0m .. -10.0m]
'#'=Obstacle, 'S'=Origin(0,0), '.'=Free Space
Y= +10.0m | .....................
Y=  +5.0m | .#...................
Y=  +0.0m | .#........S..........
Y=  -5.0m | .#...................
Y= -10.0m | #####################
```

## 3. 3D Slab Collision Detection
Trajectories are tested for safety before flight using the 3D Slab Intersection algorithm:
$$\text{Segment: } P(t) = P_0 + t(P_1 - P_0), \quad t \in [0, 1]$$
Each obstacle AABB is inflated by `clearance_m` (default 0.4m). If $t_{\text{min}} \le t_{\text{max}}$, a collision is flagged and the intersecting obstacle model/name is reported to the agent.
