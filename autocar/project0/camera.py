import threading, time, cv2
from flask import Flask, Response, jsonify, request, render_template_string
from pop import Util
from pop.Pilot import get_Control

# 1. 초기화
Util.enable_imshow()
car = get_Control() 

def init_camera():
    cam = Util.gstrmer(width=640, height=480, fps=30, flip=0)
    return cv2.VideoCapture(cam, cv2.CAP_GSTREAMER)

cap = init_camera()
camera_active = True

# 카메라 초기 정렬
car.camPan(85)
car.camTilt(0)

# 상태 변수
current_pan, current_tilt = 85, 0
STEP = 5 
FIXED_SPEED = 40 

latest_frame = None
frame_lock = threading.Lock()
stop_event = threading.Event()

def capture_loop():
    global latest_frame
    while not stop_event.is_set():
        if camera_active and cap.isOpened():
            ret, frame = cap.read()
            if ret:
                with frame_lock: latest_frame = frame.copy()
        time.sleep(0.01)

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Autocar Controller</title>
    <style>
        body { text-align: center; font-family: sans-serif; background-color: #f0f0f0; }
        #joystick-container { 
            width: 200px; height: 200px; background: #ccc; border-radius: 50%; 
            margin: 20px auto; position: relative; border: 4px solid #555;
            touch-action: none; user-select: none;
        }
        #dot { 
            width: 50px; height: 50px; background: red; border-radius: 50%; 
            position: absolute; top: 75px; left: 75px; cursor: grab; pointer-events: none;
        }
        button { padding: 10px 20px; font-size: 16px; margin: 5px; cursor: pointer; }
        .stop-btn { background-color: #ff4d4d; color: white; font-weight: bold; }
    </style>
</head>
<body>
    <h2>Autocar Prime+NX 통합 제어</h2>
    <img src="/video" width="480" height="360"><br>
    
    <div id="joystick-container">
        <div id="dot"></div>
    </div>
    
    <button class="stop-btn" onclick="resetCar()">정지 및 초기화</button><br>
    <button onclick="toggleCamera()">카메라 ON/OFF</button><br>
    <button onclick="moveCam('tilt', 'up')">▲ (위)</button><br>
    <button onclick="moveCam('pan', 'left')">◀ (좌)</button>
    <button onclick="moveCam('pan', 'right')">▶ (우)</button><br>
    <button onclick="moveCam('tilt', 'down')">▼ (아래)</button>

    <script>
        let isMoving = false;
        let lastSent = 0;
        const container = document.getElementById('joystick-container');
        const dot = document.getElementById('dot');
        
        container.addEventListener('mousedown', (e) => {
            isMoving = true;
            document.addEventListener('mousemove', moveJoy);
            document.addEventListener('mouseup', stopJoy);
            moveJoy(e);
        });

        function stopJoy() { 
            isMoving = false; 
            dot.style.transform = 'translate(0px, 0px)'; 
            document.removeEventListener('mousemove', moveJoy);
            document.removeEventListener('mouseup', stopJoy);
            fetch('/move', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({x: 0, y: 0})}); 
        }

        function moveJoy(e) {
            if(!isMoving) return;
            let now = Date.now();
            if (now - lastSent < 50) return;
            lastSent = now;
            
            let rect = container.getBoundingClientRect();
            let x = Math.max(-1, Math.min(1, (e.clientX - (rect.left + 100)) / 75));
            let y = Math.max(-1, Math.min(1, -(e.clientY - (rect.top + 100)) / 75));
            dot.style.transform = `translate(${x*75}px, ${-y*75}px)`;
            fetch('/move', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({x: x, y: y})});
        }

        function moveCam(type, dir) { fetch('/' + type, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({direction: dir}) }); }
        function toggleCamera() { fetch('/toggle', {method: 'POST'}).then(res => res.json()).then(data => alert('Camera: ' + data.status)); }
        function resetCar() { fetch('/reset', {method: 'POST'}).then(() => alert('차량이 정지되고 초기 상태로 복귀했습니다.')); }
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/move", methods=["POST"])
def move():
    data = request.json
    steer, y_val = data.get('x'), data.get('y')
    car.steering = steer
    if abs(y_val) < 0.2: car.stop()
    elif y_val >= 0.2: car.forward(FIXED_SPEED)
    else: car.backward(FIXED_SPEED)
    return jsonify({"status": "success"})

@app.route("/reset", methods=["POST"])
def reset():
    global current_pan, current_tilt
    car.stop()
    car.steering = 0
    current_pan = 85
    current_tilt = 0
    car.camPan(current_pan)
    car.camTilt(current_tilt)
    return jsonify({"status": "reset"})

@app.route("/pan", methods=["POST"])
def pan():
    global current_pan
    direction = request.json.get('direction')
    if direction == 'left': current_pan = max(8, current_pan - STEP)
    else: current_pan = min(172, current_pan + STEP)
    car.camPan(current_pan)
    return jsonify({"status": "success", "pan": current_pan})

@app.route("/tilt", methods=["POST"])
def tilt():
    global current_tilt
    direction = request.json.get('direction')
    if direction == 'up': current_tilt = min(85, current_tilt + STEP)
    else: current_tilt = max(0, current_tilt - STEP)
    car.camTilt(current_tilt)
    return jsonify({"status": "success", "tilt": current_tilt})

@app.route("/toggle", methods=["POST"])
def toggle():
    global cap, camera_active
    if camera_active: cap.release(); camera_active = False
    else: cap = init_camera(); camera_active = True
    return jsonify({"status": "ON" if camera_active else "OFF"})

@app.route("/video")
def video():
    def generate():
        while not stop_event.is_set():
            if not camera_active: time.sleep(0.5); continue
            with frame_lock: frame = None if latest_frame is None else latest_frame.copy()
            if frame is None: time.sleep(0.05); continue
            ret, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
            if ret: yield (b"--frame\r\n" b"Content-Type: image/jpeg\r\n\r\n" + jpg.tobytes() + b"\r\n")
            time.sleep(0.03)
    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")

if __name__ == "__main__":
    threading.Thread(target=capture_loop, daemon=True).start()
    try:
        app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False, threaded=True)
    except KeyboardInterrupt:
        print("\n종료 신호 감지, 자원 정리 중...")
    finally:
        stop_event.set()
        if cap.isOpened(): cap.release()
        car.stop()
        print("프로그램 종료")