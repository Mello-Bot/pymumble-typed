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
        self._logger = voice.logger.getChild(self.__class__.__name__)

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

        if time() - self._sequence_last_time <= self._encoder.audio_per_packet:
            pcm = self._remaining_sample + pcm
        self._remaining_sample = bytes()

        offset = len(pcm) // samples
        i = 0
        for i in range(0, offset * samples, samples):
            self._buffer.put(pcm[i:i + samples])
        self._remaining_sample = pcm[i:]
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
        while self._buffer.qsize() > 0 and audio_encoded < audio_per_packet:
            pcm = self._buffer.get(block=False)
            encoded = self._encoder.encode(pcm)
            audio.add_chunk(encoded)
            audio_encoded += self._encoder.encoder_framesize
        audio.target = self.target
        audio.sequence = self._sequence
        audio.positional = self.positional
        self._voice.send_packet(audio)
        delay = audio_per_packet - (time() - self._sequence_last_time)
        if delay >= 0:
            sleep(delay)
        else:
            self._logger.warning(f"delay is negative: {delay}!")

    @property
    def encoder(self):
        return self._encoder
