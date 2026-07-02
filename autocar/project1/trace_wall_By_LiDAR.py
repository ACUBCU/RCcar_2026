import threading, time, numpy as np, math, signal, sys
from flask import Flask, jsonify, request, render_template_string
from pop.Pilot import get_Control
from pop.LiDAR.rplidar import Rplidar

# 하드웨어 초기화
car = get_Control()
lidar = Rplidar()
lidar.connect("/dev/ttyUSB0")
lidar.startMotor()

# 상태 데이터
robot_pose = {'x': 0.0, 'y': 0.0, 'theta': 0.0}
collected_points = []
wall_following_active = False

# [튜닝 파라미터]
TARGET_DIST = 288    # 목표 거리 (mm)
TOLERANCE = 50       # 오차 허용 범위
SPEED = 40           # 요청하신 속도 40
DETECTION_LIMIT = 500 # 50cm(500mm) 이내의 벽만 인식

map_lock = threading.Lock()
stop_event = threading.Event()

# 종료 시 하드웨어 안전 정지 함수
def cleanup(signum, frame):
    print("\n[System] 종료 신호 감지. 하드웨어 정지 중...")
    stop_event.set()
    car.stop()
    lidar.stopMotor()
    lidar.destroy()
    sys.exit(0)

# Ctrl+C 신호 등록
signal.signal(signal.SIGINT, cleanup)

def control_loop():
    global robot_pose, collected_points, wall_following_active
    while not stop_event.is_set():
        coords = lidar.getXY()
        if coords is not None and len(coords) > 0:
            x, y = coords[:, 0], coords[:, 1]
            r = np.sqrt(x**2 + y**2)
            angle = np.degrees(np.arctan2(y, x))
            
            if wall_following_active:
                # 50cm 이내, -20도 ~ 60도 범위의 벽 탐지
                left_mask = (angle > -20) & (angle < 60) & (r < DETECTION_LIMIT)
                
                if np.any(left_mask):
                    min_dist = np.min(r[left_mask])
                    
                    # [강제 로직] 조향값을 고정치로 확실하게 명령
                    if min_dist < (TARGET_DIST - TOLERANCE):
                        # 벽에 가까움 -> 오른쪽 회피
                        target_steer = 0.5
                    elif min_dist > (TARGET_DIST + TOLERANCE):
                        # 벽에서 멂 -> 왼쪽 접근
                        target_steer = -0.5
                    else:
                        # 적정 거리 -> 직진
                        target_steer = 0.0
                    
                    car.steering = target_steer
                    car.forward(SPEED)
                    
                    # 로직 확인용 출력
                    print(f"Dist: {min_dist:.1f}mm | Steering: {car.steering}")
                else:
                    car.stop()
            
            # 매핑 데이터 누적
            theta_rad = math.radians(robot_pose['theta'])
            wx = x * np.cos(theta_rad) - y * np.sin(theta_rad) + robot_pose['x']
            wy = x * np.sin(theta_rad) + y * np.cos(theta_rad) + robot_pose['y']
            
            with map_lock:
                collected_points.extend(zip(wx.tolist(), wy.tolist()))
                if len(collected_points) > 20000: collected_points = collected_points[-20000:]
        
        time.sleep(0.05)

# Flask 설정
app = Flask(__name__)

@app.route("/")
def index():
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <body style="background:#222; color:white; text-align:center; font-family:sans-serif;">
        <h2>Wall Following (Range: 1m)</h2>
        <canvas id="globalMap" width="500" height="500" style="background:black; border:2px solid #555;"></canvas>
        <div style="margin:20px;">
            <button id="wallBtn" onclick="toggleWall()" style="padding:15px 30px; background:blue; font-size:18px;">Wall Follow: OFF</button>
            <button onclick="stopCar()" style="padding:15px 30px; background:red; font-size:18px; font-weight:bold;">STOP</button>
            <button onclick="resetMap()" style="padding:15px 30px; background:gray; font-size:18px;">Reset</button>
        </div>
        <script>
            let points = [], robot = {x:0, y:0, theta:0}, scale = 0.25, offX = 250, offY = 250;
            function toggleWall() {
                fetch('/toggle_wall', {method:'POST'}).then(r => r.json()).then(d => {
                    document.getElementById('wallBtn').style.background = d.active ? 'green' : 'blue';
                    document.getElementById('wallBtn').innerText = 'Wall Follow: ' + (d.active ? 'ON' : 'OFF');
                });
            }
            function stopCar() {
                fetch('/stop', {method:'POST'}).then(() => {
                    document.getElementById('wallBtn').style.background = 'blue';
                    document.getElementById('wallBtn').innerText = 'Wall Follow: OFF';
                });
            }
            function resetMap() { fetch('/reset', {method:'POST'}); }
            async function loop() {
                const res = await fetch('/data'); const data = await res.json();
                points = data.points; robot = data.pose;
                const ctx = document.getElementById('globalMap').getContext('2d');
                ctx.clearRect(0,0,500,500);
                
                ctx.strokeStyle = '#333';
                ctx.beginPath();
                ctx.moveTo(0, 250); ctx.lineTo(500, 250);
                ctx.moveTo(250, 0); ctx.lineTo(250, 500);
                ctx.stroke();

                points.forEach(p => {
                    ctx.fillStyle = 'white'; 
                    let px = (p[0] - robot.x) * scale + offX;
                    let py = (p[1] - robot.y) * scale + offY;
                    ctx.fillRect(px, py, 2, 2);
                });
                
                ctx.fillStyle = 'red'; 
                ctx.beginPath(); ctx.arc(offX, offY, 6, 0, 7); ctx.fill();
            }
            setInterval(loop, 200);
        </script>
    </body>
    </html>
    """)

@app.route("/toggle_wall", methods=["POST"])
def toggle():
    global wall_following_active
    wall_following_active = not wall_following_active
    return jsonify({"active": wall_following_active})

@app.route("/stop", methods=["POST"])
def stop():
    global wall_following_active
    wall_following_active = False
    car.stop()
    return jsonify({"status": "stopped"})

@app.route("/reset", methods=["POST"])
def reset():
    global collected_points, robot_pose, wall_following_active
    collected_points = []; robot_pose = {'x':0,'y':0,'theta':0}; wall_following_active = False
    car.stop()
    return jsonify({"status": "ok"})

@app.route("/data")
def data():
    with map_lock: return jsonify({"points": collected_points, "pose": robot_pose})

if __name__ == "__main__":
    try:
        threading.Thread(target=control_loop, daemon=True).start()
        app.run(host="0.0.0.0", port=5000, threaded=True)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        stop_event.set()
        car.stop()
        lidar.stopMotor()
        lidar.destroy()