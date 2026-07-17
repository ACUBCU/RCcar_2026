import time
import math
import numpy as np
from multiprocessing import Process, Event

from pop.Pilot import get_Control
from pop.LiDAR.rplidar import Rplidar

# ==========================================
# 1. AI 계단 인식 프로세스 (독립 실행)
# ==========================================
class StairDetector(Process):
    def __init__(self, stair_event, stop_event, model_path="collision_avoid_model.pth"):
        super().__init__()
        self.stair_event = stair_event
        self.stop_event = stop_event
        self.model_path = model_path

    def run(self):
        print("[AI] 계단 인식(Collision_Avoid) 프로세스 시작...")
        try:
            from pop import Camera
            from pop.Pilot import Collision_Avoid
            
            cam = Camera(width=320, height=240)
            ca = Collision_Avoid(cam)
            ca.load_model(path=self.model_path)
            print("[AI] 모델 로드 완료 및 실시간 감지 시작")
            
        except Exception as e:
            print(f"[AI] 카메라 또는 모델 로드 실패: {e}")
            return

        while not self.stop_event.is_set():
            try:
                prob_blocked = ca.run()
                
                # 차단(계단) 확률이 60% 이상일 경우 라이다 프로세스로 신호 전송
                if prob_blocked > 0.6:
                    self.stair_event.set()
                else:
                    self.stair_event.clear()
                    
            except Exception as e:
                pass
            
            time.sleep(0.05)
            
        print("[AI] 계단 감지 프로세스 종료")

# ==========================================
# 2. 자율주행 및 라이다 프로세스
# ==========================================
class LidarExplorer(Process):
    def __init__(self, data_queue, stop_event, driving_enabled, stair_event):
        super().__init__()
        self.data_queue = data_queue
        self.stop_event = stop_event
        self.driving_enabled = driving_enabled 
        self.stair_event = stair_event 
        
        # 🚨 [추가] 오도메트리 기반 회피 기동 상태 변수
        self.stair_evasion_mode = False
        self.stair_evasion_start_theta = 0.0
        
        self.SAFE_FRONT = 600          
        self.CRITICAL_FRONT = 350      
        self.BACKUP_TARGET = 700       
        self.BACKUP_MIN_TIME = 0.5     
        self.BACKUP_MAX_TIME = 1.5     
        self.backup_start_time = 0.0
        
        self.TARGET_WALL_DIST = 400    
        self.MARGIN = 150              
        self.MIN_VALID_DIST = 200      
        self.MAX_VALID_DIST = 6000     
        
        self.BASE_SPEED = 50           
        self.STEERING_TRIM = 0.0
        
        self.current_hardware_speed = None
        self.current_hardware_steering = None
        self.kinematic_speed = 0.0     
        
        self.robot_pose = {'x': 0.0, 'y': 0.0, 'theta': math.pi / 2}
        self.LIDAR_OFFSET_X = 0.12 
        
        self.CMD_TO_METERS_PER_SEC = 0.012 
        self.GYRO_SCALE = (1.0 / 131.0) * (math.pi / 180.0)
        self.GYRO_Z_OFFSET = 0.0 
        self.GYRO_DIRECTION = 1.0 

        self.explore_state = "PAUSED"

    def run(self):
        print("[LiDAR] LidarExplorer 자율주행 프로세스 시작...")
        car = get_Control() 
        lidar = Rplidar()
        lidar.connect("/dev/ttyUSB0")
        lidar.startMotor()
        
        print("[LiDAR] 자이로 센서 영점 보정 중...")
        offset_sum = 0.0
        valid_reads = 0
        for _ in range(50):
            try:
                offset_sum += car.getGyro('z')
                valid_reads += 1
            except Exception:
                pass
            time.sleep(0.02)
            
        if valid_reads > 0:
            self.GYRO_Z_OFFSET = offset_sum / valid_reads
            print(f"[LiDAR] 영점 보정 완료 (Offset: {self.GYRO_Z_OFFSET:.2f})")
        else:
            print("[LiDAR] 영점 보정 실패 (기본값 0 사용)")

        last_time = time.time()
        
        try:
            while not self.stop_event.is_set():
                current_time = time.time() 
                dt = current_time - last_time
                last_time = current_time

                try:
                    coords = lidar.getXY()
                except Exception:
                    time.sleep(0.01)
                    continue

                if coords is None or len(coords) == 0:
                    time.sleep(0.01) 
                    continue
                
                # 🚨 [수정 1] 계단 감지를 무조건 STOP 시키던 로직을 지우고, 주행 알고리즘에 '변수'로 넘겨줍니다.
                if self.driving_enabled.is_set():
                    lx, ly = coords[:, 0], coords[:, 1]
                    is_stair_detected = self.stair_event.is_set()
                    
                    # 주행 알고리즘 호출 시 계단 감지 여부를 파라미터로 추가
                    command, target_angle = self.calculate_steering_from_xy(lx, ly, current_time, is_stair=is_stair_detected)
                    self.drive_and_update_pose(car, command, dt)
                    
                    # 화면 출력을 위한 데이터 전송
                    lidar_data = [{'x': float(raw_y), 'y': float(-raw_x)} for raw_x, raw_y in zip(lx, ly)]
                    
                    lidar_abs_x = self.robot_pose['x'] + self.LIDAR_OFFSET_X * math.cos(self.robot_pose['theta'])
                    lidar_abs_y = self.robot_pose['y'] + self.LIDAR_OFFSET_X * math.sin(self.robot_pose['theta'])
                    
                    payload = {
                        'pose': {
                            'x': float(lidar_abs_x),
                            'y': float(lidar_abs_y),
                            'theta': float(self.robot_pose['theta'])
                        },
                        'state': str(self.explore_state),
                        'lidar': lidar_data
                    }
                    
                    while not self.data_queue.empty():
                        try:
                            self.data_queue.get_nowait()
                        except:
                            break
                    self.data_queue.put(payload)
                else:
                    self.explore_state = "PAUSED"
                    self.drive_and_update_pose(car, "STOP", dt)
                
                time.sleep(0.01)
                
        finally:
            print("[LiDAR] 하드웨어 안전 종료 프로세스 진행 중...")
            try:
                car.stop()
                car.steering = 0.0
                lidar.stopMotor()
            except:
                pass
            time.sleep(0.5)

    def drive_and_update_pose(self, car, command, dt):
        applied_speed = 0.0
        final_steering = self.STEERING_TRIM

        if command == "FORWARD":
            final_steering = self.STEERING_TRIM; applied_speed = self.BASE_SPEED
        elif command == "TURN_LEFT":
            final_steering = -1.0; applied_speed = self.BASE_SPEED
        elif command == "BACKWARD":
            final_steering = self.STEERING_TRIM; applied_speed = -self.BASE_SPEED     
        elif command == "SHARP_RIGHT":         
            final_steering = 1.0; applied_speed = self.BASE_SPEED
        elif command == "SMOOTH_RIGHT":
            final_steering = 0.5; applied_speed = self.BASE_SPEED
        elif command == "FORWARD_RIGHT":
            final_steering = 0.3; applied_speed = self.BASE_SPEED
        elif command == "FORWARD_LEFT":
            final_steering = -0.3; applied_speed = self.BASE_SPEED
        elif command == "SHARP_LEFT":
            final_steering = -0.6; applied_speed = self.BASE_SPEED
        elif command == "STOP":
            final_steering = 0.0; applied_speed = 0.0

        if self.current_hardware_speed is not None and applied_speed != 0:
            if (self.current_hardware_speed > 0 and applied_speed < 0) or (self.current_hardware_speed < 0 and applied_speed > 0):
                car.stop()
                time.sleep(0.15) 
                self.kinematic_speed = 0.0 

        if final_steering != self.current_hardware_steering:
            car.steering = final_steering
            self.current_hardware_steering = final_steering
            
        if applied_speed != self.current_hardware_speed:
            if applied_speed > 0: car.forward(abs(applied_speed))
            elif applied_speed < 0: car.backward(abs(applied_speed))
            else: car.stop()
            self.current_hardware_speed = applied_speed

        try:
            raw_gz = car.getGyro('z')
            gz_adj = raw_gz - self.GYRO_Z_OFFSET
            if abs(gz_adj) < 1.0: gz_adj = 0.0
            angular_velocity = gz_adj * self.GYRO_SCALE * self.GYRO_DIRECTION
        except Exception:
            angular_velocity = 0.0

        self.kinematic_speed += (applied_speed - self.kinematic_speed) * 0.15
        if abs(self.kinematic_speed) < 8.0:
            active_speed = 0.0
        else:
            active_speed = self.kinematic_speed

        linear_velocity = active_speed * self.CMD_TO_METERS_PER_SEC
        
        d_theta = angular_velocity * dt

        if abs(angular_velocity) > 0.001:
            radius = linear_velocity / angular_velocity
            dx = radius * (math.sin(self.robot_pose['theta'] + d_theta) - math.sin(self.robot_pose['theta']))
            dy = radius * (math.cos(self.robot_pose['theta']) - math.cos(self.robot_pose['theta'] + d_theta))
        else:
            dx = linear_velocity * math.cos(self.robot_pose['theta']) * dt
            dy = linear_velocity * math.sin(self.robot_pose['theta']) * dt
        
        self.robot_pose['x'] += dx
        self.robot_pose['y'] += dy
        self.robot_pose['theta'] += d_theta
        self.robot_pose['theta'] = self.robot_pose['theta'] % (2 * math.pi)

    def calculate_steering_from_xy(self, lx, ly, current_time, is_stair=False):
        front_dists = []
        diag_right_dists = []
        right_dists = []

        for raw_x, raw_y in zip(lx, ly):
            x = raw_y; y = -raw_x
            dist = math.hypot(x, y)
            if dist < self.MIN_VALID_DIST or dist > self.MAX_VALID_DIST: continue
            angle = math.degrees(math.atan2(y, x))

            if x > 0 and abs(y) <= 200: front_dists.append(dist)
            if -60 <= angle <= -15: diag_right_dists.append(dist)
            if -130 <= angle < -60: right_dists.append(dist)

        def get_robust_dist(dist_list, default_val):
            if len(dist_list) < 3: return default_val
            return sorted(dist_list)[2]

        front_dist = get_robust_dist(front_dists, self.MAX_VALID_DIST)
        diag_right_dist = get_robust_dist(diag_right_dists, self.MAX_VALID_DIST)
        right_dist = get_robust_dist(right_dists, self.MAX_VALID_DIST)

        # 🚨 [센서 퓨전 개선] 공간(Odometry) 기반 장애물 메모리
        # 카메라가 계단을 포착하면 회피 모드 ON, 현재의 차체 각도(theta) 기록
        if is_stair:
            if not self.stair_evasion_mode:
                self.stair_evasion_mode = True
                self.stair_evasion_start_theta = self.robot_pose['theta']
                print("[LiDAR] 계단 포착! 공간 기반 회피 기동 시작")

        # 회피 모드 중일 때의 동작
        if self.stair_evasion_mode:
            # 현재 차체 각도와 회피 시작 각도의 차이 계산 (최단 회전각)
            diff = abs(self.robot_pose['theta'] - self.stair_evasion_start_theta)
            if diff > math.pi:
                diff = 2 * math.pi - diff

            # 차체가 60도(약 1.05 라디안) 이상 왼쪽으로 틀어졌다면, 
            # 계단은 이제 우측 라이다의 시야(right_dist)에 완벽히 들어오므로 회피 모드 종료
            if diff > math.radians(60):
                self.stair_evasion_mode = False
                print("[LiDAR] 회피 기동 완료. LiDAR 우측 벽 추종으로 전환")
            else:
                # 60도를 돌 때까지는 카메라 시야 상실 여부와 무관하게 무조건 정면에 벽이 있다고 강제
                front_dist = 380 

        # 아래는 기존 주행 상태 머신
        if front_dist < self.CRITICAL_FRONT and self.explore_state != "BACKING_UP":
            self.explore_state = "BACKING_UP"
            self.backup_start_time = current_time 

        if self.explore_state == "BACKING_UP":
            time_spent = current_time - self.backup_start_time
            if (time_spent > self.BACKUP_MIN_TIME and front_dist >= self.BACKUP_TARGET) or (time_spent > self.BACKUP_MAX_TIME):
                self.explore_state = "ALIGNING"
                return "TURN_LEFT", 90.0
            return "BACKWARD", 0.0

        elif self.explore_state == "INIT" or self.explore_state == "PAUSED":
            if front_dist < self.SAFE_FRONT:
                self.explore_state = "ALIGNING"
                return "TURN_LEFT", 90.0
            self.explore_state = "INIT"
            return "FORWARD", 0.0

        elif self.explore_state == "ALIGNING":
            if front_dist < 600: return "TURN_LEFT", 90.0
            else:
                if right_dist < 1000 or diag_right_dist < 1000:
                    self.explore_state = "FOLLOWING"
                    return "FORWARD", 0.0
                elif front_dist > 1200 and right_dist > 1200 and diag_right_dist > 1200:
                    self.explore_state = "INIT"
                    return "FORWARD", 0.0
                return "TURN_LEFT", 90.0

        elif self.explore_state == "FOLLOWING":
            if right_dist > 1000:
                if front_dist < 400: 
                    self.explore_state = "ALIGNING"
                    return "TURN_LEFT", 90.0
                return "SHARP_RIGHT", -90.0
            elif right_dist > 700:
                if front_dist < 450:
                    self.explore_state = "ALIGNING"
                    return "TURN_LEFT", 90.0
                return "SMOOTH_RIGHT", -45.0
            if front_dist < self.SAFE_FRONT:
                self.explore_state = "ALIGNING"
                return "TURN_LEFT", 90.0
            if right_dist < 180: return "SHARP_LEFT", 90.0
            elif diag_right_dist < 220: return "FORWARD_LEFT", 30.0
            elif right_dist > self.TARGET_WALL_DIST + self.MARGIN: return "FORWARD_RIGHT", -30.0
            elif right_dist < self.TARGET_WALL_DIST - self.MARGIN: return "FORWARD_LEFT", 30.0
            else: return "FORWARD", 0.0

        return "FORWARD", 0.0