# 휠 얼라이먼트 오차제어
from pop import Pilot
from pop import AI
import numpy as np
import time

Car = Pilot.AutoCar()

forward_dataset = {'gyro' : [], 'steer' : []}
backward_dataset = {'gyro' : [], 'steer' : []}

# 데이터 수집
for i in range(-1, 1.1, 0.1):
    Car.steering = i
    Car.forward()
    time.sleep(0.5)

    forward_gyro = Car.getGyro('z')
    time.sleep(0.5)

    Car.backward()
    time.sleep(0.5)

    backward_gyro = Car.getGyro('z')
    time.sleep(1)

    Car.stop()

    forward_dataset['gyro'].append(forward_gyro)
    forward_dataset['steer'].append(i)

    backward_dataset['gyro'].append(backward_gyro)
    backward_dataset['steer'].append(i)

# 학습
forward_LR = AI.Linear_Regression(input_size = 1, output_size = 1)
forward_LR.X_data = forward_dataset['gyro']
forward_LR.Y_data = forward_dataset['steer']
forward_LR.train(times = 5000, print_every = 100)

backward_LR = AI.Linear_Regression(input_size = 1, output_size = 1)
backward_LR.X_data = backward_dataset['gyro']
backward_LR.Y_data = backward_dataset['steer']
backward_LR.train(times = 5000, print_every = 100)

print(f'전진 조향 제어 값 : {forward_LR.run([0])}')
print(f'후진 조향 제어 값 : {backward_LR.run([0])}')