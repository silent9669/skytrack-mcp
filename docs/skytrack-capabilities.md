# SkyTrack Capabilities & Platform Reference

## 1. Supported Simulation Worlds (28 Worlds)
All 28 worlds are located in Gazebo Harmonic (`/var/www/files/px4-gz/worlds/*.sdf`):
1. `default`: Flat ground plane with sun lighting, ideal for open-field test flights.
2. `warehouse`: Industrial logistics facility with 5 tall shelving racks (`rack1` to `rack5`, height 2.83m) and 3 vertical structural pillars (`pole1`, `pole2`, `pole3`, height 6.04m).
3. `city`: Dense urban environment with skyscrapers, avenues, and street furniture.
4. `urban`: Residential and light-commercial city blocks.
5. `farm-petersburg`: Expansive agricultural crop fields suitable for wide-area coverage surveys.
6. `desert-cliff-terrains`: Rugged desert terrain with elevation shifts and cliffs.
7. `industrial-factory`: Complex indoor factory with pipes, gantries, and machinery.
8. `metal-processing-factory`: Foundry and metallurgical processing bays.
9. `rabati-castle-georgia`: Historical stone fortress with courtyard corridors.
10. `lake-wheeler`: Water body and lakeside infrastructure.
11. `tunnel`: Constrained enclosed subterranean corridor.
12. `rough_tunnel`: Irregular cave/mining tunnel with jagged rocky obstacles.
13. `campus`: Multi-building university campus with pedestrian courtyards.
14. `village`: Rural village with houses, trees, and fences.
15. `tower-crane`: High-altitude construction zone with crane arm and cables.
16. `baylands`: Coastal wetlands and water basins.
17. `living_room`: Confined indoor residential room with furniture (chairs, sofa, tables).
18. `factory`: Standard manufacturing warehouse layout.
19. `competition`: UAV arena with obstacle gates and hoops.
20. `aruco`: Precision landing and visual marker testing environment.
21. `lawn`: Grassy lawn with residential boundaries.
22. `rover`: Ground vehicle testing course.
23. `forest`: Natural wooded environment with high density of tree trunks and canopies.
24. `thermal_sar`: Search and rescue scenario with thermal hotspots.
25. `minipro_motor_test`: Motor dynamometer bench world.
26. `moving_platform`: Dynamic moving landing platform test world.
27. `walls`: Maze-like partitioned rooms with drywall barriers.
28. `windy`: Atmospheric turbulence and dynamic wind simulation.

## 2. Supported Vehicle Models & Payload Capabilities

| Model Name | Display Name | Sensor / Accessories | Max Balls | Camera? | Spray? | Sys-Autostart |
|---|---|---|---|---|---|---|
| `x500_livox_mid_360` | Drone x500 Livox Mid 360 | 3D Livox Mid-360 LiDAR | 0 | No | No | 4001 |
| `x500_tennis_balls_no_cam` | Drone x500 Firefighting Balls | Tennis ball dropper | 5 | No | No | 4001 |
| `x500_tennis_balls` | Drone x500 Firefighting Cam | Dropper + Mono Cam | 5 | Yes | No | 4001 |
| `x500_gimbal` | Drone x500 Gimbal | 3-Axis Gimbal Camera | 0 | Yes | No | 4019 |
| `x500_mono_cam` | Drone x500 Mono Camera | Fixed Forward Camera | 0 | Yes | No | 4001 |
| `x500_depth_camera_D435` | Drone x500 Depth Cam D435 | Intel RealSense D435 | 0 | Yes | No | 4001 |
| `x500_thermal_camera` | Drone x500 Thermal Camera | FLIR Vue Pro R Thermal | 0 | Yes | No | 4001 |
| `x500_spray` | Drone x500 Nozzle System | Agricultural Spray Nozzle | 0 | Yes | Yes | 4027 |
| `x500_groundtruth` | Drone x500 Ground Truth | Ideal GPS/Odometry | 0 | No | No | 4024 |
| `x500_flow` | Drone x500 Optical Flow | Downward PMW3901 Flow | 0 | No | No | 4021 |
| `x500` | Drone x500 Base | Bare Quadcopter Frame | 0 | No | No | 4001 |

## 3. Mission Action Types Supported

- `navigate` (`data: [x, y, z]`): Waypoint navigation in local ENU meters.
- `drop-ball`: Triggers servo release on ball dropper payload.
- `take-snapshot`: Captures a high-resolution still image from the active camera.
- `start-recording-video`: Begins video stream capture to `.mp4`.
- `stop-recording-video`: Finalizes and saves active video recording.
- `start-spraying`: Opens solenoid valve on nozzle spray system.
- `stop-spraying`: Closes solenoid valve on nozzle spray system.
- `break-rtl`: Failsafe action returning to launch point if triggered.
- `break-land`: Failsafe action initiating emergency landing if triggered.
- `ai-flow`: Onboard edge neural network target detection with branching `then`/`else` actions.
- `rtl`: Return to Launch sequence and autonomous landing.
- `land`: Immediate vertical touchdown sequence.
