import threading, time, numpy as np, math, json
from flask import Flask, Response, jsonify, request, render_template_string
from pop.Pilot import get_Control
from pop.LiDAR.rplidar import Rplidar

# 1. 하드웨어 초기화
car = get_Control()
lidar = Rplidar()
lidar.connect("/dev/ttyUSB0")
lidar.startMotor()

# 데이터 저장소
robot_pose = {'x': 0.0, 'y': 0.0, 'theta': 0.0}
collected_points = [] 
FIXED_SPEED = 40
map_lock = threading.Lock()
stop_event = threading.Event()

def lidar_loop():
    global collected_points
    while not stop_event.is_set():
        coords = lidar.getXY()
        if coords is not None and len(coords) > 0:
            theta = math.radians(robot_pose['theta'])
            lx, ly = coords[:, 0], coords[:, 1]
            wx = lx * np.cos(theta) - ly * np.sin(theta) + robot_pose['x']
            wy = lx * np.sin(theta) + ly * np.cos(theta) + robot_pose['y']
            
            with map_lock:
                collected_points.extend(zip(wx.tolist(), wy.tolist()))
                if len(collected_points) > 50000:
                    collected_points = collected_points[-50000:]
        time.sleep(0.05)

app = Flask(__name__)

@app.route("/")
def index():
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <body style="background:#222; color:white; font-family:sans-serif; text-align:center;">
        <h2>Interactive Mapping Control</h2>
        <div style="display:flex; justify-content:center; gap:20px;">
            <div><h3>Local View (1m)</h3><canvas id="localMap" width="300" height="300" style="background:black; border:2px solid #555;"></canvas></div>
            <div><h3>Global Map (Interactive)</h3><canvas id="globalMap" width="500" height="500" style="background:black; border:2px solid #555; cursor:grab;"></canvas></div>
        </div>
        <div id="joystick-container" style="width:150px; height:150px; background:#ccc; border-radius:50%; margin:20px auto; position:relative; touch-action:none;">
            <div id="dot" style="width:40px; height:40px; background:red; border-radius:50%; position:absolute; top:55px; left:55px; pointer-events:none;"></div>
        </div>
        <button onclick="fetch('/reset', {method:'POST'}).then(()=>location.reload())" style="padding:10px;">지도 초기화</button>
        <script>
            let points = [];
            let robot = {x:0, y:0, theta:0};
            let scale = 0.05, offsetX = 250, offsetY = 250;
            
            async function fetchData() {
                const res = await fetch('/data');
                const data = await res.json();
                points = data.points;
                robot = data.pose;
                draw();
            }
            
            function draw() {
                const localCtx = document.getElementById('localMap').getContext('2d');
                const globalCtx = document.getElementById('globalMap').getContext('2d');
                
                localCtx.clearRect(0,0,300,300);
                globalCtx.clearRect(0,0,500,500);
                
                // 1. 점 데이터 그리기
                points.forEach(p => {
                    let lx = (p[0] - robot.x) * 0.15 + 150;
                    let ly = (p[1] - robot.y) * 0.15 + 150;
                    localCtx.fillStyle = 'blue';
                    localCtx.fillRect(lx, ly, 2, 2);
                    
                    let gx = p[0] * scale + offsetX;
                    let gy = p[1] * scale + offsetY;
                    globalCtx.fillStyle = 'white';
                    globalCtx.fillRect(gx, gy, 1.5, 1.5);
                });
                
                // 2. 로봇 위치 표시 (Global Map)
                let rx = robot.x * scale + offsetX;
                let ry = robot.y * scale + offsetY;
                globalCtx.fillStyle = 'red';
                globalCtx.beginPath();
                globalCtx.arc(rx, ry, 6, 0, 2 * Math.PI); // 로봇 위치 점
                globalCtx.fill();
                
                // 로봇 방향 지시선
                let rad = robot.theta * Math.PI / 180;
                globalCtx.strokeStyle = 'red';
                globalCtx.lineWidth = 2;
                globalCtx.beginPath();
                globalCtx.moveTo(rx, ry);
                globalCtx.lineTo(rx + Math.cos(rad)*20, ry + Math.sin(rad)*20);
                globalCtx.stroke();
            }

            const gMap = document.getElementById('globalMap');
            gMap.addEventListener('mousedown', e => {
                let startX = e.clientX, startY = e.clientY;
                const move = e => { offsetX += (e.clientX - startX); offsetY += (e.clientY - startY); startX = e.clientX; startY = e.clientY; };
                document.addEventListener('mousemove', move);
                document.addEventListener('mouseup', () => document.removeEventListener('mousemove', move));
            });
            gMap.addEventListener('wheel', e => { scale *= (e.deltaY > 0 ? 0.9 : 1.1); e.preventDefault(); });
            
            const con = document.getElementById('joystick-container');
            con.addEventListener('mousedown', e => {
                const move = e => {
                    let x = (e.clientX - con.getBoundingClientRect().left - 75) / 75;
                    let y = -(e.clientY - con.getBoundingClientRect().top - 75) / 75;
                    fetch('/move', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({x:x, y:y})});
                };
                document.addEventListener('mousemove', move);
                document.addEventListener('mouseup', () => document.removeEventListener('mousemove', move));
            });
            setInterval(fetchData, 200);
        </script>
    </body>
    </html>
    """)

@app.route("/data")
def get_data():
    with map_lock:
        return jsonify({"points": collected_points, "pose": robot_pose})

@app.route("/move", methods=["POST"])
def move():
    data = request.json
    steer, y_val = data.get('x'), data.get('y')
    car.steering = steer
    if abs(y_val) < 0.2: car.stop()
    elif y_val >= 0.2: car.forward(FIXED_SPEED)
    else: car.backward(FIXED_SPEED)
    
    speed_factor = FIXED_SPEED / 100.0
    robot_pose['x'] += speed_factor * math.cos(math.radians(robot_pose['theta']))
    robot_pose['y'] += speed_factor * math.sin(math.radians(robot_pose['theta']))
    # 회전 계산 (theta 갱신)
    robot_pose['theta'] += steer * 2.0
    return jsonify({"status": "success"})

@app.route("/reset", methods=["POST"])
def reset():
    global collected_points, robot_pose
    collected_points = []; robot_pose = {'x':0, 'y':0, 'theta':0}
    return jsonify({"status": "reset"})

if __name__ == "__main__":
    threading.Thread(target=lidar_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, threaded=True)