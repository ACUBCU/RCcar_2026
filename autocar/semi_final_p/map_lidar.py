import threading, time, numpy as np, math, json, signal, sys
from flask import Flask, Response, jsonify, request, render_template_string
from pop.Pilot import get_Control
from pop.LiDAR.rplidar import Rplidar

# 1. 하드웨어 초기화
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

# 오토카 하드웨어 구동 루프
def hardware_loop():
    global current_speed, current_steering
    last_speed = None
    last_steering = None
    
    while not stop_event.is_set():
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

        # 모터 제어
        final_steering = current_steering + STEERING_TRIM
        final_steering = max(min(final_steering, 1.0), -1.0)
        
        applied_speed = current_speed
        
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

# LiDAR 데이터 연산 루프 (누적 로직 제거, 실시간 갱신)
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
            
            # 근접 노이즈 필터링 적용 후 실시간 스캔 데이터만 저장
            filtered_local = []
            filtered_global = []
            
            for gx, gy, lvx, lvy in zip(wx, wy, lx_list, ly_list):
                if math.hypot(lvx, lvy) >= 150.0:
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
    <body style="background:#222; color:white; font-family:sans-serif; text-align:center;">
        <h2>Interactive Radar Control (Real-time View)</h2>
        <div style="display:flex; justify-content:center; gap:20px;">
            <div><h3>Local View (Real-time)</h3><canvas id="localMap" width="300" height="300" style="background:black; border:2px solid #555;"></canvas></div>
            <div><h3>Global View (Real-time)</h3><canvas id="globalMap" width="500" height="500" style="background:black; border:2px solid #555; cursor:grab;"></canvas></div>
        </div>
        
        <div style="display:flex; justify-content:center; align-items:center; gap:30px; margin-top:20px;">
            <button id="stopBtn" style="padding:15px 40px; background:red; color:white; font-size:18px; font-weight:bold; border-radius:10px; cursor:pointer; border:none;">FORCE STOP</button>
            <div id="joystick" style="width:150px; height:150px; background:#333; border-radius:50%; position:relative;"></div>
        </div>
        
        <button onclick="resetPosition()" style="padding:10px; margin-top:15px;">위치 초기화</button>
        <script>
            let globalPoints = [];
            let localPoints = [];
            let robot = {x:0, y:0, theta:0};
            let scale = 0.05, offsetX = 250, offsetY = 250;
            let isDrawing = false;
            
            let j_speed = 0, j_steer = 0;
            let last_sent_speed = null, last_sent_steer = null;
            let isStopped = false;
            const stopBtn = document.getElementById('stopBtn');

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

            const bufferLocal = document.createElement('canvas');
            bufferLocal.width = 300; bufferLocal.height = 300;
            const ctxLocalBuffer = bufferLocal.getContext('2d');
            
            const bufferGlobal = document.createElement('canvas');
            bufferGlobal.width = 500; bufferGlobal.height = 500;
            const ctxGlobalBuffer = bufferGlobal.getContext('2d');
            
            const localMap = document.getElementById('localMap').getContext('2d');
            const globalMap = document.getElementById('globalMap').getContext('2d');

            async function fetchData() {
                try {
                    const res = await fetch('/data');
                    const data = await res.json();
                    
                    globalPoints = data.global || [];
                    localPoints = data.local || [];
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
                // Local Map 실시간 렌더링
                ctxLocalBuffer.clearRect(0,0,300,300);
                ctxLocalBuffer.fillStyle = 'blue';
                ctxLocalBuffer.beginPath();
                localPoints.forEach(p => {
                    let lx = p[0] * 0.15 + 150;
                    let ly = p[1] * 0.15 + 150;
                    ctxLocalBuffer.rect(lx - 1.5, ly - 1.5, 3, 3);
                });
                ctxLocalBuffer.fill();
                
                // Global Map 실시간 렌더링 (누적 레이어 제거)
                ctxGlobalBuffer.clearRect(0,0,500,500);
                ctxGlobalBuffer.fillStyle = 'white';
                ctxGlobalBuffer.beginPath();
                globalPoints.forEach(p => {
                    let gx = p[0] * scale + offsetX;
                    let gy = p[1] * scale + offsetY;
                    if(gx > -5 && gx < 505 && gy > -5 && gy < 505) {
                        ctxGlobalBuffer.rect(gx - 1.5, gy - 1.5, 3, 3);
                    }
                });
                ctxGlobalBuffer.fill();
                
                // 로봇 위치 표시 (Global Map)
                let rx = robot.x * scale + offsetX;
                let ry = robot.y * scale + offsetY;
                ctxGlobalBuffer.fillStyle = 'red';
                ctxGlobalBuffer.beginPath();
                ctxGlobalBuffer.arc(rx, ry, 6, 0, 2 * Math.PI);
                ctxGlobalBuffer.fill();
                
                let rad = robot.theta;
                ctxGlobalBuffer.strokeStyle = 'red';
                ctxGlobalBuffer.lineWidth = 2;
                ctxGlobalBuffer.beginPath();
                ctxGlobalBuffer.moveTo(rx, ry);
                ctxGlobalBuffer.lineTo(rx + Math.cos(rad)*20, ry + Math.sin(rad)*20);
                ctxGlobalBuffer.stroke();

                localMap.clearRect(0,0,300,300);
                localMap.drawImage(bufferLocal, 0, 0);
                
                globalMap.clearRect(0,0,500,500);
                globalMap.drawImage(bufferGlobal, 0, 0);
            }

            async function resetPosition() {
                await fetch('/reset', {method:'POST'});
            }

            const gMap = document.getElementById('globalMap');
            gMap.addEventListener('mousedown', e => {
                let startX = e.clientX, startY = e.clientY;
                const move = e => { 
                    offsetX += (e.clientX - startX); 
                    offsetY += (e.clientY - startY); 
                    startX = e.clientX; 
                    startY = e.clientY; 
                    requestDraw(); 
                };
                document.addEventListener('mousemove', move);
                document.addEventListener('mouseup', () => document.removeEventListener('mousemove', move));
            });
            gMap.addEventListener('wheel', e => { 
                scale *= (e.deltaY > 0 ? 0.9 : 1.1); 
                e.preventDefault(); 
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