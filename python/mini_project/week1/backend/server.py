from flask import Flask, jsonify, render_template, send_from_directory
import os
import random

# 프로젝트 루트 폴더 기준 경로 설정
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')

app = Flask(__name__, static_folder=FRONTEND_DIR, template_folder=FRONTEND_DIR)

@app.route('/')
def index():
    return send_from_directory(FRONTEND_DIR, 'index.html')

# 정적 파일(css, js) 매핑을 위한 라우팅
@app.route('/<path:path>')
def send_static(path):
    return send_from_directory(FRONTEND_DIR, path)

# AutoCar PrimeX 상태 데이터를 내려주는 모킹 API
@app.route('/api/telemetry')
def get_telemetry():
    # 보여주기 용도로 매번 요청 시마다 값이 조금씩 변하게 설정
    mock_data = {
        "device_info": {
            "model": "AutoCar PrimeX",
            "manufacturer": "Hanback Electronics",
            "status": "Connected"
        },
        "sensors": {
            "lidar_distance": round(random.uniform(1.2, 4.5), 2),
            "ultrasonic_front": random.randint(20, 150),
            "ultrasonic_rear": random.randint(50, 200),
            "imu_yaw": round(random.uniform(-180, 180), 1),
            "battery": random.randint(75, 98)
        },
        "drive_info": {
            "speed": random.randint(0, 45),
            "steering_angle": random.randint(-30, 30),
            "gear": random.choice(["D", "N", "R", "P"])
        }
    }
    return jsonify(mock_data)

if __name__ == '__main__':
    app.run(debug=True)