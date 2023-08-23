from struct import pack
from time import time_ns

from pymumble_typed import UdpMessageType, MessageType
from pymumble_typed.protobuf.MumbleUDP_pb2 import Audio, Ping
from pymumble_typed.protobuf.Mumble_pb2 import UDPTunnel
from pymumble_typed.sound import AudioType
from pymumble_typed.tools import VarInt


class UDPData:
    def __init__(self, is_ping: bool = True):
        self.is_ping = is_ping
        self.time = time_ns()
        self.request_extended_information = False

    @property
    def udp_packet(self):
        packet = Ping()
        packet.timestamp = self.time
        packet.request_extended_information = self.request_extended_information
        return packet

    @property
    def serialized_udp_packet(self):
        return bytes((self.type.value,)) + self.udp_packet.SerializeToString()

    @property
    def legacy_udp_packet(self):
        data = VarInt(self.time).encode()
        if self.request_extended_information:
            return bytes((0, 0, 0, 0)) + data
        else:
            return pack("!B", 1 << 5) + data

    @property
    def type(self):
        return UdpMessageType.Ping

    @property
    def legacy_tcp_packet(self):
        return b""

    @property
    def tcp_packet(self):
        packet = UDPTunnel()
        packet.packet = self.serialized_udp_packet
        return packet


class PingData(UDPData):
    def __init__(self):
        super().__init__()


class AudioData(UDPData):
    def __init__(self):
        super().__init__(is_ping=False)
        self._chunks: bytes = b""
        self.codec: AudioType = AudioType.OPUS
        self.sequence: int = 0
        self.target: int = 0
        self.positional: [int, int, int] = [0, 0, 0]
        self._payload = bytearray()

    def add_chunk(self, chunk: bytes):
        self._payload += VarInt(len(chunk)).encode() + chunk
        self._chunks += chunk

    @property
    def header(self):
        return self.codec << 5

    @property
    def payload(self):
        return self._payload

    @property
    def legacy_udp_packet(self):
        packet = pack('!B', self.header | self.target) + VarInt(self.sequence).encode() + self.payload
        if self.positional:
            packet += pack("fff", self.positional[0], self.positional[1],
                           self.positional[2])
        return packet

    @property
    def udp_packet(self):
        packet = Audio()
        packet.opus_data = self._chunks
        packet.target = self.target
        packet.frame_number = self.sequence
        if self.positional:
            packet.positional_data.extend(self.positional)
        return packet

    @property
    def type(self):
        return UdpMessageType.Audio

    @property
    def legacy_tcp_packet(self):
        data = self.legacy_udp_packet
        return pack("!HL", MessageType.UDPTunnel.value, len(data)) + data
