from threading import Lock

from opuslib import Encoder as OpusEncoder
from opuslib import OpusError

from pymumble_typed.network.voice import VoiceStack
from pymumble_typed.sound import AUDIO_PER_PACKET, BANDWIDTH, CHANNELS, SAMPLE_RATE, CodecProfile


class Encoder:
    def __init__(self, voice: VoiceStack, channels: int = CHANNELS, codec_profile: CodecProfile = CodecProfile.Audio):
        self._check_channels(channels)
        self._audio_per_packet: float = AUDIO_PER_PACKET
        self._sample_rate: int = SAMPLE_RATE
        self._channels: int = channels
        self._codec_profile: CodecProfile = codec_profile
        self._bandwidth: int = BANDWIDTH
        self._sample_size: int = 0
        self._samples: int = 0
        self._voice = voice
        # Guards the Opus encoder and the frame sizes encode() reads: the setters may run on another thread
        # while the audio is being encoded.
        self._encoder_ready = Lock()
        self._calc_samples()
        self._encoder: OpusEncoder = self._build_encoder()
        voice.on_protocol_switch(self._recalc_bitrate)

    @staticmethod
    def _check_channels(channels: int):
        if channels not in (1, 2):
            raise ValueError("Invalid number of channels")

    def _build_encoder(self) -> OpusEncoder:
        # The channel count, sample rate and application of an Opus encoder are fixed at creation: changing them
        # needs a new encoder, which starts from the default bitrate, so the configured one is applied again.
        encoder = OpusEncoder(self._sample_rate, self._channels, self._codec_profile)
        encoder.bitrate = self._calc_bitrate()
        return encoder

    def _update_encoder(self):
        with self._encoder_ready:
            self._calc_samples()
            self._encoder = self._build_encoder()

    def _recalc_bitrate(self, _: bool):
        with self._encoder_ready:
            self._encoder.bitrate = self._calc_bitrate()

    @property
    def encoder_framesize(self):
        # FIXME(nico9889): ???
        return self._audio_per_packet

    def _calc_sample_size(self):
        # Bytes of one 16 bit sample of every channel (one interleaved PCM frame).
        self._sample_size = self._channels * 2

    def _calc_samples(self):
        self._calc_sample_size()
        self._samples = int(self.encoder_framesize * self._sample_rate * self._sample_size)

    def encode(self, pcm: bytes) -> bytes:
        with self._encoder_ready:
            if len(pcm) < self._samples:
                pcm += b"\x00" * (self._samples - len(pcm))
            try:
                encoded = self._encoder.encode(pcm, len(pcm) // self._sample_size)
            except OpusError:
                encoded = b""
        return encoded

    @property
    def sample_size(self):
        return self._sample_size

    @property
    def samples(self):
        """Bytes of interleaved 16 bit PCM, with `channels` channels, that make one encoded frame."""
        return self._samples

    def _calc_bitrate(self):
        overhead_per_packet = 20
        # FIXME(nico9889): ??? self._audio_per_packet == self.encoder_framesize, results 1
        overhead_per_packet += 3 * int(self._audio_per_packet) / self.encoder_framesize
        if self._voice.active:
            overhead_per_packet += 12
        else:
            overhead_per_packet += 20  # TCP Header
            overhead_per_packet += 6  # TCPTunnel Encapsulation
        overhead_per_second = int(overhead_per_packet * 8 / self._audio_per_packet)
        return self._bandwidth - overhead_per_second

    @property
    def bandwidth(self):
        return self._bandwidth

    @bandwidth.setter
    def bandwidth(self, bandwidth: int):
        with self._encoder_ready:
            self._bandwidth = bandwidth
            self._encoder.bitrate = self._calc_bitrate()

    @property
    def audio_per_packet(self):
        return self._audio_per_packet

    @audio_per_packet.setter
    def audio_per_packet(self, adp: float):
        if adp not in (0.0025, 0.005, 0.01, 0.02, 0.04, 0.06):
            raise ValueError(
                f"Invalid audio frame duration: {adp}. It must be in [0.0025, 0.005, 0.01, 0.02, 0.04, 0.06]."
            )
        with self._encoder_ready:
            self._audio_per_packet = adp
            # FIXME(nico9889): this is changing the framesize
            self._calc_samples()
            # The per packet overhead, and so the bitrate left to the audio, depends on the packet duration.
            self._encoder.bitrate = self._calc_bitrate()

    @property
    def channels(self):
        return self._channels

    @channels.setter
    def channels(self, channels: int):
        self._check_channels(channels)
        self._channels = channels
        self._update_encoder()

    @property
    def sample_rate(self):
        return self._sample_rate

    @sample_rate.setter
    def sample_rate(self, rate: int):
        self._sample_rate = rate
        self._update_encoder()

    @property
    def codec_profile(self):
        return self._codec_profile

    @codec_profile.setter
    def codec_profile(self, profile: CodecProfile):
        self._codec_profile = profile
        self._update_encoder()

    @property
    def bitrate(self):
        return self._calc_bitrate()
