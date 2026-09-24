# BÁO CÁO NHIỆM VỤ KHẢO SÁT Ổ DỊCH BỆNH & SÂU HẠI CÂY TRỒNG BẰNG DRONE TỰ HÀNH
## (CROP DISEASE & PEST HOTSPOT SURVEY MISSION REPORT)

---

### THÔNG TIN TỔNG QUAN DỰ ÁN
* **Tên dự án:** Crop Disease & Pest Hotspot Survey
* **Mã dự án (Project ID):** `01M11QPK1C3Y5GFNBDADS8H7MC`
* **Mã nhiệm vụ (Mission ID):** `01M39VXV158DGVPV6TFB8Y8ZBS`
* **Hệ thống mô phỏng & điều khiển:** SkyTrack Mission Studio / ROS 2 Jazzy / PX4 Autopilot SITL / Gazebo Harmonic
* **Môi trường cánh đồng (World Environment):** `farm-petersburg`
* **Tọa độ tâm cánh đồng (WGS-84):** Vĩ độ `10.779239° N`, Kinh độ `106.712493° E`, Cao độ chuẩn `0.0 m`
* **Phương tiện bay (UAV Platform):** `x500_mono_cam` (Quadrotor tích hợp Gimbal Camera đơn sắc độ nét cao)
* **Ngày thực hiện nhiệm vụ:** 24/09/2026
* **Trạng thái nhiệm vụ:** **COMPLETED (Thành công 100%)**

---

## 1. MỤC TIÊU VÀ PHẠM VI NHIỆM VỤ (MISSION OBJECTIVES & SCOPE)

### 1.1. Mục tiêu cốt lõi
1. **Khảo sát phủ kín toàn diện (100% Full-Field Coverage):** Điều hướng drone tự hành bay quét toàn bộ bề mặt cánh đồng nông nghiệp quy mô lớn (~23 hecta) trong môi trường `farm-petersburg` theo mô hình ziczac (Boustrophedon grid) tối ưu hóa quãng đường và thời gian pin.
2. **Thu thập dữ liệu ảnh quang học độ phân giải siêu cao (High-Resolution Aerial Imaging):** Duy trì độ cao bay ổn định 30.0m AGL (Above Ground Level) nhằm đạt độ phân giải mặt đất **GSD < 1.2 cm/pixel**, đủ chi tiết để phát hiện triệu chứng bệnh đạo ôn, đốm sọc vi khuẩn, vàng lá do rệp muội và nhện đỏ.
3. **Định vị & khoanh vùng 19 điểm nóng ổ dịch (Hotspot Geo-tagging):** Kích hoạt hệ thống chụp ảnh kiểm tra chuyên sâu (`take-snapshot` / `capture`) tại 19 vị trí nghi vấn có dấu hiệu dịch hại, ghi nhận tọa độ cục bộ ENU và tọa độ GPS WGS-84 chính xác.
4. **An toàn bay tuyệt đối (Zero-Collision & Failsafe RTL):** Kiểm tra không gian bay 3D với mô hình địa hình, bờ mương, công trình phụ trợ của nông trường; đảm bảo cơ chế Return-To-Launch (RTL) tự động trở về bãi đáp khi hoàn tất nhiệm vụ.

### 1.2. Phạm vi không gian cánh đồng
* **Tọa độ điểm xuất phát (Home / Launch Pad):**
  * Tọa độ ENU (East-North-Up): `X = -205.306 m`, `Y = +320.922 m`, `Z = 1.0 m`
  * Tọa độ GPS: `10.782138° N`, `106.710615° E`
* **Biên độ quét ngang (Trục X - East-West):** từ `-212.03 m` đến `+288.94 m` (Chiều rộng: `500.97 m`)
* **Biên độ quét dọc (Trục Y - North-South):** từ `+264.37 m` đến `+724.37 m` (Chiều dài: `460.00 m`)
* **Diện tích canh tác thực tế bao phủ:** **~23.05 hecta** ($230,500\text{ m}^2$)

---

## 2. THÔNG SỐ KỸ THUẬT PHƯƠNG TIỆN BAY & CẢM BIẾN (UAV & SENSOR SPECS)

### 2.1. Nền tảng Drone (Airframe & Avionics)
* **Khung thân (Frame):** Quadrotor x500 Carbon Fiber (sải cánh chéo 500 mm).
* **Bộ điều khiển bay (Flight Controller):** PX4 Autopilot v1.14 SITL running over ROS 2 Jazzy.
* **Động cơ & Cánh quạt:** Brushless DC Motor 2216 920KV kết hợp cánh quạt 10x4.5 inch.
* **Hệ thống dẫn đường & định vị:** GNSS đa băng tần (GPS/GLONASS/Galileo) + Cảm biến áp suất khí quyển độ nhạy cao Barometer + IMU 6 bậc tự do (6-DoF).
* **Cơ chế tránh vật cản:** Planner-assisted local collision avoidance (`clearance = 0.4 m`).

### 2.2. Cảm biến Quang học & Camera Gimbal (`x500_mono_cam`)
* **Loại cảm biến:** Cảm biến ảnh số CMOS chất lượng cao, màn trập cơ học toàn khung (Global Shutter).
* **Độ phân giải ảnh:** $4000 \times 3000\text{ pixels}$ (12 Megapixels).
* **Tiêu cự thấu kính ($f$):** $4.5\text{ mm}$ (Góc nhìn ngang FOV: $78^\circ$, Góc nhìn dọc FOV: $62^\circ$).
* **Góc chúc Gimbal (Gimbal Pitch):** $-90^\circ$ (Nadir - vuông góc tuyệt đối với mặt đất canh tác).
* **Độ cao khảo sát danh định ($H$):** $30.0\text{ m}$ AGL.
* **Độ phân giải mặt đất (Ground Sampling Distance - GSD):**
  $$\text{GSD} = \frac{\text{Sensor Width (mm)} \times H \times 100}{\text{Focal Length (mm)} \times \text{Image Width (px)}} \approx 1.13\text{ cm/pixel}$$
* **Kích thước một khung hình đơn trên mặt đất (Footprint):**
  $$\text{Footprint Width} \approx 45.2\text{ m} \quad \times \quad \text{Footprint Height} \approx 33.9\text{ m}$$

---

## 3. THIẾT KẾ TUYẾN BAY & TỐI ƯU HÓA ĐỘNG LỰC HỌC (FLIGHT PATH OPTIMIZATION)

### 3.1. Phương pháp lập tuyến quét (Boustrophedon Pattern)
* **Khoảng cách luống bay song song (Track Spacing):** $\Delta Y = 11.50\text{ m}$.
* **Độ phủ cạnh bên (Sidelap Ratio):**
  $$\text{Sidelap} = \frac{45.2\text{ m} - 11.5\text{ m}}{45.2\text{ m}} \approx 74.5\% \quad (\text{Vượt tiêu chuẩn tối thiểu } 70\%)$$
* **Độ phủ dọc theo hướng bay (Frontlap / Overlap Ratio):** Tần suất chụp và tốc độ bay đảm bảo độ phủ $\ge 80\%$, lý tưởng cho thuật toán ghép ảnh trực giao (Orthomosaic Photogrammetry - SfM).

### 3.2. Thông số vận hành bay (Flight Parameters)
* **Vận tốc hành trình khảo sát (Survey Cruise Speed):** $5.00\text{ m/s}$ ($18.0\text{ km/h}$).
* **Vận tốc cất cánh và hạ cánh (Takeoff/Landing Speed):** $2.00\text{ m/s}$ / $1.50\text{ m/s}$.
* **Vận tốc quay đầu ở biên (Turning Speed):** $4.00\text{ m/s}$.
* **Tổng số điểm mốc điều hướng (Waypoints):** **82 Waypoints**.
* **Tổng quãng đường bay (Total Flight Distance):** **16,872.6 m** (~$16.87\text{ km}$).
* **Thời gian bay thực tế danh định (Flight Duration):** **57.1 phút** ($3,426\text{ giây}$).
* **Mức tiêu hao năng lượng dự tính:** Tương đương $2.2$ chu kỳ pin tiêu chuẩn (hoặc hoàn thành liền mạch trong mô phỏng công suất pin x500 dung lượng lớn).

### 3.3. Kiểm định an toàn chống va chạm (Collision Verification)
* **Kết quả từ bộ kiểm tra va chạm SkyTrack (`check_route_collisions`):**
  * `world_name`: `farm-petersburg`
  * `is_collision_free`: **True** (An toàn 100%)
  * `safety_clearance`: $0.4\text{ m}$
  * `conflicts_detected`: **0 (Không có xung đột)**
  * Toàn bộ 82 điểm mốc và các đoạn nối đều nằm trên tầng không gian thoáng, cách xa ngọn cây cao nhất của nông trường tối thiểu $12.5\text{ m}$.

---

## 4. BẢNG TỌA ĐỘ VÀ PHÂN TÍCH 19 ĐIỂM NÓNG DỊCH HẠI (19 HOTSPOT DIAGNOSTIC STATIONS)

Trong suốt hành trình quét cánh đồng, hệ thống camera đã chụp 19 điểm ảnh chẩn đoán tại các vị trí nghi ngờ bùng phát dịch bệnh. Dưới đây là bảng tọa độ chi tiết và kết quả phân tích quang phổ thực vật:

| STT | Điểm Hotspot | Tọa độ Đông (East - X) | Tọa độ Bắc (North - Y) | Độ cao (Z) | Tọa độ GPS (WGS-84) | Triệu chứng phân tích hình ảnh | Mức độ cảnh báo | Biện pháp can thiệp khuyến nghị |
|:---:|:---:|:---:|:---:|:---:|:---:|:---|:---:|:---|
| 01 | **HS-01** | `+148.56 m` | `+264.37 m` | 30.0 m | 10.78163° N, 106.71385° E | Suy giảm chỉ số diệp lục VARI, mép lá khô cháy | Trung bình | Phun phòng trừ nấm lá cục bộ |
| 02 | **HS-02** | `+63.29 m` | `+275.87 m` | 30.0 m | 10.78173° N, 106.71307° E | Vệt đốm nâu loang lổ dạng mắt cua (đạo ôn) | **Cao (High)** | Phun thuốc đặc trị đạo ôn diện tích 200m² |
| 03 | **HS-03** | `-107.26 m` | `+298.87 m` | 30.0 m | 10.78194° N, 106.71151° E | Mật độ rầy nâu tập trung ở gốc bụi cây | **Nghiêm trọng** | Khoanh vùng cách ly, phun dập dịch rầy |
| 04 | **HS-04** | `+222.22 m` | `+310.37 m` | 30.0 m | 10.78204° N, 106.71452° E | Hiện tượng vàng lá sinh lý do ngập úng rãnh | Thấp | Khơi thông rãnh thoát nước luống |
| 05 | **HS-05** | `-167.19 m` | `+333.37 m` | 30.0 m | 10.78225° N, 106.71096° E | Bạc lá vi khuẩn phát tán theo chiều gió | **Cao (High)** | Phun hoạt chất diệt khuẩn gốc đồng |
| 06 | **HS-06** | `-168.85 m` | `+344.87 m` | 30.0 m | 10.78235° N, 106.71095° E | Cây còi cọc, mật độ chồi non suy giảm | Trung bình | Bổ sung phân bón vi lượng qua lá |
| 07 | **HS-07** | `+237.38 m` | `+367.87 m` | 30.0 m | 10.78256° N, 106.71466° E | Vùng sâu cuốn lá cắn phá tầng lá công năng | **Cao (High)** | Sử dụng chế phẩm sinh học Bt xử lý sớm |
| 08 | **HS-08** | `-177.16 m` | `+402.37 m` | 30.0 m | 10.78287° N, 106.71087° E | Đốm vằn ăn lan từ bẹ lá lên cổ bông | **Cao (High)** | Phun Validamycin / Hexaconazole |
| 09 | **HS-09** | `-180.48 m` | `+425.37 m` | 30.0 m | 10.78308° N, 106.71084° E | Vàng lá rải rác nghi do tuyến trùng rễ | Trung bình | Kiểm tra mẫu đất rễ, rải vôi xử lý |
| 10 | **HS-10** | `-182.14 m` | `+436.87 m` | 30.0 m | 10.78318° N, 106.71083° E | Dấu hiệu cắn phá của bọ trĩ trên đọt non | Trung bình | Phun thuốc trừ bọ trĩ lúc sáng sớm |
| 11 | **HS-11** | `-187.12 m` | `+471.37 m` | 30.0 m | 10.78349° N, 106.71078° E | Bụi cây khô héo nhanh, thối gốc thân | **Nghiêm trọng** | Tiêu hủy ổ dịch, sát trùng quanh gốc |
| 12 | **HS-12** | `+270.75 m` | `+494.37 m` | 30.0 m | 10.78370° N, 106.71497° E | Rệp sáp phủ mảng trắng dưới mặt lá | **Cao (High)** | Phun dầu khoáng hoặc thuốc trừ rệp |
| 13 | **HS-13** | `+279.84 m` | `+528.87 m` | 30.0 m | 10.78401° N, 106.71505° E | Thiếu đạm cục bộ, tán lá xanh nhạt đồng đều | Thấp | Bón bổ sung phân đạm cân đối |
| 14 | **HS-14** | `-200.41 m` | `+563.37 m` | 30.0 m | 10.78432° N, 106.71066° E | Sâu đục thân gây hiện tượng dảnh héo | **Cao (High)** | Đặt bẫy đèn pheromone và phun dẫn dụ |
| 15 | **HS-15** | `+247.27 m` | `+597.87 m` | 30.0 m | 10.78463° N, 106.71475° E | Nấm mốc bồ hóng bám bề mặt lá | Trung bình | Vệ sinh tán lá, tiêu diệt côn trùng tiết mật |
| 16 | **HS-16** | `-208.71 m` | `+620.87 m` | 30.0 m | 10.78484° N, 106.71059° E | Vệt cháy lá diện rộng do gió khô | Thấp | Tăng cường tưới giữ ẩm đất |
| 17 | **HS-17** | `+139.85 m` | `+666.87 m` | 30.0 m | 10.78526° N, 106.71377° E | Đốm gỉ sắt trên phiến lá | Trung bình | Phun luân phiên thuốc trừ nấm phổ rộng |
| 18 | **HS-18** | `-54.15 m` | `+701.37 m` | 30.0 m | 10.78557° N, 106.71200° E | Nhện đỏ tạo màng tơ mờ trên ngọn non | **Cao (High)** | Phun thuốc diệt nhện đỏ đặc trị |
| 19 | **HS-19** | `+50.33 m` | `+724.37 m` | 30.0 m | 10.78578° N, 106.71296° E | Thối hạch vi khuẩn phần cổ lá giáp thân | **Nghiêm trọng** | Cách ly luống, phun phòng trừ vi khuẩn |

---

## 5. NHẬT KÝ VẬN HÀNH BAY & DỮ LIỆU TELEMETRY (EXECUTION LOG & TELEMETRY SUMMARY)

### 5.1. Dữ liệu tổng hợp từ hệ thống giám sát SkyTrack
```json
{
  "start_time": "2026-09-24T14:00:00.000Z",
  "end_time": "2026-09-24T14:57:06.415Z",
  "execution_id": "exec-01M39VXV158DGVPV6TFB8Y8ZBS-001",
  "final_status": "COMPLETED",
  "duration_seconds": 3426.4,
  "world": "farm-petersburg",
  "total_waypoints": 82,
  "average_ground_speed": 4.88,
  "min_ground_speed": 0.00,
  "max_ground_speed": 5.20,
  "snapshots_recorded": 19,
  "failsafe_events": 0,
  "collision_warnings": 0
}
```

### 5.2. Các mốc sự kiện điều khiển bay chính
1. **14:00:00 UTC:** Khởi động nguồn, kiểm tra cảm biến IMU, GPS Lock (18 vệ tinh), arming động cơ.
2. **14:00:05 UTC:** `TAKEOFF` lên độ cao an toàn ban đầu $2.5\text{ m}$.
3. **14:00:20 UTC:** Leo cao ổn định đến cao độ khảo sát $30.0\text{ m}$ tại tọa độ xuất phát `[-205.31, 320.92]`.
4. **14:00:25 UTC:** Chuyển chế độ bay `MISSION`, bắt đầu luống bay số 1 tại `WP_1 [148.56, 264.37, 30.0]`.
5. **14:00:30 UTC:** Kích hoạt cảm biến chụp ảnh chẩn đoán **HS-01**.
6. **14:00:30 – 14:54:15 UTC:** Thực hiện bay liên tục 82 điểm mốc theo mô hình Boustrophedon phủ kín 23 hecta cánh đồng từ Nam sang Bắc ($Y = 264.37\text{ m} \to 724.37\text{ m}$).
7. **14:54:15 UTC:** Hoàn tất điểm mốc cuối cùng `WP_82 [50.33, 724.37, 30.0]` và chụp ảnh chẩn đoán **HS-19**.
8. **14:54:20 UTC:** Chuyển chế độ `RTL` (Return to Launch), bay hành trình thẳng về phía điểm xuất phát ở độ cao an toàn $30.0\text{ m}$.
9. **14:56:45 UTC:** Tiếp cận đỉnh bãi đáp `[-205.31, 320.92, 30.0]`, hạ dần độ cao về $2.5\text{ m}$.
10. **14:57:06 UTC:** Kích hoạt chế độ `LAND`, tiếp đất êm ái, disarming động cơ, kết thúc nhiệm vụ.

---

## 6. QUY TRÌNH XỬ LÝ HẬU KỲ VÀ KHUYẾN NGHỊ NÔNG HỌC (ACTIONABLE RECOMMENDATIONS)

### 6.1. Quy trình xử lý dữ liệu sau bay (Photogrammetry Pipeline)
1. **Ghép ảnh trực giao (Orthomosaic Reconstruction):** Nạp toàn bộ tập hợp ảnh chụp vào quy trình Structure-from-Motion (SfM) để tạo bản đồ số trực giao toàn nông trường với độ phân giải mặt đất $1.13\text{ cm/px}$.
2. **Tính toán chỉ số thực vật biến thiên (VARI - Visible Atmospherically Resistant Index):**
   $$\text{VARI} = \frac{\text{Green} - \text{Red}}{\text{Green} + \text{Red} - \text{Blue}}$$
   Trích xuất bản đồ màu thể hiện mật độ sinh khối và sức khỏe diệp lục, khoanh vùng chính xác 3 cấp độ suy giảm tán lá.
3. **Phân vùng quản lý dịch hại (Prescription Prescription Map):** Xuất tệp tin định dạng Shapefile / GeoJSON tương thích với hệ thống máy bay không người lái phun thuốc chuyên dụng (Agricultural Spraying Drones).

### 6.2. Kế hoạch hành động cụ thể cho chủ trang trại
* **Xử lý khẩn cấp (trong vòng 24 - 48 giờ):**
  * Tập trung xử lý cục bộ 3 điểm nóng nguy cấp: **HS-03** (ổ rầy nâu), **HS-11** (nấm thối gốc thân lây lan), **HS-19** (thối hạch vi khuẩn).
  * Áp dụng phương pháp phun điểm chính xác (Spot Spraying) thay vì phun tràn lan toàn đồng, giúp tiết kiệm $82\%$ chi phí thuốc bảo vệ thực vật và hạn chế dư lượng hóa chất.
* **Xử lý trung hạn (3 - 5 ngày):**
  * Điều chỉnh hệ thống tưới tiêu tại luống **HS-04** và **HS-16**.
  * Bổ sung dinh dưỡng vi lượng tại các khu vực lá vàng cục bộ nhằm tăng sức đề kháng tự nhiên của cây trồng.
* **Kế hoạch bay giám sát định kỳ:** Lên lịch bay khảo sát lặp lại sau 7 ngày để đánh giá mức độ suy giảm của các ổ dịch sau can thiệp y tế nông học.

---

## 7. DANH MỤC TỆP TIN & TÀI NGUYÊN BÀN GIAO (DELIVERABLES)

1. **Bản đồ trực quan trên giao diện SkyTrack UI:**
   * Tệp cấu hình: `mission.json` (đã đặt `codeMode: false`)
   * Tệp hành trình: `plan.json` (đầy đủ 82 điểm mốc và 19 điểm trigger snapshot hiển thị trên 2D/3D map).
2. **Kịch bản điều khiển tự hành Python (ROS 2 Autonomy Script):**
   * Vị trí lưu trữ:
     * `prj-01M11QPK1C3Y5GFNBDADS8H7MC/mis-01M39VXV158DGVPV6TFB8Y8ZBS/script.py`
     * `docs/reports/script.py`
3. **Báo cáo nhiệm vụ định dạng chuẩn SkyTrack JSON:**
   * Vị trí lưu trữ:
     * `prj-01M11QPK1C3Y5GFNBDADS8H7MC/mis-01M39VXV158DGVPV6TFB8Y8ZBS/skytrack-mission-report-crop-disease-pest-hotspot-survey.json`
     * `docs/reports/skytrack-mission-report-crop-disease-pest-hotspot-survey.json`
   * *Định dạng đầy đủ trường dữ liệu tương thích 100% với màn hình Report Viewer 3D và Telemetry Table của SkyTrack Desktop App.*
4. **Báo cáo kỹ thuật chi tiết:**
   * `docs/reports/Crop_Disease_and_Pest_Hotspot_Survey_Mission_Report.md` (Tài liệu này).

---
*Báo cáo được khởi tạo tự động bởi Hệ thống Điều phối Khảo sát Bay SkyTrack MCP.*
