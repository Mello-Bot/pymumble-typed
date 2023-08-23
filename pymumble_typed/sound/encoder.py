from threading import Lock

from pymumble_typed.sound import AUDIO_PER_PACKET, SAMPLE_RATE, CodecProfile, BANDWIDTH, CHANNELS
from opuslib import Encoder as OpusEncoder, OpusError


class Encoder:
    def __init__(self):
        self._audio_per_packet: float = AUDIO_PER_PACKET
        self._sample_rate: int = SAMPLE_RATE
        self._channels: int = CHANNELS
        self._sample_size = self._channels * 2
        self._codec_profile: CodecProfile = CodecProfile.Audio
        self._encoder: OpusEncoder = OpusEncoder(self._sample_rate, self._channels, self._codec_profile)
        self._bandwidth: int = BANDWIDTH
        self._samples = int(self.encoder_framesize * self._sample_rate * self.sample_size)
        self._encoder_ready = Lock()

    def _update_encoder(self):
        self._encoder_ready.acquire(blocking=True)
        self._encoder: OpusEncoder = OpusEncoder(self._sample_rate, self._channels, self._codec_profile)
        self._encoder_ready.release()

    @property
    def encoder_framesize(self):
        # FIXME: ???
        return self._audio_per_packet

    def _calc_sample_size(self):
        self._sample_size = self._channels * 2

    def _calc_samples(self):
        self._calc_sample_size()
        self._samples = int(self.encoder_framesize * self._sample_rate * self._sample_size)

    def encode(self, pcm: bytes) -> bytes:
        if len(pcm) < self._samples:
            pcm += b'\x00' * (self._samples - len(pcm))
        try:
            self._encoder_ready.acquire(blocking=True)
            encoded = self._encoder.encode(pcm, len(pcm) // self._sample_size)
            self._encoder_ready.release()
        except OpusError:
            encoded = b''
        return encoded

    @property
    def sample_size(self):
        return self._sample_size

    @property
    def samples(self):
        return self._samples

    @property
    def bandwidth(self):
        return self._bandwidth

    @bandwidth.setter
    def bandwidth(self, bandwidth: int):
        self._bandwidth = bandwidth
        overhead_per_packet = 20
        # FIXME: ??? self._audio_per_packet == self.encoder_framesize, results 1
        overhead_per_packet += (3 * int(self._audio_per_packet) / self.encoder_framesize)
        # TODO: UDP Code
        overhead_per_packet += 20  # TCP Header
        overhead_per_packet += 6  # TCPTunnel Encapsulation
        overhead_per_second = int(overhead_per_packet * 8 / self._audio_per_packet)
        self._encoder.bitrate = self._bandwidth - overhead_per_second

    @property
    def audio_per_packet(self):
        return self._audio_per_packet

    @audio_per_packet.setter
    def audio_per_packet(self, adp: float):
        self._audio_per_packet = adp
        # FIXME: this is changing the framesize
        self._calc_samples()

    @property
    def channels(self):
        return self._channels

    @channels.setter
    def channels(self, channels: int):
        if channels != 1 and channels != 2:
            raise ValueError("Invalid number of channels")
        self._channels = channels
        self._calc_samples()
        self._update_encoder()

    @property
    def sample_rate(self):
        return self._sample_rate

    @sample_rate.setter
    def sample_rate(self, rate: int):
        self._sample_rate = rate
        self._calc_samples()
        self._update_encoder()

    @property
    def codec_profile(self):
        return self._codec_profile

    @codec_profile.setter
    def codec_profile(self, profile: CodecProfile):
        self._codec_profile = profile
        self._update_encoder()
