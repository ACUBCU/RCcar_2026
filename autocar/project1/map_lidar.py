import threading, time, numpy as np, math
from flask import Flask, Response, jsonify, request, render_template_string
from pop import Util
from pop.Pilot import get_Control
from pop.LiDAR.rplidar import Rplidar

# 1. 하드웨어 초기화
car = get_Control()
lidar = Rplidar()
lidar.connect("/dev/ttyUSB0")
lidar.startMotor()

# 로봇 상태 및 지도 변수
robot_pose = {'x': 0.0, 'y': 0.0, 'theta': 0.0} 
FIXED_SPEED = 40
MAP_RANGE, GRID_SIZE = 5000, 300
grid_map = np.zeros((GRID_SIZE, GRID_SIZE), dtype=np.uint8)

map_lock = threading.Lock()
stop_event = threading.Event()

# 2. LiDAR 매핑 로직
def lidar_loop():
    global grid_map
    while not stop_event.is_set():
        coords = lidar.getXY()
        if coords is not None and len(coords) > 0:
            theta = math.radians(robot_pose['theta'])
            lx, ly = coords[:, 0], coords[:, 1]
            
            # 세계 좌표계 변환
            wx = lx * np.cos(theta) - ly * np.sin(theta) + robot_pose['x']
            wy = lx * np.sin(theta) + ly * np.cos(theta) + robot_pose['y']
            
            grid_x = ((wx + MAP_RANGE) / (MAP_RANGE * 2 / GRID_SIZE)).astype(int)
            grid_y = ((wy + MAP_RANGE) / (MAP_RANGE * 2 / GRID_SIZE)).astype(int)
            
            with map_lock:
                mask = (grid_x >= 0) & (grid_x < GRID_SIZE) & (grid_y >= 0) & (grid_y < GRID_SIZE)
                grid_map[grid_y[mask], grid_x[mask]] = 255
        time.sleep(0.1)

# 3. 플라스크 웹 서버
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Autocar Mapping</title>
    <style>
        body { text-align: center; font-family: sans-serif; background: #f0f0f0; }
        #joystick-container { width: 200px; height: 200px; background: #ccc; border-radius: 50%; margin: 20px auto; position: relative; border: 4px solid #555; touch-action: none; user-select: none; }
        #dot { width: 50px; height: 50px; background: red; border-radius: 50%; position: absolute; top: 75px; left: 75px; cursor: grab; pointer-events: none; }
        img { border: 2px solid #333; }
    </style>
</head>
<body>
    <h2>Autocar Mapping Control</h2>
    <img id="map" src="/map" width="300" height="300"><br>
    <div id="joystick-container">
        <div id="dot"></div>
    </div>
    <button onclick="fetch('/reset', {method:'POST'}).then(()=>alert('지도 및 위치가 초기화되었습니다.'))" style="padding:10px 20px; font-size:16px;">정지 및 초기화</button>
    
    <script>
        let isMoving = false;
        const container = document.getElementById('joystick-container');
        const dot = document.getElementById('dot');
        
        container.addEventListener('mousedown', (e) => { isMoving = true; document.addEventListener('mousemove', moveJoy); document.addEventListener('mouseup', stopJoy); moveJoy(e); });
        
        function stopJoy() { isMoving = false; dot.style.transform = 'translate(0px, 0px)'; document.removeEventListener('mousemove', moveJoy); document.removeEventListener('mouseup', stopJoy); fetch('/move', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({x:0, y:0})}); }
        
        function moveJoy(e) { if(!isMoving) return; let rect = container.getBoundingClientRect(); let x = Math.max(-1, Math.min(1, (e.clientX - rect.left - 100) / 75)); let y = Math.max(-1, Math.min(1, -(e.clientY - rect.top - 100) / 75)); dot.style.transform = `translate(${x*75}px, ${-y*75}px)`; fetch('/move', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({x:x, y:y})}); }
        
        setInterval(() => { document.getElementById('map').src = '/map?' + new Date().getTime(); }, 500);
    </script>
</body>
</html>
"""

@app.route("/")
def index(): return render_template_string(HTML_TEMPLATE)

@app.route("/map")
def get_map():
    with map_lock:
        ret, jpg = cv2.imencode(".jpg", grid_map)
    return Response(jpg.tobytes(), mimetype="image/jpeg")

@app.route("/move", methods=["POST"])
def move():
    data = request.json
    steer, y_val = data.get('x'), data.get('y')
    car.steering = steer
    
    # 모터 제어
    if abs(y_val) < 0.2: car.stop()
    elif y_val >= 0.2: car.forward(FIXED_SPEED)
    else: car.backward(FIXED_SPEED)
    
    # 위치 보정 (Dead Reckoning)
    if abs(y_val) >= 0.2:
        speed_factor = FIXED_SPEED / 100.0
        robot_pose['x'] += speed_factor * math.cos(math.radians(robot_pose['theta']))
        robot_pose['y'] += speed_factor * math.sin(math.radians(robot_pose['theta']))
    robot_pose['theta'] += steer * 2.0
    return jsonify({"status": "success"})

@app.route("/reset", methods=["POST"])
def reset():
    global grid_map, robot_pose
    car.stop(); car.steering = 0
    grid_map = np.zeros((GRID_SIZE, GRID_SIZE), dtype=np.uint8)
    robot_pose = {'x': 0.0, 'y': 0.0, 'theta': 0.0}
    return jsonify({"status": "reset"})

if __name__ == "__main__":
    threading.Thread(target=lidar_loop, daemon=True).start()
    try:
        app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False, threaded=True)
    except KeyboardInterrupt:
        print("\n종료 신호 감지...")
    finally:
        stop_event.set()
        lidar.stopMotor(); lidar.destroy()
        car.stop()