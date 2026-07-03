# AutoCar Prime + NX (_cat=6) GPIO / PWM 문제 정리

## 장비 정보

| 항목 | 내용 |
|------|------|
| 기기명 | AutoCar Prime + NX (`_cat = 6`) |
| OS | Ubuntu 18.04 + JetPack (Linux 4.9.140-tegra, aarch64) |
| IP | 192.168.0.34 |
| I²C bus 1 장치 | `0x5c` (PCA9685 서보+LED), `0x5e` (PCA9685 모터) |
| USB | `10c4:ea60` CP210x → LiDAR (has_lidar = True) |

---

## 1. LED가 GPIO로 안 켜지는 문제

### 증상
`Led(23).on()` 등 RPi.GPIO BCM 번호로 LED 제어 시도 → 켜지지 않음

### 원인
AutoCar Prime + NX의 헤드/테일 LED는 **RPi.GPIO 직접 핀이 아닌
I²C bus 1, 주소 `0x5c`의 PCA9685 PWM 컨트롤러**에 연결되어 있음.
pop 라이브러리의 `Led` 클래스(RPi.GPIO 사용)로는 제어 불가능.

### PCA9685 채널 배분 (bus=1, addr=0x5c)

| 채널 | 용도 |
|------|------|
| 0 ~ 12 | LED (앞뒤 각 2개 포함) |
| 13 | 카메라팟 Pan 서보 (Horizontal_GPIO) |
| 14 | 카메라팟 Tilt 서보 (Vertical_GPIO) |
| 15 | 조향 서보 (GPIO_SERVO) |

### 해결 - LED 제어 코드

```python
from pop import Pilot

led = Pilot.PWM(1, 0x5c)
led.setFreq(50)

led.setDuty(0, 100)   # ch0 최대 밝기
led.setDuty(0, 50)    # ch0 50% 밝기
led.setDuty(0, 0)     # ch0 끄기
```

### 프로토콜 구조

```
Jetson NX  ──I²C bus 1──►  PCA9685 (0x5c)  ──PWM──►  LED
```

---

## 2. 상단 센서 모듈 (카메라팟) 제어

```python
from pop import Pilot

car = Pilot.AutoCar()     # _cat=6 자동 감지

# 카메라 팬 (좌우, PCA9685 ch13)
car.camPan(0)             # 중앙
car.cam2Left(30)          # 왼쪽 30도
car.cam2Right(30)         # 오른쪽 30도

# 카메라 틸트 (상하, PCA9685 ch14)
car.camTilt(0)            # 정면
car.cam2Front()           # 앞으로
car.cam2Back()            # 뒤로 (LiDAR 장착 시 90도로 자동 제한)
```

> **참고**: LiDAR가 USB에 연결되어 있으면 (`has_lidar=True`) `cam2Back()` 시 틸트가 90도로 제한됨.

---

## 3. PiezoBuzzer가 동작하지 않는 문제

### 증상

```
FileNotFoundError: [Errno 2] No such file or directory:
  '/sys/devices/32f0000.pwm/pwm/pwmchip4/pwm0/enable'
```
또는
```
PermissionError: [Errno 13] Permission denied:
  '/sys/devices/32f0000.pwm/pwm/pwmchip4/pwm0/period'
```
또는
```
RuntimeError: Please set pin numbering mode using GPIO.setmode(...)
```

### 원인 분석

#### 원인 A: `pwm0`가 export되지 않음
Jetson NX는 재부팅 후 `/sys/class/pwm/pwmchip4/pwm0` 디렉터리가 기본적으로 생성되지 않음.
`Jetson.GPIO`의 `_export_pwm()`이 자동 export를 시도하지만 핀 mux 상태에 따라 실패.

#### 원인 B: `GPIO.setup(12, OUT)`이 핀 mux를 GPIO 모드로 전환
`PiezoBuzzer.__init__`가 내부적으로 `GPIO.setup(n, GPIO.OUT)`을 호출 →
핀이 GPIO mux 모드로 전환된 상태에서 `_export_pwm`이 기존 `pwm0` 디렉터리를
발견하면 재초기화를 건너뜀 → 핀 mux가 PWM 모드로 복원되지 않음 →
`period` / `enable` 쓰기 시 **PermissionError / FileNotFoundError** 발생.

#### 원인 C: `GPIO.cleanup()` 후 모드가 None으로 초기화
`cleanup()` 이후 `GPIO.setmode()` 재설정 없이 `GPIO.setup()` 호출 시
`RuntimeError: Please set pin numbering mode` 발생.

#### 원인 D: Jupyter 셀 재실행 시 중복 PWM 객체
`_channel_configuration[12] = HARD_PWM` 잔류 →
`ValueError: Can't create duplicate PWM objects` 발생.

#### 원인 E: `os.system("echo 0 | sudo tee ...")` 조용히 실패
비TTY(Jupyter) 환경에서 `sudo tee`가 rc=1로 실패하지만
파이프 앞 `echo 0`의 리턴코드(0)가 반영되어 성공처럼 보임.

### 근본 원인 흐름

```
GPIO.setup(12, OUT)
    → 핀 mux가 GPIO 모드로 전환

GPIO.PWM(12, 261) 내부에서 cleanup(12) 호출
    → GPIO 424 unexport, 핀이 limbo 상태

_export_pwm() 에서 pwm0 이미 존재 → 건너뜀
    → 핀 mux가 PWM 모드로 복원되지 않음

period / enable 파일 쓰기
    → PermissionError / FileNotFoundError
```

### 해결 코드 (Jupyter 셀)

```python
import time
import RPi.GPIO as GPIO

# 1. 이전 실행 잔류 상태 정리 + 모드 재설정
GPIO.setwarnings(False)
GPIO.cleanup()
GPIO.setmode(GPIO.BCM)   # cleanup 후 반드시 재설정

# 2. pwm0 강제 초기화 (stale mux 방지, sudo 불필요)
#    soda 사용자는 gpio 그룹(999) 멤버이므로 직접 쓰기 가능
try:
    with open('/sys/class/pwm/pwmchip4/unexport', 'w') as f:
        f.write('0')
except OSError:
    pass

# 3. GPIO.setup(n, OUT) no-op 패치
#    → GPIO.PWM이 pwm0를 새로 export → 핀 mux가 PWM 모드로 올바르게 전환
_orig_setup = GPIO.setup
def _pwm_safe_setup(channel, direction, *args, **kwargs):
    if direction == GPIO.OUT:
        return  # GPIO.PWM이 직접 처리하도록 스킵
    return _orig_setup(channel, direction, *args, **kwargs)
GPIO.setup = _pwm_safe_setup

from pop import PiezoBuzzer
p = PiezoBuzzer(12)
GPIO.setup = _orig_setup  # 패치 복원

# 연주
butterfly_scale    = [4,4,4, 4,4,4, 4,4,4,4, 4,4,4,  4,4,4,4, 4,4,4, 4,4,4,4, 4,4,4]
butterfly_pitch    = [8,5,5, 6,3,3, 1,3,5,6, 8,8,8,  8,5,5,5, 6,3,3, 1,5,8,8, 5,5,5]
butterfly_duration = [8,8,4, 8,8,4, 8,8,8,8, 8,8,4,  8,8,8,8, 8,8,4, 8,8,8,8, 8,8,4]
sheet_butterfly = [butterfly_scale, butterfly_pitch, butterfly_duration]

p.play(sheet_butterfly)
```

### 각 원인별 해결 요약

| 원인 | 잘못된 방법 | 올바른 방법 |
|------|-------------|-------------|
| pwm0 export 실패 | `os.system("echo 0 \| sudo tee ...")` | `open('/sys/class/pwm/pwmchip4/unexport', 'w').write('0')` 후 GPIO.PWM이 자동 export |
| 핀 mux GPIO→PWM 미복원 | export만 하고 GPIO.setup 허용 | `GPIO.setup(n, OUT)`을 no-op 패치 |
| cleanup 후 모드 None | cleanup만 호출 | `cleanup()` 후 `GPIO.setmode(GPIO.BCM)` 재설정 |
| 중복 PWM 객체 | 셀 재실행 시 그냥 호출 | 셀 상단에 `GPIO.cleanup()` 추가 |

---

## 4. 하드웨어 PWM 경로 정보

| 항목 | 값 |
|------|-----|
| BCM 핀 번호 | 12 |
| Tegra GPIO 번호 | 424 |
| pwm_chip_dir | `/sys/devices/32f0000.pwm/pwm/pwmchip4` |
| pwm_id | 0 |
| export 경로 | `/sys/class/pwm/pwmchip4/export` |
| enable 경로 | `/sys/class/pwm/pwmchip4/pwm0/enable` |
| period 경로 | `/sys/class/pwm/pwmchip4/pwm0/period` |
| 파일 소유자 | `root:gpio` (soda는 gpio 그룹 멤버이므로 직접 쓰기 가능) |
