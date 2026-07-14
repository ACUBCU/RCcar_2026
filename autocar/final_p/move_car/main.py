import time
import multiprocessing
import sys

from follow_wall import LidarExplorer 

def main():
    multiprocessing.set_start_method('spawn', force=True)

    print("=========================================")
    print(" AutoCar Prime NX - 자율 맵핑 시스템 시작")
    print("=========================================")

    data_queue = multiprocessing.Queue(maxsize=10)
    
    # 💡 안전 종료를 위한 Event 객체 생성
    stop_event = multiprocessing.Event()

    # 인자에 stop_event 추가
    explorer_process = LidarExplorer(data_queue=data_queue, stop_event=stop_event)

    try:
        explorer_process.start()

        print("[System] 주행 모니터링 중... (종료하려면 Ctrl+C를 누르세요)")
        while True:
            if not data_queue.empty():
                status_data = data_queue.get()
                cmd = status_data['steering_vector']['command']
                print(f"현재 주행 명령: {cmd}")
                
            time.sleep(0.5)

    except KeyboardInterrupt:
        # Ctrl+C가 눌렸을 때 실행됨
        print("\n[System] 사용자에 의한 긴급 정지 감지! 시스템 종료를 시작합니다.")
        
    finally:
        # 1. 자식 프로세스에게 "이제 멈추고 루프를 빠져나와!" 라고 알림
        stop_event.set()
        
        # 2. 자식 프로세스가 finally 블록(car.stop())을 다 실행할 때까지 기다림 (최대 3초)
        if explorer_process.is_alive():
            print("[System] 하드웨어가 완전히 멈출 때까지 대기 중...")
            explorer_process.join(timeout=3.0)
            
            # 3초가 지났는데도 프로세스가 안 죽으면 최후의 수단으로 킬
            if explorer_process.is_alive():
                print("[System] 응답이 없어 프로세스를 강제 종료합니다.")
                explorer_process.terminate()
                explorer_process.join()
        
        print("=========================================")
        print(" 자율 맵핑 시스템이 안전하게 종료되었습니다.")
        print("=========================================")
        sys.exit(0)

if __name__ == '__main__':
    main()