from time import sleep, time, monotonic
from queue import Full, Queue

from pymumble_typed.network.control import ControlStack
from pymumble_typed.network.udp_data import AudioData
from pymumble_typed.network.voice import VoiceStack
from pymumble_typed.sound import SEQUENCE_DURATION, SEQUENCE_RESET_INTERVAL
from pymumble_typed.sound.encoder import Encoder


class VoiceOutput:
    def __init__(self, control: ControlStack, voice: VoiceStack):
        self.positional: [int, int, int] | None = None
        self._remaining_sample: bytes = b''
        self._encoder: Encoder = Encoder(voice)
        self._buffer: Queue[bytes] = Queue(maxsize=int(2 / self._encoder.audio_per_packet))
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

        # Discard the remaining sample if too much time has passed from the previous sent.
        # This should avoid adding delay to the audio sent or sending audio out of order.
        if monotonic() - self._sequence_last_time <= self._encoder.audio_per_packet:
            pcm = self._remaining_sample + pcm
        self._remaining_sample = b''

        offset = len(pcm) // samples
        processed = offset * samples
        try:
            for i in range(0, processed, samples):
                self._buffer.put(pcm[i:i + samples], block=False)
            self._remaining_sample = pcm[processed:]
        except Full:
            self._logger.warning(f"Buffer is full! Dropping audio packet!")
        self.send_audio()

    def _update_sequence(self):
        audio_per_packet = self._encoder.audio_per_packet
        current_time = monotonic()
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
        self._buffer = Queue(maxsize=int(2 / self._encoder.audio_per_packet))

    def send_audio(self):
        if not self._buffer.qsize() > 0:
            return
        while self._buffer.qsize() > 0:
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
            delay = audio_per_packet - (monotonic() - self._sequence_last_time)
            if delay >= 0:
                sleep(delay)
            else:
                self._logger.warning(f"delay is negative: {delay}!")

    @property
    def encoder(self):
        return self._encoder
