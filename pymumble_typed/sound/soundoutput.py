from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pymumble_typed.Mumble_pb2 import CodecVersion
    from pymumble_typed.mumble import Mumble, MessageType

from socket import error
from struct import pack
from threading import Lock

from opuslib import OpusError, Encoder

from pymumble_typed.commands import VoiceTarget
from pymumble_typed.tools import VarInt

from pymumble_typed.sound import AudioType, SAMPLE_RATE, SEQUENCE_RESET_INTERVAL, SEQUENCE_DURATION, \
    CodecNotSupportedError
from time import time


class SoundOutput:
    def __init__(self, mumble: Mumble, audio_per_packet: int, bandwidth: int, stereo=False, profile=AudioType.OPUS):
        self._mumble = mumble
        self._pcm = []
        self._lock = Lock()
        self._codec = None
        self._encoder: Encoder | None = None
        self._encoder_framesize = None
        self._opus_profile = profile
        self._channels = 1 if not stereo else 2
        self._bandwidth = mumble.bandwidth
        self._audio_per_packet = 0
        self.set_audio_per_packet(audio_per_packet)
        self.set_bandwidth(bandwidth)
        self._codec_type = None
        self._target = 0
        self._sequence_start_time = 0
        self._sequence_last_time = 0
        self._sequence = 0

    def send_audio(self):
        if not self._encoder or len(self._pcm) == 0:
            return

        samples = int(self._encoder_framesize * SAMPLE_RATE * 2 * self._channels)

        while len(self._pcm) > 0 and self._sequence_last_time + self._audio_per_packet <= time():
            current_time = time()
            if self._sequence_last_time + SEQUENCE_RESET_INTERVAL <= current_time:
                self._sequence = 0
                self._sequence_start_time = 0
                self._sequence_last_time = 0
            elif self._sequence_last_time + (self._audio_per_packet * 2) <= current_time:
                self._sequence = (current_time - self._sequence_start_time) // SEQUENCE_DURATION
                self._sequence_last_time = self._sequence_start_time + (self._sequence * SEQUENCE_DURATION)
            else:
                self._sequence += self._audio_per_packet // SEQUENCE_DURATION
                self._sequence_last_time = self._sequence_start_time + (self._sequence * SEQUENCE_DURATION)

            payload = bytearray()
            audio_encoded = 0

            while len(self._pcm) > 0 and audio_encoded < self._audio_per_packet:
                self._lock.acquire()
                to_encode = self._pcm.pop(0)
                self._lock.release()

                if len(to_encode) != samples:
                    to_encode += b'\x00' * (samples - len(to_encode))

                try:
                    encoded = self._encoder.encode(to_encode, len(to_encode) // (2 * self._channels))
                except OpusError:
                    encoded = b''

                audio_encoded += encoded

                if self._codec == AudioType.OPUS:
                    frame_header = VarInt(len(encoded)).encode()
                else:
                    frame_header = len(encoded)
                    if audio_encoded < self._audio_per_packet and len(self._pcm) > 0:
                        frame_header += (1 << 7)
                    frame_header = pack('!B', frame_header)
                payload += frame_header + encoded
            header = self._codec_type << 5
            sequence = VarInt(self._sequence).encode()
            udp_packet = pack('!B', header | self._target) + sequence + payload
            if self._mumble.positional:
                udp_packet += pack("fff", self._mumble.positional[0], self._mumble.positional[1],
                                   self._mumble.positional[2])
            tcp_packet = pack('!HL', MessageType.UDPTunnel, len(udp_packet)) + udp_packet

            while len(tcp_packet) > 0:
                sent = self._mumble.control_socket.send(tcp_packet)
                if sent < 0:
                    raise error("Server socket error while sending audio")
                tcp_packet = tcp_packet[sent:]

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
            overhead_per_packet += (3 * (self._audio_per_packet // self._encoder_framesize))
            if self._mumble.udp_active:
                overhead_per_packet += 12
            else:
                overhead_per_packet += 20  # TCP Header
                overhead_per_packet += 6  # TCPTunnel Encapsulation
            overhead_per_second = (overhead_per_packet * 8) // self._audio_per_packet
            self._encoder.bitrate = self._bandwidth - overhead_per_second

    def add_sound(self, pcm: bytes):
        if len(pcm) % 2 != 0:
            raise Exception("pcm data must be 16 bits")

        samples = int(self._encoder_framesize * SAMPLE_RATE * 2 * self._channels)
        self._lock.acquire()
        if len(self._pcm) and len(self._pcm[-1]) < samples:
            initial_offset = samples - len(self._pcm[-1])
        else:
            initial_offset = 0
        for i in range(initial_offset, len(pcm), samples):
            self._pcm.append(pcm[i:i + samples])
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
