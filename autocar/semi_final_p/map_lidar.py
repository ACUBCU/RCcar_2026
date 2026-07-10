import threading, time, numpy as np, math, json, signal, sys
from flask import Flask, Response, jsonify, request, render_template_string
from pop.Pilot import get_Control
from pop.LiDAR.rplidar import Rplidar

# --- 하드웨어 초기화 ---
car = get_Control()
lidar = Rplidar()
lidar.connect("/dev/ttyUSB0")
lidar.startMotor()

# 모터 제어 헬퍼 함수
def car_forward(car_obj, speed):
    try:
        car_obj.setSpeed(int(speed))
        car_obj.forward(int(speed))
    except TypeError:
        car_obj.forward()

def car_backward(car_obj, speed):
    try:
        car_obj.setSpeed(int(speed))
        car_obj.backward(int(speed))
    except TypeError:
        car_obj.backward()

# --- 캘리브레이션 상수 ---
CMD_TO_METERS_PER_SEC = 0.015
STEERING_TO_RADS_PER_SEC = 0.02
STEERING_TRIM = 0.0 

# 데이터 저장소
robot_pose = {'x': 0.0, 'y': 0.0, 'theta': math.pi / 2}
current_speed = 0.0
current_steering = 0.0
is_emergency_stopped = False

latest_local_scan = []
latest_global_scan = []
map_lock = threading.Lock()
stop_event = threading.Event()

def cleanup(signum, frame):
    stop_event.set()
    try:
        car.stop()
    except:
        pass
    try:
        lidar.stopMotor()
        lidar.disconnect()
    except:
        pass
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

# --- 하드웨어 구동 및 오도메트리 루프 ---
def hardware_loop():
    global current_speed, current_steering, is_emergency_stopped
    last_speed = 0.0
    last_steering = 0.0
    last_time = time.time()
    
    while not stop_event.is_set():
        current_time = time.time()
        dt = current_time - last_time
        last_time = current_time

        if is_emergency_stopped:
            if last_speed != 0.0 or last_steering != 0.0:
                try:
                    car.stop()
                    car.steering = STEERING_TRIM
                except:
                    pass
                last_speed = 0.0
                last_steering = 0.0
            time.sleep(0.05)
            continue

        final_steering = current_steering + STEERING_TRIM
        final_steering = max(min(final_steering, 1.0), -1.0)
        applied_speed = current_speed
        
        linear_velocity = applied_speed * CMD_TO_METERS_PER_SEC
        angular_velocity = applied_speed * final_steering * STEERING_TO_RADS_PER_SEC
        
        with map_lock:
            robot_pose['theta'] += angular_velocity * dt
            robot_pose['x'] += linear_velocity * math.cos(robot_pose['theta']) * dt
            robot_pose['y'] += linear_velocity * math.sin(robot_pose['theta']) * dt

        if applied_speed != last_speed or final_steering != last_steering:
            try:
                car.steering = float(final_steering)
                if applied_speed > 0: 
                    car_forward(car, abs(applied_speed))
                elif applied_speed < 0: 
                    car_backward(car, abs(applied_speed))
                else:
                    car.stop()
            except Exception as e:
                pass
                
            last_speed = applied_speed
            last_steering = final_steering
            
        time.sleep(0.05)

# --- LiDAR 데이터 파싱 루프 ---
def lidar_loop():
    global latest_local_scan, latest_global_scan
    while not stop_event.is_set():
        coords = lidar.getXY()
        if coords is not None and len(coords) > 0:
            lx, ly = coords[:, 0], coords[:, 1]
            theta = robot_pose['theta'] 
            
            wx = lx * np.cos(theta) - ly * np.sin(theta) + robot_pose['x']
            wy = lx * np.sin(theta) + ly * np.cos(theta) + robot_pose['y']
            
            lx_list = lx.tolist()
            ly_list = ly.tolist()
            
            filtered_local = []
            filtered_global = []
            
            for gx, gy, lvx, lvy in zip(wx, wy, lx_list, ly_list):
                filtered_local.append((lvx, lvy))
                filtered_global.append((gx, gy))
            
            with map_lock:
                latest_local_scan = filtered_local
                latest_global_scan = filtered_global
                    
        time.sleep(0.05)

app = Flask(__name__)

@app.route("/")
def index():
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/nipplejs/0.9.0/nipplejs.min.js"></script>
    </head>
    <body style="background:#222; color:white; font-family:sans-serif; text-align:center; margin: 0; padding: 20px;">
        <h2>Interactive LiDAR Mapping (1st Person Top-View)</h2>
        
        <div style="display:flex; justify-content:center; margin-bottom: 20px;">
            <canvas id="mainMap" width="800" height="600" style="background:black; border:2px solid #555;"></canvas>
        </div>
        
        <div style="display:flex; justify-content:center; align-items:center; gap:30px; margin-top:20px;">
            <button id="stopBtn" style="padding:15px 40px; background:red; color:white; font-size:18px; font-weight:bold; border-radius:10px; cursor:pointer; border:none;">FORCE STOP</button>
            <div id="joystick" style="width:150px; height:150px; background:#333; border-radius:50%; position:relative;"></div>
        </div>
        
        <button onclick="resetPosition()" style="padding:10px; margin-top:15px;">맵 및 위치 초기화</button>
        
        <script>
            let globalPoints = [];
            let robot = {x:0, y:0, theta: Math.PI / 2};
            let scale = 0.05;
            let isDrawing = false;
            
            let j_speed = 0, j_steer = 0;
            let last_sent_speed = null, last_sent_steer = null;
            let isStopped = false;
            const stopBtn = document.getElementById('stopBtn');

            // 음수 좌표까지 기록하기 위해 매우 큰 가상 도화지 생성
            const MAP_CENTER = 4000; 
            const mapCanvas = document.createElement('canvas');
            mapCanvas.width = 8000; 
            mapCanvas.height = 8000;
            const mapCtx = mapCanvas.getContext('2d');
            
            const mainMap = document.getElementById('mainMap').getContext('2d');

            stopBtn.onclick = async () => {
                if (!isStopped) {
                    await fetch('/stop');
                    stopBtn.innerText = "RESUME";
                    stopBtn.style.background = "green";
                    isStopped = true;
                } else {
                    await fetch('/resume');
                    stopBtn.innerText = "FORCE STOP";
                    stopBtn.style.background = "red";
                    isStopped = false;
                }
            };

            const joystick = nipplejs.create({zone: document.getElementById('joystick'), mode: 'static', position: {left: '50%', top: '50%'}});
            
            joystick.on('move', (evt, data) => {
                if (isStopped || !data || !data.vector) return;
                if (Math.abs(data.vector.y) > 0.05) j_speed = data.vector.y * 70;
                else j_speed = 0;
                if (Math.abs(data.vector.x) > 0.2) j_steer = data.vector.x;
                else j_steer = 0;
            });
            
            joystick.on('end', () => { 
                j_speed = 0; 
                j_steer = 0; 
            });

            let isCmdPending = false;
            setInterval(async () => {
                if (isCmdPending) return;
                if (j_speed === last_sent_speed && j_steer === last_sent_steer) return;
                
                isCmdPending = true;
                try { 
                    await fetch(`/cmd?speed=${j_speed}&steer=${j_steer}`); 
                    last_sent_speed = j_speed;
                    last_sent_steer = j_steer;
                } catch(e) {}
                isCmdPending = false;
            }, 50);

            async function fetchData() {
                try {
                    const res = await fetch('/data');
                    const data = await res.json();
                    
                    globalPoints = data.global || [];
                    robot = data.pose;
                    requestDraw();
                } catch(e) {}
            }
            
            function requestDraw() {
                if (!isDrawing) {
                    isDrawing = true;
                    requestAnimationFrame(() => {
                        draw();
                        isDrawing = false;
                    });
                }
            }
            
            function draw() {
                // 1. 누적 맵 데이터 기록 (글로벌 좌표 기준)
                mapCtx.fillStyle = 'rgba(76, 175, 80, 0.5)';
                mapCtx.beginPath();
                globalPoints.forEach(p => {
                    let gx = (p[0] * scale) + MAP_CENTER;
                    let gy = (p[1] * scale) + MAP_CENTER;
                    mapCtx.rect(gx - 1.5, gy - 1.5, 3, 3);
                });
                mapCtx.fill();

                // 2. 화면 렌더링 
                mainMap.clearRect(0,0,800,600);
                mainMap.save();

                // 카메라를 화면 정중앙으로 이동
                const centerX = 400;
                const centerY = 300;
                mainMap.translate(centerX, centerY);

                // 화면 회전: 로봇이 항상 위쪽(12시 방향)을 향하도록 캔버스를 반대 방향으로 회전
                mainMap.rotate(-(robot.theta + Math.PI / 2));

                // 맵 역이동: 로봇의 위치가 화면 중앙에 오도록 글로벌 좌표를 반대로 이동
                mainMap.translate(-(robot.x * scale), -(robot.y * scale));

                // 배경 그리드 렌더링
                mainMap.strokeStyle = '#333';
                mainMap.lineWidth = 1;
                mainMap.beginPath();
                
                // 최적화를 위해 로봇 주변 반경의 그리드만 생성
                let startX = (robot.x * scale) - 1000;
                let endX = (robot.x * scale) + 1000;
                let startY = (robot.y * scale) - 1000;
                let endY = (robot.y * scale) + 1000;

                for(let i=Math.floor(startX/50)*50; i<endX; i+=50) { 
                    mainMap.moveTo(i, startY); mainMap.lineTo(i, endY); 
                }
                for(let i=Math.floor(startY/50)*50; i<endY; i+=50) { 
                    mainMap.moveTo(startX, i); mainMap.lineTo(endX, i); 
                }
                mainMap.stroke();

                // 가상 도화지(누적 맵) 부착
                mainMap.drawImage(mapCanvas, -MAP_CENTER, -MAP_CENTER); 

                // 로봇 아이콘 렌더링 (글로벌 좌표 상에 출력)
                let rx = robot.x * scale;
                let ry = robot.y * scale;

                mainMap.fillStyle = 'red';
                mainMap.beginPath();
                mainMap.arc(rx, ry, 6, 0, 2 * Math.PI);
                mainMap.fill();
                
                mainMap.strokeStyle = 'red';
                mainMap.lineWidth = 2;
                mainMap.beginPath();
                mainMap.moveTo(rx, ry);
                mainMap.lineTo(rx + Math.cos(robot.theta)*20, ry + Math.sin(robot.theta)*20);
                mainMap.stroke();

                mainMap.restore();
            }

            async function resetPosition() {
                await fetch('/reset', {method:'POST'});
                scale = 0.05;
                mapCtx.clearRect(0, 0, 8000, 8000);
                requestDraw();
            }

            // 1인칭 탑뷰에서는 수동 드래그 이동을 비활성화하고 마우스 휠 줌 기능만 유지
            const mMap = document.getElementById('mainMap');
            mMap.addEventListener('wheel', e => { 
                scale *= (e.deltaY > 0 ? 0.9 : 1.1); 
                e.preventDefault(); 
                mapCtx.clearRect(0, 0, 8000, 8000); // 줌 변경 시 점 크기 동기화를 위해 도화지 초기화
                requestDraw(); 
            });
            
            setInterval(fetchData, 100); 
        </script>
    </body>
    </html>
    """)

@app.route("/data")
def get_data():
    with map_lock:
        local_scan = latest_local_scan.copy()
        global_scan = latest_global_scan.copy()
        
    return jsonify({"global": global_scan, "local": local_scan, "pose": robot_pose})

@app.route("/cmd")
def cmd():
    global current_speed, current_steering, is_emergency_stopped
    if is_emergency_stopped: return "stopped", 200
    current_speed = float(request.args.get('speed', 0))
    current_steering = float(request.args.get('steer', 0))
    return "ok", 200

@app.route("/stop")
def stop_car():
    global current_speed, current_steering, is_emergency_stopped
    is_emergency_stopped = True
    try:
        car.stop()
        car.steering = STEERING_TRIM
    except:
        pass
    current_speed = 0
    current_steering = 0
    return "stopped", 200

@app.route("/resume")
def resume_car():
    global is_emergency_stopped
    is_emergency_stopped = False
    return "resumed", 200

@app.route("/reset", methods=["POST"])
def reset():
    global robot_pose
    with map_lock:
        robot_pose = {'x':0, 'y':0, 'theta': math.pi / 2}
    return jsonify({"status": "reset"})

if __name__ == "__main__":
    threading.Thread(target=hardware_loop, daemon=True).start()
    threading.Thread(target=lidar_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, threaded=True)