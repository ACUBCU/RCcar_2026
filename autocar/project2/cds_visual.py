import threading, time, math, signal, sys
from flask import Flask, jsonify, request, render_template_string
from pop.Pilot import get_Control

# 하드웨어 초기화
car = get_Control()

# 시작 시 바퀴 정렬 (조향값 0으로 초기화)
car.steering = 0 

# 상태 데이터
# 초기 theta를 math.pi / 2 (90도, 즉 위쪽)로 설정하여 북쪽을 바라보게 함
robot_pose = {'x': 0.0, 'y': 0.0, 'theta': math.pi / 2}
path_history = []
current_speed = 0.0
current_steering = 0.0
is_emergency_stopped = False

# [설정값]
WHEELBASE = 150.0  
ALPHA = 0.2        
MAX_SPEED = 60     

stop_event = threading.Event()

def cleanup(signum, frame):
    stop_event.set()
    car.stop()
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup)

# 모터 제어 루프
def drive_loop():
    while not stop_event.is_set():
        if not is_emergency_stopped:
            # 안전하게 클램핑된 조향값을 하드웨어에 전달
            car.steering = max(-1.0, min(1.0, current_steering))
            
            if current_speed > 0: car.forward(current_speed)
            elif current_speed < 0: car.backward(abs(current_speed))
            else: car.stop()
        time.sleep(0.05)

# 위치 추정 로직
def pose_update_loop():
    global robot_pose
    last_time = time.time()
    while not stop_event.is_set():
        dt = time.time() - last_time
        last_time = time.time()
        
        # [회전 가중치 및 전진 감속 로직]
        # 1. 회전이 클수록 전진 거리(v_real) 감소
        turn_factor = abs(current_steering)
        v_real = current_speed * ALPHA * (1.0 - turn_factor * 0.5) 
        
        # 2. 회전 가중치 대폭 증가 (steering 입력에 2.5를 곱해 즉각적 회전)
        steer_rad = current_steering * 2.5 
        
        # 3. 자전거 모델 기반 계산
        omega = (v_real / WHEELBASE) * math.tan(steer_rad)
        robot_pose['theta'] += omega * dt
        
        robot_pose['x'] += v_real * math.cos(robot_pose['theta']) * dt
        robot_pose['y'] += v_real * math.sin(robot_pose['theta']) * dt
        
        # 움직임이 있을 때만 경로 기록
        if abs(current_speed) > 0.1 or abs(current_steering) > 0.1:
            path_history.append((robot_pose['x'], robot_pose['y']))
            if len(path_history) > 1000: path_history.pop(0)
        time.sleep(0.05)

app = Flask(__name__)

@app.route("/")
def index():
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head><script src="https://cdnjs.cloudflare.com/ajax/libs/nipplejs/0.9.0/nipplejs.min.js"></script></head>
    <body style="background:#222; color:white; display:flex; flex-direction:column; align-items:center; font-family:sans-serif; margin:0; padding:10px;">
        <h3 style="margin:5px 0;">AutoCar Controller</h3>
        <!-- 화면 영역 -->
        <canvas id="map" width="500" height="300" style="background:black; border:2px solid #555;"></canvas>
        <!-- 정지 버튼 -->
        <button id="stopBtn" style="margin:15px 0; padding:15px 60px; background:red; color:white; font-size:20px; font-weight:bold; border-radius:10px; cursor:pointer;">FORCE STOP</button>
        <!-- 조이스틱 영역 -->
        <div id="joystick" style="width:200px; height:200px; background:#333; border-radius:20px; position:relative;"></div>
        
        <script>
            const canvas = document.getElementById('map');
            const ctx = canvas.getContext('2d');
            let j_speed = 0, j_steer = 0;

            document.getElementById('stopBtn').onclick = () => fetch('/stop');

            const joystick = nipplejs.create({zone: document.getElementById('joystick'), mode: 'static', position: {left: '50%', top: '50%'}});
            joystick.on('move', (evt, data) => {
                j_speed = data.vector.y * 60;
                j_steer = data.vector.x * 2.5; // 자바스크립트 조향 감도 유지
            });
            joystick.on('end', () => { j_speed = 0; j_steer = 0; });

            // 주기적 명령 전송
            setInterval(() => { fetch(`/cmd?speed=${j_speed}&steer=${j_steer}`); }, 100);

            // 맵 그리기 (Y축 반전하여 상단이 북쪽)
            setInterval(async () => {
                const res = await fetch('/data');
                const data = await res.json();
                ctx.clearRect(0,0,500,300);
                ctx.strokeStyle = 'white'; ctx.lineWidth = 2; ctx.beginPath();
                data.path.forEach((p, i) => {
                    let px = (p[0] * 0.5) + 250;
                    let py = 150 - (p[1] * 0.5); // Y를 반전
                    if(i==0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
                });
                ctx.stroke();
            }, 100);
        </script>
    </body>
    </html>
    """)

@app.route("/cmd")
def cmd():
    global current_speed, current_steering, is_emergency_stopped
    if is_emergency_stopped: return "stopped"
    
    speed_in = float(request.args.get('speed', 0))
    steer_in = float(request.args.get('steer', 0))
    
    # [터미널 경고 해결] 값을 -1.0 ~ 1.0 사이로 강제 제한 (Clamp)
    current_steering = max(-1.0, min(1.0, steer_in))
    current_speed = speed_in
    return "ok"

@app.route("/stop")
def stop():
    global current_speed, current_steering, is_emergency_stopped
    is_emergency_stopped = True
    car.stop()
    current_speed = 0
    current_steering = 0
    return "stopped"

@app.route("/data")
def data():
    return jsonify({"path": path_history})

if __name__ == "__main__":
    threading.Thread(target=drive_loop, daemon=True).start()
    threading.Thread(target=pose_update_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, threaded=True)