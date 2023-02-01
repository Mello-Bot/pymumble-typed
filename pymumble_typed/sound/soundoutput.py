from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pymumble_typed.Mumble_pb2 import CodecVersion
    from pymumble_typed.mumble import Mumble

from struct import pack
from threading import Lock

from opuslib import OpusError, Encoder

from pymumble_typed.commands import VoiceTarget
from pymumble_typed.tools import VarInt

from pymumble_typed.sound import AudioType, SAMPLE_RATE, SEQUENCE_RESET_INTERVAL, CodecNotSupportedError, CodecProfile
from time import time


class SoundOutput:
    def __init__(self, mumble: Mumble, audio_per_packet: int, bandwidth: int, stereo=False, profile=CodecProfile.Audio):
        self._mumble = mumble

        self._pcm = []
        self._lock = Lock()

        self._opus_profile: CodecProfile = profile
        self._encoder: Encoder | None = None
        self._encoder_framesize = None
        self._codec = None
        self._bandwidth = mumble.bandwidth
        self._audio_per_packet = audio_per_packet
        self._channels = 1 if not stereo else 2
        self._codec_type = AudioType.OPUS

        self.set_bandwidth(bandwidth)
        self.set_audio_per_packet(audio_per_packet)

        self._target = 0
        self._sequence_last_time = 0
        self._sequence = 0

    @property
    def sample_size(self):
        return self._channels * 2

    @property
    def samples(self):
        return int(self._encoder_framesize * SAMPLE_RATE * self.sample_size)

    def send_audio(self):
        if not self._encoder or len(self._pcm) == 0:
            return

        while len(self._pcm) > 0:
            if self._sequence_last_time + SEQUENCE_RESET_INTERVAL <= time():
                self._sequence = 0
            else:
                self._sequence += 1

            payload = bytearray()
            audio_encoded = 0

            while len(self._pcm) > 0 and audio_encoded < self._audio_per_packet:
                self._lock.acquire()
                to_encode = self._pcm.pop(0)
                self._lock.release()

                if len(to_encode) != self.samples:
                    to_encode += b'\x00' * (self.samples - len(to_encode))
                try:
                    encoded = self._encoder.encode(to_encode, len(to_encode) // self.sample_size)
                except OpusError:
                    encoded = b''

                audio_encoded += self._encoder_framesize

                if self._codec_type == AudioType.OPUS:
                    frame_header = VarInt(len(encoded)).encode()
                else:
                    frame_header = len(encoded)
                    if audio_encoded < self._audio_per_packet and len(self._pcm) > 0:
                        frame_header += (1 << 7)
                    frame_header = pack('!B', frame_header)

                payload += frame_header + encoded

            header = self._codec_type.value << 5
            sequence = VarInt(self._sequence).encode()

            udp_packet = pack('!B', header | self._target) + sequence + payload
            if self._mumble.positional:
                udp_packet += pack("fff", self._mumble.positional[0], self._mumble.positional[1],
                                   self._mumble.positional[2])

            self._mumble.send_audio(udp_packet)
            self._sequence_last_time = time()

    def get_audio_per_packet(self):
        return self._audio_per_packet

    def set_audio_per_packet(self, audio_per_packet):
        self._audio_per_packet = audio_per_packet
        self.create_encoder()

    def get_bandwidth(self):
        return self._bandwidth

    def set_bandwidth(self, bandwidth):
        self._bandwidth = bandwidth
        self._set_bandwidth()

    def _set_bandwidth(self):
        if self._encoder:
            overhead_per_packet = 20
            overhead_per_packet += (3 * int(self._audio_per_packet / self._encoder_framesize))
            if self._mumble.udp_active:
                overhead_per_packet += 12
            else:
                overhead_per_packet += 20  # TCP Header
                overhead_per_packet += 6  # TCPTunnel Encapsulation
            overhead_per_second = int(overhead_per_packet * 8 / self._audio_per_packet)
            self._encoder.bitrate = self._bandwidth - overhead_per_second

    def add_sound(self, pcm: bytes):
        if len(pcm) % 2 != 0:
            raise Exception("pcm data must be 16 bits")

        self._lock.acquire()
        if len(self._pcm) and len(self._pcm[-1]) < self.samples:
            initial_offset = self.samples - len(self._pcm[-1])
            self._pcm[-1] += pcm[:initial_offset]
        else:
            initial_offset = 0
        for i in range(initial_offset, len(pcm), self.samples):
            self._pcm.append(pcm[i:i + self.samples])
        self._lock.release()

    def clear_buffer(self):
        self._lock.acquire()
        self._pcm = []
        self._lock.release()

    def get_buffer_size(self):
        return sum(len(chunk) for chunk in self._pcm) / 2. / SAMPLE_RATE / self._channels

    def set_default_codec(self, codec: CodecVersion):
        self._codec = codec
        self.create_encoder()

    def create_encoder(self):
        if not self._codec:
            return
        if self._codec.opus:
            self._encoder = Encoder(SAMPLE_RATE, self._channels, self._opus_profile)

            self._encoder_framesize = self._audio_per_packet
            self._codec_type = AudioType.OPUS
        else:
            raise CodecNotSupportedError('')
        self._set_bandwidth()

    def set_whisper(self, target_id: list[int], channel=False):
        self._target = 1 if channel else 2
        command = VoiceTarget(self._target, target_id)
        self._mumble.execute_command(command)

    def remove_whisper(self):
        self._target = 0
        command = VoiceTarget(self._target, [])
        self._mumble.execute_command(command)
