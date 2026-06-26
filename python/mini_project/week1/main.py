import threading
import time
import webview
from backend.server import app

def run_flask():
    # 외부 접속 허용 및 포트 5000 지정
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)

if __name__ == '__main__':
    # Flask 서버를 백그라운드 스레드로 가동
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # 서버가 켜질 때까지 잠시 대기
    time.sleep(1)
    
    # pywebview 창 생성 및 연결
    webview.create_window(
        title='Hanback Electronics - AutoCar PrimeX Dashboard',
        url='http://127.0.0.1:5000',
        width=1000,
        height=700,
        resizable=True
    )
    
    # 리눅스/WSL 환경에 맞는 GTK 백엔드로 시작
    webview.start(gui='gtk')