"""Crop Disease & Pest Hotspot Survey - Autonomous UAV Mission Script.

World: farm-petersburg
Vehicle: x500_mono_cam (Multispectral / High-Resolution RGB Monocular Camera)
Survey Altitude: 30.0m AGL (Ground Sampling Distance < 1.2 cm/px)
Field Coverage: ~23 Hectares (82 survey waypoints, 19 diagnostic hotspot snapshot triggers)
"""

from typing import Any, Iterator
from local_planner import (
    boot_drone,
    takeoff,
    fly_to,
    capture,
    brake,
    land,
)


def scenario(ctx: Any) -> Iterator[Any]:
    # Phase 1: Takeoff to initial altitude and climb to survey altitude
    yield takeoff(alt_m=2.5)
    yield fly_to(north=320.922, east=-205.306, alt_m=30.0, target_speed=2.0, name="climb_survey_alt")
    yield brake()

    # Phase 2: Systematic Boustrophedon / Zigzag survey grid covering entire crop field
    yield fly_to(north=264.366, east=148.563, alt_m=30.0, target_speed=5.0, name="wp_1")
    yield capture(filename="crop_hotspot_diag_01.jpg", name="capture_hotspot_1")
    yield fly_to(north=264.366, east=210.089, alt_m=30.0, target_speed=5.0, name="wp_2")
    yield fly_to(north=275.866, east=213.122, alt_m=30.0, target_speed=5.0, name="wp_3")
    yield fly_to(north=275.866, east=63.289, alt_m=30.0, target_speed=5.0, name="wp_4")
    yield capture(filename="crop_hotspot_diag_02.jpg", name="capture_hotspot_2")
    yield fly_to(north=287.366, east=-21.985, alt_m=30.0, target_speed=5.0, name="wp_5")
    yield fly_to(north=287.366, east=216.154, alt_m=30.0, target_speed=5.0, name="wp_6")
    yield fly_to(north=298.866, east=219.187, alt_m=30.0, target_speed=5.0, name="wp_7")
    yield fly_to(north=298.866, east=-107.260, alt_m=30.0, target_speed=5.0, name="wp_8")
    yield capture(filename="crop_hotspot_diag_03.jpg", name="capture_hotspot_3")
    yield fly_to(north=310.366, east=-163.869, alt_m=30.0, target_speed=5.0, name="wp_9")
    yield fly_to(north=310.366, east=222.220, alt_m=30.0, target_speed=5.0, name="wp_10")
    yield capture(filename="crop_hotspot_diag_04.jpg", name="capture_hotspot_4")
    yield fly_to(north=321.866, east=225.253, alt_m=30.0, target_speed=5.0, name="wp_11")
    yield fly_to(north=321.866, east=-165.530, alt_m=30.0, target_speed=5.0, name="wp_12")
    yield fly_to(north=333.366, east=-167.191, alt_m=30.0, target_speed=5.0, name="wp_13")
    yield capture(filename="crop_hotspot_diag_05.jpg", name="capture_hotspot_5")
    yield fly_to(north=333.366, east=228.286, alt_m=30.0, target_speed=5.0, name="wp_14")
    yield fly_to(north=344.866, east=231.319, alt_m=30.0, target_speed=5.0, name="wp_15")
    yield fly_to(north=344.866, east=-168.852, alt_m=30.0, target_speed=5.0, name="wp_16")
    yield capture(filename="crop_hotspot_diag_06.jpg", name="capture_hotspot_6")
    yield fly_to(north=356.366, east=-170.513, alt_m=30.0, target_speed=5.0, name="wp_17")
    yield fly_to(north=356.366, east=234.352, alt_m=30.0, target_speed=5.0, name="wp_18")
    yield fly_to(north=367.866, east=237.385, alt_m=30.0, target_speed=5.0, name="wp_19")
    yield capture(filename="crop_hotspot_diag_07.jpg", name="capture_hotspot_7")
    yield fly_to(north=367.866, east=-172.173, alt_m=30.0, target_speed=5.0, name="wp_20")
    yield fly_to(north=379.366, east=-173.834, alt_m=30.0, target_speed=5.0, name="wp_21")
    yield fly_to(north=379.366, east=240.417, alt_m=30.0, target_speed=5.0, name="wp_22")
    yield fly_to(north=390.866, east=243.450, alt_m=30.0, target_speed=5.0, name="wp_23")
    yield fly_to(north=390.866, east=-175.495, alt_m=30.0, target_speed=5.0, name="wp_24")
    yield fly_to(north=402.366, east=-177.156, alt_m=30.0, target_speed=5.0, name="wp_25")
    yield capture(filename="crop_hotspot_diag_08.jpg", name="capture_hotspot_8")
    yield fly_to(north=402.366, east=246.483, alt_m=30.0, target_speed=5.0, name="wp_26")
    yield fly_to(north=413.866, east=249.516, alt_m=30.0, target_speed=5.0, name="wp_27")
    yield fly_to(north=413.866, east=-178.817, alt_m=30.0, target_speed=5.0, name="wp_28")
    yield fly_to(north=425.366, east=-180.477, alt_m=30.0, target_speed=5.0, name="wp_29")
    yield capture(filename="crop_hotspot_diag_09.jpg", name="capture_hotspot_9")
    yield fly_to(north=425.366, east=252.549, alt_m=30.0, target_speed=5.0, name="wp_30")
    yield fly_to(north=436.866, east=255.582, alt_m=30.0, target_speed=5.0, name="wp_31")
    yield fly_to(north=436.866, east=-182.138, alt_m=30.0, target_speed=5.0, name="wp_32")
    yield capture(filename="crop_hotspot_diag_10.jpg", name="capture_hotspot_10")
    yield fly_to(north=448.366, east=-183.799, alt_m=30.0, target_speed=5.0, name="wp_33")
    yield fly_to(north=448.366, east=258.615, alt_m=30.0, target_speed=5.0, name="wp_34")
    yield fly_to(north=459.866, east=261.647, alt_m=30.0, target_speed=5.0, name="wp_35")
    yield fly_to(north=459.866, east=-185.460, alt_m=30.0, target_speed=5.0, name="wp_36")
    yield fly_to(north=471.366, east=-187.121, alt_m=30.0, target_speed=5.0, name="wp_37")
    yield capture(filename="crop_hotspot_diag_11.jpg", name="capture_hotspot_11")
    yield fly_to(north=471.366, east=264.680, alt_m=30.0, target_speed=5.0, name="wp_38")
    yield fly_to(north=482.866, east=267.713, alt_m=30.0, target_speed=5.0, name="wp_39")
    yield fly_to(north=482.866, east=-188.781, alt_m=30.0, target_speed=5.0, name="wp_40")
    yield fly_to(north=494.366, east=-190.442, alt_m=30.0, target_speed=5.0, name="wp_41")
    yield fly_to(north=494.366, east=270.746, alt_m=30.0, target_speed=5.0, name="wp_42")
    yield capture(filename="crop_hotspot_diag_12.jpg", name="capture_hotspot_12")
    yield fly_to(north=505.866, east=273.779, alt_m=30.0, target_speed=5.0, name="wp_43")
    yield fly_to(north=505.866, east=-192.103, alt_m=30.0, target_speed=5.0, name="wp_44")
    yield fly_to(north=517.366, east=-193.764, alt_m=30.0, target_speed=5.0, name="wp_45")
    yield fly_to(north=517.366, east=276.812, alt_m=30.0, target_speed=5.0, name="wp_46")
    yield fly_to(north=528.866, east=279.845, alt_m=30.0, target_speed=5.0, name="wp_47")
    yield capture(filename="crop_hotspot_diag_13.jpg", name="capture_hotspot_13")
    yield fly_to(north=528.866, east=-195.425, alt_m=30.0, target_speed=5.0, name="wp_48")
    yield fly_to(north=540.366, east=-197.085, alt_m=30.0, target_speed=5.0, name="wp_49")
    yield fly_to(north=540.366, east=282.878, alt_m=30.0, target_speed=5.0, name="wp_50")
    yield fly_to(north=551.866, east=285.910, alt_m=30.0, target_speed=5.0, name="wp_51")
    yield fly_to(north=551.866, east=-198.746, alt_m=30.0, target_speed=5.0, name="wp_52")
    yield fly_to(north=563.366, east=-200.407, alt_m=30.0, target_speed=5.0, name="wp_53")
    yield capture(filename="crop_hotspot_diag_14.jpg", name="capture_hotspot_14")
    yield fly_to(north=563.366, east=288.943, alt_m=30.0, target_speed=5.0, name="wp_54")
    yield fly_to(north=574.866, east=283.081, alt_m=30.0, target_speed=5.0, name="wp_55")
    yield fly_to(north=574.866, east=-202.068, alt_m=30.0, target_speed=5.0, name="wp_56")
    yield fly_to(north=586.366, east=-203.729, alt_m=30.0, target_speed=5.0, name="wp_57")
    yield fly_to(north=586.366, east=265.177, alt_m=30.0, target_speed=5.0, name="wp_58")
    yield fly_to(north=597.866, east=247.273, alt_m=30.0, target_speed=5.0, name="wp_59")
    yield capture(filename="crop_hotspot_diag_15.jpg", name="capture_hotspot_15")
    yield fly_to(north=597.866, east=-205.390, alt_m=30.0, target_speed=5.0, name="wp_60")
    yield fly_to(north=609.366, east=-207.050, alt_m=30.0, target_speed=5.0, name="wp_61")
    yield fly_to(north=609.366, east=229.370, alt_m=30.0, target_speed=5.0, name="wp_62")
    yield fly_to(north=620.866, east=211.466, alt_m=30.0, target_speed=5.0, name="wp_63")
    yield fly_to(north=620.866, east=-208.711, alt_m=30.0, target_speed=5.0, name="wp_64")
    yield capture(filename="crop_hotspot_diag_16.jpg", name="capture_hotspot_16")
    yield fly_to(north=632.366, east=-210.372, alt_m=30.0, target_speed=5.0, name="wp_65")
    yield fly_to(north=632.366, east=193.562, alt_m=30.0, target_speed=5.0, name="wp_66")
    yield fly_to(north=643.866, east=175.658, alt_m=30.0, target_speed=5.0, name="wp_67")
    yield fly_to(north=643.866, east=-212.033, alt_m=30.0, target_speed=5.0, name="wp_68")
    yield fly_to(north=655.366, east=-190.618, alt_m=30.0, target_speed=5.0, name="wp_69")
    yield fly_to(north=655.366, east=157.755, alt_m=30.0, target_speed=5.0, name="wp_70")
    yield fly_to(north=666.866, east=139.851, alt_m=30.0, target_speed=5.0, name="wp_71")
    yield capture(filename="crop_hotspot_diag_17.jpg", name="capture_hotspot_17")
    yield fly_to(north=666.866, east=-156.500, alt_m=30.0, target_speed=5.0, name="wp_72")
    yield fly_to(north=678.366, east=-122.382, alt_m=30.0, target_speed=5.0, name="wp_73")
    yield fly_to(north=678.366, east=121.947, alt_m=30.0, target_speed=5.0, name="wp_74")
    yield fly_to(north=689.866, east=104.044, alt_m=30.0, target_speed=5.0, name="wp_75")
    yield fly_to(north=689.866, east=-88.265, alt_m=30.0, target_speed=5.0, name="wp_76")
    yield fly_to(north=701.366, east=-54.147, alt_m=30.0, target_speed=5.0, name="wp_77")
    yield capture(filename="crop_hotspot_diag_18.jpg", name="capture_hotspot_18")
    yield fly_to(north=701.366, east=86.140, alt_m=30.0, target_speed=5.0, name="wp_78")
    yield fly_to(north=712.866, east=68.236, alt_m=30.0, target_speed=5.0, name="wp_79")
    yield fly_to(north=712.866, east=-20.030, alt_m=30.0, target_speed=5.0, name="wp_80")
    yield fly_to(north=724.366, east=14.088, alt_m=30.0, target_speed=5.0, name="wp_81")
    yield fly_to(north=724.366, east=50.333, alt_m=30.0, target_speed=5.0, name="wp_82")
    yield capture(filename="crop_hotspot_diag_19.jpg", name="capture_hotspot_19")

    # Phase 3: Failsafe Return to Launch (RTL) & Precision Landing
    yield fly_to(north=320.922, east=-205.306, alt_m=30.0, target_speed=4.0, name="rtl_ingress")
    yield fly_to(north=320.922, east=-205.306, alt_m=2.5, target_speed=1.5, name="descend_home")
    yield brake()
    yield land()


scenario.requires_senses = ["pose", "obstacle", "status"]


def main() -> None:
    with boot_drone() as drone:
        drone.fly(scenario)
        drone.run()


if __name__ == "__main__":
    main()
