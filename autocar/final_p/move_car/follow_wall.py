import time
import math
import numpy as np
from multiprocessing import Process, Queue, Event

from pop.Pilot import get_Control
from pop.LiDAR.rplidar import Rplidar

class LidarExplorer(Process):
    def __init__(self, data_queue, stop_event):
        super().__init__()
        self.data_queue = data_queue
        self.stop_event = stop_event
        
        # 🚨 [수정 1] 실내 주행에 맞춰 전방 회피 기준을 90cm에서 60cm로 축소
        self.SAFE_FRONT = 600          
        self.CRITICAL_FRONT = 350      # 긴급 제동 기준도 35cm로 살짝 축소
        self.BACKUP_TARGET = 700       
        self.BACKUP_MIN_TIME = 0.5     
        self.BACKUP_MAX_TIME = 1.5     
        self.backup_start_time = 0.0
        
        self.TARGET_WALL_DIST = 400    
        self.MARGIN = 150              
        
        self.MIN_VALID_DIST = 200      
        self.MAX_VALID_DIST = 6000
        self.MAP_SIZE = 100
        self.RESOLUTION = 100
        self.CENTER = self.MAP_SIZE // 2
        
        self.BASE_SPEED = 50           
        self.STEERING_TRIM = 0.0
        
        self.current_hardware_speed = None
        self.current_hardware_steering = None
        
        self.robot_pose = {'x': 0.0, 'y': 0.0, 'theta': math.pi / 2}
        self.CMD_TO_METERS_PER_SEC = 0.015
        self.GYRO_SCALE = (1.0 / 131.0) * (math.pi / 180.0)
        self.GYRO_Z_OFFSET = 0.0
        self.GYRO_DIRECTION = 1.0 

        self.explore_state = "INIT"

    def run(self):
        car = get_Control() 
        lidar = Rplidar()
        lidar.connect("/dev/ttyUSB0")
        lidar.startMotor()
        
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
                
                lx, ly = coords[:, 0], coords[:, 1]
                
                command, target_angle = self.calculate_steering_from_xy(lx, ly, current_time)
                self.drive_and_update_pose(car, command, dt)
                
                time.sleep(0.01)
                
        finally:
            try:
                car.stop()
                car.steering = 0.0
            except:
                pass
            try:
                lidar.stopMotor()
            except:
                pass
            time.sleep(0.5)

    def drive_and_update_pose(self, car, command, dt):
        applied_speed = 0.0
        final_steering = self.STEERING_TRIM

        if command == "FORWARD":
            final_steering = self.STEERING_TRIM
            applied_speed = self.BASE_SPEED
        elif command == "TURN_LEFT":
            final_steering = -1.0   
            applied_speed = self.BASE_SPEED
        elif command == "BACKWARD":
            final_steering = self.STEERING_TRIM  
            applied_speed = -self.BASE_SPEED     
            
        elif command == "SHARP_RIGHT":         
            final_steering = 1.0    
            applied_speed = self.BASE_SPEED
        elif command == "SMOOTH_RIGHT":
            final_steering = 0.5    
            applied_speed = self.BASE_SPEED
            
        elif command == "FORWARD_RIGHT":
            final_steering = 0.3    
            applied_speed = self.BASE_SPEED
        elif command == "FORWARD_LEFT":
            final_steering = -0.3   
            applied_speed = self.BASE_SPEED
        elif command == "SHARP_LEFT":
            final_steering = -0.6   
            applied_speed = self.BASE_SPEED
            
        elif command == "STOP":
            final_steering = 0.0
            applied_speed = 0.0

        if final_steering != self.current_hardware_steering:
            car.steering = final_steering
            self.current_hardware_steering = final_steering
            
        if applied_speed != self.current_hardware_speed:
            if applied_speed > 0:
                car.forward(abs(applied_speed))
            elif applied_speed < 0:
                car.backward(abs(applied_speed))
            else:
                car.stop()
            self.current_hardware_speed = applied_speed

        try:
            raw_gz = car.getGyro('z')
            angular_velocity = (raw_gz - self.GYRO_Z_OFFSET) * self.GYRO_SCALE * self.GYRO_DIRECTION
        except Exception:
            angular_velocity = 0.0

        linear_velocity = applied_speed * self.CMD_TO_METERS_PER_SEC
        self.robot_pose['theta'] += angular_velocity * dt
        self.robot_pose['x'] += linear_velocity * math.cos(self.robot_pose['theta']) * dt
        self.robot_pose['y'] += linear_velocity * math.sin(self.robot_pose['theta']) * dt

    def calculate_steering_from_xy(self, lx, ly, current_time):
        front_dists = []
        diag_right_dists = []
        right_dists = []

        for raw_x, raw_y in zip(lx, ly):
            x = raw_y
            y = -raw_x

            dist = math.hypot(x, y)
            if dist < self.MIN_VALID_DIST or dist > self.MAX_VALID_DIST: 
                continue

            angle = math.degrees(math.atan2(y, x))

            if x > 0 and abs(y) <= 200: 
                front_dists.append(dist)
            if -60 <= angle <= -15:
                diag_right_dists.append(dist)
            if -130 <= angle < -60:
                right_dists.append(dist)

        def get_robust_dist(dist_list, default_val):
            if len(dist_list) < 3:
                return default_val
            return sorted(dist_list)[2]

        front_dist = get_robust_dist(front_dists, self.MAX_VALID_DIST)
        diag_right_dist = get_robust_dist(diag_right_dists, self.MAX_VALID_DIST)
        right_dist = get_robust_dist(right_dists, self.MAX_VALID_DIST)

        # 0. 충돌 방지 및 후진 진입
        if front_dist < self.CRITICAL_FRONT and self.explore_state != "BACKING_UP":
            self.explore_state = "BACKING_UP"
            self.backup_start_time = current_time 

        # 1. 후진 모드
        if self.explore_state == "BACKING_UP":
            time_spent = current_time - self.backup_start_time
            if (time_spent > self.BACKUP_MIN_TIME and front_dist >= self.BACKUP_TARGET) or (time_spent > self.BACKUP_MAX_TIME):
                self.explore_state = "ALIGNING"
                return "TURN_LEFT", 90.0
            return "BACKWARD", 0.0

        # 2. 탐색 모드
        elif self.explore_state == "INIT":
            if front_dist < self.SAFE_FRONT:
                self.explore_state = "ALIGNING"
                return "TURN_LEFT", 90.0
            return "FORWARD", 0.0

        # 3. 정렬 모드
        elif self.explore_state == "ALIGNING":
            if front_dist < 600: # SAFE_FRONT 감소에 맞춰 하향
                return "TURN_LEFT", 90.0
            else:
                if right_dist < 1000 or diag_right_dist < 1000:
                    self.explore_state = "FOLLOWING"
                    return "FORWARD", 0.0
                elif front_dist > 1200 and right_dist > 1200 and diag_right_dist > 1200:
                    self.explore_state = "INIT"
                    return "FORWARD", 0.0
                return "TURN_LEFT", 90.0

        # 4. 벽 타기 모드
        elif self.explore_state == "FOLLOWING":
            
            # 🚨 [핵심 수정 2] 틈새 진입을 최우선으로 검사 (우선순위 역전)
            # 우측 입구가 발견되면, 코너를 도는 중이므로 정면 기준을 40cm로 완화하여 강제 진입
            if right_dist > 1000:
                if front_dist < 400: # 코너 돌다가 진짜 박을 것 같을 때만 좌회전 회피
                    self.explore_state = "ALIGNING"
                    return "TURN_LEFT", 90.0
                return "SHARP_RIGHT", -90.0
                
            elif right_dist > 700:
                if front_dist < 450:
                    self.explore_state = "ALIGNING"
                    return "TURN_LEFT", 90.0
                return "SMOOTH_RIGHT", -45.0
            
            # 🚨 우측에 입구가 없는 '일반 직진(벽 타기)' 상태일 때만 SAFE_FRONT(60cm) 적용
            if front_dist < self.SAFE_FRONT:
                self.explore_state = "ALIGNING"
                return "TURN_LEFT", 90.0
            
            # 벽 너무 가까워짐 방지 (패닉 억제)
            if right_dist < 180: 
                return "SHARP_LEFT", 90.0
            elif diag_right_dist < 220: 
                return "FORWARD_LEFT", 30.0
                
            # 정상적인 벽 간격 조절
            elif right_dist > self.TARGET_WALL_DIST + self.MARGIN:
                return "FORWARD_RIGHT", -30.0
            elif right_dist < self.TARGET_WALL_DIST - self.MARGIN:
                return "FORWARD_LEFT", 30.0
            else:
                return "FORWARD", 0.0

        return "FORWARD", 0.0