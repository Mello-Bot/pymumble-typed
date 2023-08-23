from threading import Lock, Thread
from time import time, sleep

from pymumble_typed.network.control import ControlStack
from pymumble_typed.network.udp_data import AudioData
from pymumble_typed.network.voice import VoiceStack
from pymumble_typed.sound import SEQUENCE_RESET_INTERVAL, SEQUENCE_DURATION
from pymumble_typed.sound.encoder import Encoder


class VoiceOutput:
    def __init__(self, control: ControlStack, voice: VoiceStack):
        self.positional = [0, 0, 0]
        self._buffer: list[bytes] = []
        self._encoder: Encoder = Encoder()
        self._buffer_lock = Lock()
        self.target: int = 0

        self._control = control
        self._voice = voice

        self._sequence_start_time = 0
        self._sequence_last_time = 0
        self._sequence = 0

        self._thread = Thread(target=self.send_audio, name="VoiceOutput:SendAudio")

    # Legacy code support
    def add_sound(self, pcm: bytes):
        self.add_pcm(pcm)

    def add_pcm(self, pcm: bytes):
        if len(pcm) % 2 != 0:
            raise ValueError("pcm data must be 16 bits")
        samples = self._encoder.samples
        self._buffer_lock.acquire(blocking=True)
        if len(self._buffer) and len(self._buffer[-1]) < samples:
            initial_offset = samples - len(self._buffer[-1])
            self._buffer[-1] += pcm[:initial_offset]
        else:
            initial_offset = 0
        for i in range(initial_offset, len(pcm), samples):
            self._buffer.append(pcm[i:i + samples])
        self._buffer_lock.release()
        if not self._thread.is_alive():
            self._thread = Thread(target=self.send_audio, name="VoiceOutput:SendAudio")
            self._thread.start()

    def clear_buffer(self):
        self._buffer_lock.acquire(blocking=True)
        self._buffer = []
        self._buffer_lock.release()

    def get_buffer_size(self):
        sample_rate = self._encoder.sample_rate
        channels = self._encoder.channels
        return sum(len(chunk) for chunk in self._buffer) / 2. / sample_rate / channels

    def send_audio(self):
        self._control.is_ready()
        timeout = False
        while self._control.is_connected() and not timeout:
            audio_per_packet = self._encoder.audio_per_packet
            while len(self._buffer) > 0 and self._sequence_last_time + audio_per_packet <= time():
                current_time = time()
                # waited enough, resetting sequence to 0
                if self._sequence_last_time + SEQUENCE_RESET_INTERVAL <= current_time:
                    self._sequence = 0
                    self._sequence_start_time = current_time
                    self._sequence_last_time = current_time
                # give some slack (2*audio_per_frame) before interrupting a continuous sequence
                elif self._sequence_last_time + (audio_per_packet * 2) <= current_time:
                    # calculating sequence after a pause
                    self._sequence = int((current_time - self._sequence_start_time) / SEQUENCE_DURATION)
                    self._sequence_last_time = self._sequence_start_time + (self._sequence * SEQUENCE_DURATION)
                else:  # continuous sound
                    self._sequence += int(audio_per_packet / SEQUENCE_DURATION)
                    self._sequence_last_time = self._sequence_start_time + (self._sequence * SEQUENCE_DURATION)

                audio = AudioData()
                audio_encoded = 0

                while len(self._buffer) > 0 and audio_encoded < audio_per_packet:
                    self._buffer_lock.acquire()
                    pcm = self._buffer.pop(0)
                    self._buffer_lock.release()
                    encoded = self._encoder.encode(pcm)
                    audio.add_chunk(encoded)
                    audio_encoded += self._encoder.encoder_framesize
                audio.target = self.target
                audio.sequence = self._sequence
                audio.positional = self.positional
                self._voice.send_packet(audio)
            sleep(0.01)
            timeout = time() - self._sequence_last_time > 0.1

    @property
    def encoder(self):
        return self._encoder
