document.addEventListener("DOMContentLoaded", () => {
    // 1초마다 백엔드로부터 가상 차량 정보 데이터를 패치
    setInterval(updateTelemetry, 1000);
    updateTelemetry(); // 최초 1회 즉시 실행
});

function updateTelemetry() {
    fetch('/api/telemetry')
        .then(response => response.json())
        .then(data => {
            // 장치 정보 매핑
            document.getElementById('info-manufacturer').innerText = data.device_info.manufacturer;
            document.getElementById('info-model').innerText = data.device_info.model;
            document.getElementById('info-status').innerText = data.device_info.status;

            // 주행 상태 매핑
            document.getElementById('drive-speed').innerText = data.drive_info.speed;
            document.getElementById('drive-steering').innerText = data.drive_info.steering_angle;
            document.getElementById('drive-gear').innerText = data.drive_info.gear;

            // 센서 데이터 매핑
            document.getElementById('sensor-lidar').innerText = data.sensors.lidar_distance;
            document.getElementById('sensor-ultra-front').innerText = data.sensors.ultrasonic_front;
            document.getElementById('sensor-ultra-rear').innerText = data.sensors.ultrasonic_rear;
            document.getElementById('sensor-imu').innerText = data.sensors.imu_yaw;

            // 배터리 UI 매핑
            const batteryBar = document.getElementById('battery-level-bar');
            const batteryText = document.getElementById('battery-text');
            batteryBar.style.width = data.sensors.battery + '%';
            batteryText.innerText = data.sensors.battery + '%';
        })
        .catch(error => {
            console.error("데이터 로드 실패:", error);
        });
}