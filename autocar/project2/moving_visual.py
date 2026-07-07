import threading, time, math, signal, sys
from flask import Flask, jsonify, request, render_template_string
from pop.Pilot import get_Control
from pop import Pilot

print("======================================================")
print(" NEW CODE LOADED: TURN MULTIPLIER 0.8 & POSITION 18.0 ")
print("======================================================")

# =====================================================================
# [ 튜닝 설정 영역 ]
# =====================================================================
# 1. 하드웨어 물리 보정 (직진 유지를 위한 기계적 영점)
STEERING_TRIM = -0.25 

# 2. 그래프 시각화 배율
VISUAL_POSITION_MULTIPLIER = 18.0  # 직진 길이 배율 (기존 15.0 -> 18.0 소폭 상승)
VISUAL_TURN_MULTIPLIER = 0.5      # 회전 속도 배율 (기존 1.5 -> 0.8 하향)

# 3. 자이로 직진 보조 (하드웨어 제어용)
ENABLE_GYRO_CORRECTION = False 
GYRO_CORRECTION_DIR = 1 
GYRO_KP = 0.0005  
# =====================================================================

car = get_Control()
car.steering = STEERING_TRIM 

led = Pilot.PWM(1, 0x5c)
led.setFreq(50)
for i in range(4):
    led.setDuty(i, 4095)

robot_pose = {'x': 0.0, 'y': 0.0, 'theta': math.pi / 2}
path_history = []
current_speed = 0.0
current_steering = 0.0
is_emergency_stopped = False

ACCEL_SCALE = 9.81 / 16384.0 

stop_event = threading.Event()

def cleanup(signum, frame):
    stop_event.set()
    car.stop()
    for i in range(4):
        led.setDuty(i, 0)
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup)

def hardware_loop():
    global robot_pose
    estimated_velocity = 0.0
    last_speed = None
    last_steering = None
    last_time = time.time()
    
    lpf_accel = 0.0
    LPF_ALPHA = 0.3  
    
    while not stop_event.is_set():
        current_time = time.time()
        dt = current_time - last_time
        last_time = current_time
        
        if is_emergency_stopped:
            if last_speed != 0.0 or last_steering != 0.0:
                car.stop()
                car.steering = STEERING_TRIM
                last_speed = 0.0
                last_steering = 0.0
            time.sleep(0.05)
            continue

        try:
            raw_accel = car.getAccel('y') 
            raw_gyro = car.getGyro('z')
        except:
            raw_accel = 0
            raw_gyro = 0
            
        # 1. 가속도 센서 필터링 및 이동 거리 연산
        if abs(raw_accel) < 100: 
            raw_accel = 0
        lpf_accel = (LPF_ALPHA * raw_accel) + ((1.0 - LPF_ALPHA) * lpf_accel)
        
        a_y = lpf_accel * ACCEL_SCALE
        
        if current_speed == 0.0:
            estimated_velocity = 0.0
            lpf_accel = 0.0
        else:
            if current_steering != 0.0:
                a_y *= 2.5
            estimated_velocity += a_y * dt
            
            MIN_VISUAL_SPEED = 0.2
            if current_speed > 0 and estimated_velocity < MIN_VISUAL_SPEED:
                estimated_velocity = MIN_VISUAL_SPEED
            elif current_speed < 0 and estimated_velocity > -MIN_VISUAL_SPEED:
                estimated_velocity = -MIN_VISUAL_SPEED
        
        # 2. 좌표 업데이트
        if abs(estimated_velocity) > 0:
            speed_sign = 1.0 if estimated_velocity > 0 else -1.0
            
            omega = -current_steering * VISUAL_TURN_MULTIPLIER * speed_sign
            
            robot_pose['theta'] += omega * dt
            
            pixel_velocity = estimated_velocity * VISUAL_POSITION_MULTIPLIER
            robot_pose['x'] += pixel_velocity * math.cos(robot_pose['theta']) * dt
            robot_pose['y'] += pixel_velocity * math.sin(robot_pose['theta']) * dt
            
            path_history.append((robot_pose['x'], robot_pose['y']))
            if len(path_history) > 1000: path_history.pop(0)

        # 3. 하드웨어 모터 제어
        if current_speed == 0.0 and current_steering == 0.0:
            if last_speed != 0.0 or last_steering != 0.0:
                car.stop()
                car.steering = STEERING_TRIM
                last_speed = 0.0
                last_steering = 0.0
        else:
            final_steering = current_steering + STEERING_TRIM
            
            if ENABLE_GYRO_CORRECTION and current_steering == 0.0 and current_speed != 0.0:
                if abs(raw_gyro) > 50: 
                    correction = (raw_gyro * GYRO_KP) * GYRO_CORRECTION_DIR
                    final_steering += correction
            
            final_steering = max(min(final_steering, 1.0), -1.0)
            
            applied_speed = current_speed
            if current_steering != 0.0 and current_speed != 0.0:
                applied_speed = 90.0 if current_speed > 0 else -90.0
            
            if applied_speed != last_speed or final_steering != last_steering:
                if applied_speed > 0: 
                    car.steering = final_steering
                    car.forward(applied_speed)
                elif applied_speed < 0: 
                    car.steering = final_steering
                    car.backward(abs(applied_speed))
                else:
                    car.steering = final_steering
                    
                last_speed = applied_speed
                last_steering = final_steering
                
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
        <canvas id="map" width="500" height="300" style="background:black; border:2px solid #555;"></canvas>
        <button id="stopBtn" style="margin:15px 0; padding:15px 60px; background:red; color:white; font-size:20px; font-weight:bold; border-radius:10px; cursor:pointer;">FORCE STOP</button>
        <div id="joystick" style="width:200px; height:200px; background:#333; border-radius:20px; position:relative;"></div>
        
        <script>
            const canvas = document.getElementById('map');
            const ctx = canvas.getContext('2d');
            let j_speed = 0, j_steer = 0;
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
                if (isStopped) return;
                
                if (Math.abs(data.vector.y) > 0.05) j_speed = data.vector.y * 60;
                else j_speed = 0;
                
                if (Math.abs(data.vector.x) > 0.2) j_steer = data.vector.x;
                else j_steer = 0;
            });
            
            joystick.on('end', () => { 
                j_speed = 0; 
                j_steer = 0; 
                fetch(`/cmd?speed=0&steer=0`);
            });

            let isCmdPending = false;
            setInterval(async () => {
                if (isCmdPending) return;
                isCmdPending = true;
                try { await fetch(`/cmd?speed=${j_speed}&steer=${j_steer}`); } catch(e) {}
                isCmdPending = false;
            }, 100);

            let isDataPending = false;
            setInterval(async () => {
                if (isDataPending) return;
                isDataPending = true;
                try {
                    const res = await fetch('/data');
                    const data = await res.json();
                    ctx.clearRect(0,0,500,300);
                    
                    ctx.strokeStyle = 'white'; 
                    ctx.lineWidth = 2; 
                    ctx.beginPath();
                    data.path.forEach((p, i) => {
                        let px = p[0] + 250;
                        let py = 150 - p[1];
                        if(i==0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
                    });
                    ctx.stroke();
                    
                    if(data.path.length > 0) {
                        let lastP = data.path[data.path.length - 1];
                        let lastPx = lastP[0] + 250;
                        let lastPy = 150 - lastP[1];
                        ctx.beginPath();
                        ctx.arc(lastPx, lastPy, 4, 0, 2 * Math.PI);
                        ctx.fillStyle = 'red';
                        ctx.fill();
                    }
                } catch(e) {}
                isDataPending = false;
            }, 100);
        </script>
    </body>
    </html>
    """)

@app.route("/cmd")
def cmd():
    global current_speed, current_steering, is_emergency_stopped
    if is_emergency_stopped: return "stopped", 200
    current_speed = float(request.args.get('speed', 0))
    current_steering = float(request.args.get('steer', 0))
    return "ok", 200

@app.route("/stop")
def stop():
    global current_speed, current_steering, is_emergency_stopped
    is_emergency_stopped = True
    car.stop()
    car.steering = STEERING_TRIM
    current_speed = 0
    current_steering = 0
    return "stopped", 200

@app.route("/resume")
def resume():
    global is_emergency_stopped
    is_emergency_stopped = False
    return "resumed", 200

@app.route("/data")
def data():
    return jsonify({"path": path_history}), 200

if __name__ == "__main__":
    threading.Thread(target=hardware_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, threaded=True) 