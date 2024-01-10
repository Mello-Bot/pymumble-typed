from queue import Queue
from time import time, sleep

from pymumble_typed.network.control import ControlStack
from pymumble_typed.network.udp_data import AudioData
from pymumble_typed.network.voice import VoiceStack
from pymumble_typed.sound import SEQUENCE_RESET_INTERVAL, SEQUENCE_DURATION
from pymumble_typed.sound.encoder import Encoder


class VoiceOutput:
    def __init__(self, control: ControlStack, voice: VoiceStack):
        self.positional = [0, 0, 0]
        self._buffer: Queue[bytes] = Queue()
        self._remaining_sample: bytes = bytes()
        self._encoder: Encoder = Encoder(voice)
        self.target: int = 0

        self._control = control
        self._voice = voice

        self._sequence_start_time = 0
        self._sequence_last_time = 0
        self._sequence = 0

    # Legacy code support
    def add_sound(self, pcm: bytes):
        self.add_pcm(pcm)

    def add_pcm(self, pcm: bytes):
        if len(pcm) % 2 != 0:
            raise ValueError("pcm data must be 16 bits")
        samples = self._encoder.samples
        if len(self._remaining_sample) < samples:
            initial_offset = samples - len(self._remaining_sample)
            self._remaining_sample += pcm[initial_offset:]
            self._buffer.put(self._remaining_sample)
            self._remaining_sample = bytes()
        else:
            initial_offset = 0
        remaining = len(pcm) % samples
        self._remaining_sample = pcm[-remaining:]
        for i in range(initial_offset, len(pcm) - remaining, samples):
            self._buffer.put(pcm[i:i + samples])
        self.send_audio()

    def _update_sequence(self):
        audio_per_packet = self._encoder.audio_per_packet
        current_time = time()
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

    def clear_buffer(self):
        self._buffer = Queue()

    def send_audio(self):
        audio_per_packet = self._encoder.audio_per_packet
        self._update_sequence()
        audio = AudioData()
        audio_encoded = 0
        pcm = self._buffer.get()
        while pcm and audio_encoded < audio_per_packet:
            encoded = self._encoder.encode(pcm)
            audio.add_chunk(encoded)
            audio_encoded += self._encoder.encoder_framesize
            if audio_encoded < audio_per_packet:
                pcm = self._buffer.get()
        audio.target = self.target
        audio.sequence = self._sequence
        audio.positional = self.positional
        self._voice.send_packet(audio)
        sleep(audio_per_packet - (time() - self._sequence_last_time))

    @property
    def encoder(self):
        return self._encoder
