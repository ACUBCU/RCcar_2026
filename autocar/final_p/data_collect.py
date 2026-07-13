# 주행 불가능 영역을 탐지하기 위한 코드
from pop import Pilot

cam = Pilot.Camera(width=300, height=300)
cam.show()

dataCollecter = Pilot.Data_Collecter(Pilot.Collision_Avoid, camera=cam)
dataCollecter.show()
