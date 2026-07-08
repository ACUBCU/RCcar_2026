from tensorflow import keras
# 모델 구성
model = keras.models.Sequential()
model.add(keras.layers.Input(shape=(1,)))  # 입력층: X1
model.add(keras.layers.Dense(4))           # 첫 번째 은닉층: 4개 노드
model.add(keras.layers.Dense(2))           # 두 번째 은닉층: 2개 노드
model.add(keras.layers.Dense(1))           # 출력층: Y2
model.compile(loss='MAE', optimizer='Adam')

model.summary()

#Cds와 조도계값을 담을 1차원 배열 / 임의의 값을 넣어둠
import numpy as np
a = np.array([1.0, 2.0, 3.0, 4.0, 5.0], dtype=float)
b = np.array([1.0, 2.0, 3.0, 4.0, 5.0], dtype=float)

# 모델 학습
model.fit(a, b, epochs=500, verbose=0)