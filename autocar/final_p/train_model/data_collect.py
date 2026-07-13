# 주행 불가능 영역을 탐지하기 위한 코드
from pop import Pilot
car = Pilot.AutoCar()

car.camPan(85) #카메라 좌우 정중앙
car.camTilt(-17) # 카메라 상하 아래 최대로

cam = Pilot.Camera(width=300, height=300)
cam.show()

dataCollecter = Pilot.Data_Collector(Pilot.Collision_Avoid, camera=cam)
dataCollecter.show()