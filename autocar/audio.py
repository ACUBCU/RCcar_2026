import time

import numpy as np
import pyaudio
class Tone:
    def __init__(self, volume=0.5, rate=48000, channels=1):
        self.volume = volume
        self.rate = rate
        self.channels = channels
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(format=pyaudio.paFloat32, channels=self.channels, rate=self.rate, output=True)

    def play(self, octave=3, note=1, duration=2):
        f = 2**(octave) * 55 * 2**(((note)-10)/12)
        sample = (np.sin(2 * np.pi * np.arange(self.rate*duration) * f/self.rate)).astype(np.float32)
        self.stream.write(self.volume * sample)

    def stop(self):
        self.stream.stop_stream()
        self.stream.close()
        self.p.terminate()

tone = Tone()
for n in [1, 3, 5, 7, 8, 10, 12]:
    tone.play(3, n, 4)
tone.stop()


# 이 클래스를 사용해서 재미 있는 게임음악 멜로디를 출력하세요.
# 스타워즈, 클래식, 기타 등등... ( 능동 버저 프로젝트를 참고해서 노래를 선택해서 플레이)
# 논 블럭스타일로 클래스를 수정하세요.



class Tone:
    NOTE_TABLE = {
        "C": 0,
        "C#": 1,
        "Db": 1,
        "D": 2,
        "D#": 3,
        "Eb": 3,
        "E": 4,
        "F": 5,
        "F#": 6,
        "Gb": 6,
        "G": 7,
        "G#": 8,
        "Ab": 8,
        "A": 9,
        "A#": 10,
        "Bb": 10,
        "B": 11,
    }

    def __init__(self, volume=0.5, rate=48000, channels=1, output_device_index=None):
        self.volume = volume
        self.rate = rate
        self.channels = channels
        self.output_device_index = output_device_index

        self.p = pyaudio.PyAudio()
        self.stream = None

        self.audio_data = np.array([], dtype=np.float32)
        self.position = 0

    def print_output_devices(self):
        print("=== Output devices ===")
        for i in range(self.p.get_device_count()):
            info = self.p.get_device_info_by_index(i)
            if info["maxOutputChannels"] > 0:
                print(i, info["name"], info["maxOutputChannels"], info["defaultSampleRate"])

    def note_to_freq(self, note_name):
        if note_name == "R":
            return 0

        if len(note_name) == 2:
            name = note_name[0]
            octave = int(note_name[1])
        else:
            name = note_name[:-1]
            octave = int(note_name[-1])

        semitone = self.NOTE_TABLE[name]

        # C4 = 60, A4 = 69
        midi_number = (octave + 1) * 12 + semitone

        # A4 = 440Hz
        freq = 440.0 * (2 ** ((midi_number - 69) / 12))
        return freq

    def make_wave(self, freq, duration):
        sample_count = int(self.rate * duration)

        if freq == 0:
            return np.zeros(sample_count, dtype=np.float32)

        t = np.arange(sample_count) / self.rate
        sample = np.sin(2 * np.pi * freq * t).astype(np.float32)

        # 틱틱 소리 방지용 fade in / fade out
        fade_time = 0.01
        fade_samples = int(self.rate * fade_time)

        if fade_samples * 2 < sample_count:
            fade_in = np.linspace(0.0, 1.0, fade_samples).astype(np.float32)
            fade_out = np.linspace(1.0, 0.0, fade_samples).astype(np.float32)

            sample[:fade_samples] *= fade_in
            sample[-fade_samples:] *= fade_out

        return sample

    def make_melody_data(self, melody):
        """
        melody 예:
        [
            ("C4", 0.5),
            ("D4", 0.5),
            ("E4", 1.0),
            ("R", 0.3),
        ]
        """
        waves = []

        for note_name, duration in melody:
            freq = self.note_to_freq(note_name)
            sample = self.make_wave(freq, duration)
            waves.append(sample)

        if len(waves) == 0:
            return np.array([], dtype=np.float32)

        audio_data = np.concatenate(waves)
        audio_data = (self.volume * audio_data).astype(np.float32)

        return audio_data

    def play_callback(self, in_data, frame_count, time_info, status):
        end_position = self.position + frame_count

        chunk = self.audio_data[self.position:end_position]
        self.position = end_position

        if len(chunk) < frame_count:
            remain = frame_count - len(chunk)
            chunk = np.pad(chunk, (0, remain), mode="constant")
            return (chunk.astype(np.float32).tobytes(), pyaudio.paComplete)

        return (chunk.astype(np.float32).tobytes(), pyaudio.paContinue)

    def play_melody(self, melody):
        self.audio_data = self.make_melody_data(melody)
        self.position = 0

        if self.stream is not None:
            if self.stream.is_active():
                self.stream.stop_stream()
            self.stream.close()

        self.stream = self.p.open(
            format=pyaudio.paFloat32,
            channels=self.channels,
            rate=self.rate,
            output=True,
            output_device_index=self.output_device_index,
            stream_callback=self.play_callback
        )

        self.stream.start_stream()

    def is_playing(self):
        if self.stream is None:
            return False

        return self.stream.is_active()

    def stop(self):
        if self.stream is not None:
            if self.stream.is_active():
                self.stream.stop_stream()
            self.stream.close()
            self.stream = None

    def close(self):
        self.stop()
        self.p.terminate()

space_fanfare = [
    ("G3", 0.35),
    ("G3", 0.35),
    ("G3", 0.35),

    ("C4", 1.00),
    ("G4", 1.00),

    ("F4", 0.30),
    ("E4", 0.30),
    ("D4", 0.30),
    ("C5", 1.00),

    ("G4", 0.50),
    ("F4", 0.30),
    ("E4", 0.30),
    ("D4", 0.30),
    ("C5", 1.00),

    ("G4", 0.70),
    ("F4", 0.30),
    ("E4", 0.30),
    ("F4", 0.30),
    ("D4", 1.00),

    ("R", 0.30),

    ("G3", 0.30),
    ("G3", 0.30),
    ("G3", 0.30),
    ("C4", 1.20),
]

tone = Tone(volume=0.4)

# 장치 번호 확인이 필요하면 실행
tone.print_output_devices()

tone.play_melody(space_fanfare)

while tone.is_playing():
    print("main work...")
    time.sleep(0.1)

tone.close()