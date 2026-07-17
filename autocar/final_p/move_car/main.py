import threading
import time
from flask import Flask, render_template, jsonify
from multiprocessing import Queue, Event

from follow_wall import LidarExplorer, StairDetector

app = Flask(__name__)
data_queue = Queue()

explorer = None
stair_detector = None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/data')
def get_data():
    latest_data = None
    while not data_queue.empty():
        try:
            latest_data = data_queue.get()
        except:
            break
    if latest_data:
        return jsonify(latest_data)
    return jsonify({"status": "empty"})

@app.route('/command/<action>')
def send_command(action):
    global explorer
    if not explorer:
        return jsonify({"error": "시스템이 준비되지 않았습니다."}), 500
        
    if action == 'start':
        explorer.driving_enabled.set() 
        return jsonify({"status": "success", "message": "주행을 시작합니다."})
    elif action == 'stop':
        explorer.driving_enabled.clear()
        return jsonify({"status": "success", "message": "주행을 정지했습니다."})
    else:
        return jsonify({"error": "알 수 없는 명령입니다."}), 400

if __name__ == '__main__':
    stop_event = Event()
    driving_enabled_event = Event() 
    stair_event = Event() # 계단 감지 신호 동기화 이벤트
    
    explorer = LidarExplorer(data_queue, stop_event, driving_enabled_event, stair_event)
    explorer.start()
    
    # 🚨 학습된 pth 파일명에 맞게 model_path 값을 변경하십시오.
    stair_detector = StairDetector(stair_event, stop_event, model_path="collision_avoid_model.pth")
    stair_detector.start()
    
    print("[SYSTEM] 오토카 주행 시스템 및 웹 서버가 구동되었습니다.")
    print("[SYSTEM] 노트북 브라우저에서 http://192.168.0.49:5000 으로 접속하세요.")
    
    try:
        app.run(host='0.0.0.0', port=5000, threaded=True, use_reloader=False)
    except KeyboardInterrupt:
        print("\n[SYSTEM] 시스템을 종료합니다.")
    finally:
        stop_event.set()
        explorer.join()
        stair_detector.join()