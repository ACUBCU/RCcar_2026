# 수집한 데이터로 학습하는 코드
from pop import Pilot
cam = Pilot.Camera(width=300, height=300)

CA = Pilot.Collision_Avoid(cam)
CA.load_datasets()
CA.train(times=10) # 10 epoch

# 모델 평가
print(CA.run())