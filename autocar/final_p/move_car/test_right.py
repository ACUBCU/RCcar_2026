import time
import math
from pop.LiDAR.rplidar import Rplidar

def run_lidar_test():
    print("[TEST] 라이다 센서 각도 및 거리 측정 테스트 시작...")
    
    lidar = Rplidar()
    lidar.connect("/dev/ttyUSB0")
    lidar.startMotor()
    
    try:
        print("[TEST] 오토카 우측에 벽을 두고 결과를 확인하세요. (종료: Ctrl+C)")
        print("-" * 50)
        
        while True:
            coords = lidar.getXY()
            
            # 데이터가 없으면 대기
            if coords is None or len(coords) == 0:
                time.sleep(0.1)
                continue
            
            min_dist = float('inf')
            closest_angle = 0.0
            closest_x = 0.0
            closest_y = 0.0
            
            # 추출된 모든 점들을 검사하여 가장 가까운 점 찾기
            for x, y in coords:
                dist = math.hypot(x, y)
                
                # 너무 가깝거나(노이즈), 너무 먼 데이터 필터링 (20cm ~ 6m)
                if dist < 200 or dist > 6000:
                    continue
                    
                if dist < min_dist:
                    min_dist = dist
                    closest_angle = math.degrees(math.atan2(y, x))
                    closest_x = x
                    closest_y = y
            
            # 유효한 점이 발견되었다면 터미널에 출력
            if min_dist != float('inf'):
                print(f"가장 가까운 물체 -> 거리: {min_dist:4.0f} mm | 각도: {closest_angle:5.1f}° | (X: {closest_x:5.0f}, Y: {closest_y:5.0f})")
            else:
                print("유효한 거리 내에 물체가 없습니다.")
                
            # 너무 빠르게 올라가면 읽기 힘드므로 0.5초마다 갱신
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n[TEST] 사용자에 의해 테스트가 종료되었습니다.")
    except Exception as e:
        print(f"[TEST] 에러 발생: {e}")
    finally:
        print("[TEST] 라이다 모터 안전 종료 중...")
        try:
            lidar.stopMotor()
        except:
            pass
        time.sleep(0.5)
        print("[TEST] 종료 완료.")

if __name__ == "__main__":
    run_lidar_test()