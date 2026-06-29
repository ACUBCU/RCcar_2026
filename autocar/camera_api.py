'''
/video 카메라 정보
flask로 서버열기
import cv2
from pop import Util
Util.enable_imshow() 
cam = Util.gstrmer(width=640, height=480, fps=30, flip=0)
camera = cv2.VideoCapture(cam, cv2.CAP_GSTREAMER)
if not camera.isOpened():
else:
    while True:
        ret, frame = camera.read()
        if not ret:
            break
        cv2.imshow("soda", frame)
    
camera.release()
cv2.destroyAllWindows()

이 파이썬 코드를 사용
jpg 60%압축
5000번 포트 api
쓰레드 사용
'''
import threading
import time
from threading import Thread

# 카메라 열기
import cv2
from flask import Flask, Response, jsonify
from pop import Util

# for _ in range(120):
#     ret, frame = cap.read()
#     if not ret:
#         print(ret)
#         continue
#     cv2.imshow("frame", frame)
# cap.release()
# 위 코드를 기준으로 해서 작성
# jpg 압축 60% 해서 데이터 보내기
# 5000 번 포트로 api 열기
# 쓰레드 사용
# scp camera_api.py soda@192.168.0.34:/home/soda



app = Flask("camera_api")

cam = Util.gstrmer(width=640, height=480, fps=30, flip=0)
cap = cv2.VideoCapture(cam, cv2.CAP_GSTREAMER)

if not cap.isOpened():
    raise RuntimeError("Camera open failed")

latest_frame = None
stop_event = threading.Event()
frame_lock = threading.Lock()


def capture_loop():
    global latest_frame

    while not stop_event.is_set():
        ret, frame = cap.read()

        if ret:
            with frame_lock:
                latest_frame = frame.copy()

        time.sleep(0.01)


def encode_jpeg(frame, quality=80):
    ret, jpeg = cv2.imencode(
        ".jpg",
        frame,
        [cv2.IMWRITE_JPEG_QUALITY, quality]
    )

    if not ret:
        return None

    return jpeg.tobytes()


@app.route("/")
def index():
    return """
    <html>
        <head>
            <title>Jetson Camera API</title>
        </head>
        <body>
            <h2>Jetson Camera API</h2>
            <img src="/video" width="640" height="480">
            <p><a href="/snapshot.jpg">snapshot</a></p>
            <p><a href="/status">status</a></p>
            <p><a href="/stop">stop camera</a></p>
        </body>
    </html>
    """


@app.route("/video")
def video():
    def generate():
        while not stop_event.is_set():
            with frame_lock:
                frame = None if latest_frame is None else latest_frame.copy()

            if frame is None:
                time.sleep(0.05)
                continue

            jpg = encode_jpeg(frame, quality=75)

            if jpg is None:
                continue

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" +
                jpg +
                b"\r\n"
            )

            time.sleep(0.03)

    return Response(
        generate(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/snapshot.jpg")
def snapshot():
    with frame_lock:
        frame = None if latest_frame is None else latest_frame.copy()

    if frame is None:
        return "No frame", 503

    jpg = encode_jpeg(frame, quality=90)

    return Response(jpg, mimetype="image/jpeg")


@app.route("/status")
def status():
    with frame_lock:
        frame = None if latest_frame is None else latest_frame.copy()

    if frame is None:
        return jsonify({
            "camera": "not ready"
        })

    h, w = frame.shape[:2]

    return jsonify({
        "camera": "ok",
        "width": w,
        "height": h
    })


@app.route("/stop")
def stop():
    stop_camera()
    return "camera stopped"


def stop_camera():
    stop_event.set()
    time.sleep(0.2)

    if cap.isOpened():
        cap.release()

    print("camera released")


def run_server():
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        use_reloader=False,
        threaded=True
    )


capture_thread = threading.Thread(target=capture_loop)
capture_thread.start()

server_thread = threading.Thread(target=run_server)
server_thread.start()

print("Camera API started")
print("Open: http://JETSON_IP:5000")