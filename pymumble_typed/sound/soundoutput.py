from __future__ import annotations

from typing import TYPE_CHECKING

from pymumble_typed.network.udp_data import AudioData

if TYPE_CHECKING:
    from pymumble_typed.protobuf.Mumble_pb2 import CodecVersion
    from pymumble_typed.mumble import Mumble

from struct import pack
from threading import Lock

from opuslib import OpusError, Encoder

from pymumble_typed.commands import VoiceTarget
from pymumble_typed.tools import VarInt

from pymumble_typed.sound import AudioType, SAMPLE_RATE, SEQUENCE_RESET_INTERVAL, CodecNotSupportedError, CodecProfile,\
    SEQUENCE_DURATION
from time import time


class SoundOutput:
    def __init__(self, mumble: Mumble, audio_per_packet: int, bandwidth: int, stereo=False, profile=CodecProfile.Audio):
        self._mumble = mumble

        self._pcm = []
        self._lock = Lock()

        self._opus_profile: CodecProfile = profile
        self._encoder: Encoder | None = None
        self._codec = None
        self._bandwidth = bandwidth
        self._audio_per_packet = audio_per_packet
        self._encoder_framesize = self._audio_per_packet
        self._channels = 1 if not stereo else 2
        self._codec_type = AudioType.OPUS

        self.set_bandwidth(bandwidth)
        self.set_audio_per_packet(audio_per_packet)

        self._target = 0
        self._sequence_start_time = 0
        self._sequence_last_time = 0
        self._sequence = 0

    @property
    def sample_size(self):
        return self._channels * 2

    @property
    def samples(self):
        return int(self._encoder_framesize * SAMPLE_RATE * self.sample_size)

    def send_audio(self):
        if not self._encoder:
            return

        while len(self._pcm) > 0 and self._sequence_last_time + self._audio_per_packet <= time():
            current_time = time()
            if self._sequence_last_time + SEQUENCE_RESET_INTERVAL <= current_time:  # waited enough, resetting sequence to 0
                self._sequence = 0
                self._sequence_start_time = current_time
                self._sequence_last_time = current_time
            elif self._sequence_last_time + (
                    self._audio_per_packet * 2) <= current_time:  # give some slack (2*audio_per_frame) before interrupting a continuous sequence
                # calculating sequence after a pause
                self._sequence = int((current_time - self._sequence_start_time) / SEQUENCE_DURATION)
                self._sequence_last_time = self._sequence_start_time + (self._sequence * SEQUENCE_DURATION)
            else:  # continuous sound
                self._sequence += int(self._audio_per_packet / SEQUENCE_DURATION)
                self._sequence_last_time = self._sequence_start_time + (self._sequence * SEQUENCE_DURATION)

            audio = AudioData()
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
                audio.add_chunk(encoded)
                audio_encoded += self._encoder_framesize
            audio.target = self._target
            audio.codec = self._codec_type.value
            audio.sequence = self._sequence
            audio.positional = self._mumble.positional
            self._mumble.send_audio(audio.legacy_udp_packet)

    def get_audio_per_packet(self):
        return self._audio_per_packet

    def set_audio_per_packet(self, audio_per_packet):
        self._audio_per_packet = audio_per_packet
        self._create_encoder()

    def get_bandwidth(self):
        return self._bandwidth

    def set_bandwidth(self, bandwidth):
        self._bandwidth = min(96000, bandwidth)
        self._set_bandwidth()

    def _set_bandwidth(self):
        if self._encoder:
            overhead_per_packet = 20
            overhead_per_packet += (3 * int(self._audio_per_packet / self._encoder_framesize))
            # if self._mumble.udp_active:
            #     overhead_per_packet += 12
            # else:
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
        print(self._pcm.__len__())

    def clear_buffer(self):
        self._lock.acquire()
        self._pcm = []
        self._lock.release()

    def get_buffer_size(self):
        return sum(len(chunk) for chunk in self._pcm) / 2. / SAMPLE_RATE / self._channels

    def set_default_codec(self, codec: CodecVersion):
        self._codec = codec
        self._create_encoder()

    def _create_encoder(self):
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
