from __future__ import annotations

import platform
import socket
import ssl
import struct
import sys
from struct import pack
from time import sleep
from typing import TYPE_CHECKING

from pymumble_typed.Mumble_pb2 import Version, Authenticate, Ping as PingPacket, UDPTunnel, Reject, ServerSync, \
    ChannelRemove, ChannelState, UserRemove, UserState, BanList, TextMessage, PermissionDenied, ACL, QueryUsers, \
    CryptSetup, ContextActionModify, ContextAction, UserList, VoiceTarget, PermissionQuery, CodecVersion, UserStats, \
    RequestBlob, ServerConfig
from pymumble_typed.commands import Command, Move, TextMessage as TextMessageCommand, TextPrivateMessage, CreateChannel, \
    RemoveChannel, UpdateChannel, LinkChannel, UnlinkChannel, VoiceTarget as VoiceTargetCommand, ModUserState, \
    RemoveUser, QueryACL, UpdateACL, CommandQueue
from pymumble_typed.tools import VarInt

if TYPE_CHECKING:
    from ssl import SSLSocket
    from google.protobuf.message import Message

from enum import IntEnum
from threading import Thread, current_thread, Lock
from pymumble_typed.soundqueue import AudioType, CodecProfile
from time import time
from select import select


class MessageType(IntEnum):
    Version = 0
    UDPTunnel = 1
    Authenticate = 2
    PingPacket = 3
    Reject = 4
    ServerSync = 5
    ChannelRemove = 6
    ChannelState = 7
    UserRemove = 8
    UserState = 9
    BanList = 10
    TextMessage = 11
    PermissionDenied = 12
    ACL = 13
    QueryUsers = 14
    CryptSetup = 15
    ContextActionModify = 16
    ContextAction = 17
    UserList = 18
    VoiceTarget = 19
    PermissionQuery = 20
    CodecVersion = 21
    UserStats = 22
    RequestBlob = 23
    ServerConfig = 24
    SuggestConfig = 25


class Status(IntEnum):
    NOT_CONNECTED = 0
    AUTHENTICATING = 1
    CONNECTED = 2
    FAILED = 3


class Type(IntEnum):
    USER = 0
    BOT = 1


class Ping:
    DELAY = 10

    def __init__(self, client: Mumble):
        self.last_receive = 0.
        self.time_send = 0.
        self.number = 0.
        self.average = 0.
        self.variance = 0.
        self.last = time()
        self.client = client

    def send(self):
        if self.last + Ping.DELAY < time():
            ping = PingPacket()
            ping.timestamp = int(time())
            ping.tcp_ping_avg = self.average
            ping.tcp_ping_var = self.variance
            ping.tcp_packets = self.number

            self.client.send_message(ping)
            self.time_send = int(time() * 1000)
            if self.last_receive != 0 and int(time() * 1000) > self.last_receive + 60000:
                self.client.connected = Status.NOT_CONNECTED
            self.last = time()

    def receive(self, packet: PingPacket):
        pass


class Mumble(Thread):
    LOOP_RATE = 0.01
    VERSION = (1, 6, 0)
    PROTOCOL_VERSION = (1, 6, 0)
    VERSION_STRING = f"PyMumble-Typed {VERSION}"
    BANDWIDTH = 50 * 1000
    CONNECTION_RETRY_INTERVAL = 10
    READ_BUFFER_SIZE = 4096
    OS = f"PyMumble {VERSION}"
    OS_VERSION = f"Python {sys.version} - {platform.system()} {platform.release()}"

    def __init__(self, host: str, user: str, port: int = 64738, password: str = '', cert_file: str = None,
                 key_file: str = None, reconnect: bool = False, tokens: list[str] = None, stereo: bool = False,
                 client_type: Type = Type.BOT, debug: bool = False):
        super().__init__()
        if tokens is None:
            tokens = []

        self._parent_thread = current_thread()
        self._mumble_thread: Thread | None = None

        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.cert_file = cert_file
        self.key_file = key_file
        self.reconnect = reconnect
        self.tokens = tokens
        self._opus_profile = CodecProfile.Audio
        self.stereo = stereo
        self.client_type = client_type

        self.sound_receive = False
        self.loop_rate = Mumble.LOOP_RATE
        self.application = Mumble.VERSION_STRING

        self.callbacks = None

        self._ready_lock = Lock()
        self._ready_lock.acquire()

        self.positional = None

        self.connected: Status = Status.NOT_CONNECTED

        self.control_socket: SSLSocket | None = None
        self.media_socket: SSLSocket | None = None

        self.bandwidth = Mumble.BANDWIDTH
        self.server_max_bandwidth = 0
        self.udp_active = False

        self.server_allow_html = True
        self.server_max_message_length = 5000
        self.server_max_image_message_length = 131072

        self.users: Users = Users()
        self.channels: Channels = Channels()

        self.sound_output: SoundOutput | None = None
        self.command_queue: CommandQueue = CommandQueue()

        self.receive_buffer = bytes()
        self.ping: Ping = Ping(self)
        self.exit = False

    def init_connection(self):
        self._ready_lock.acquire(False)
        self.connected = Status.NOT_CONNECTED

        self.control_socket = None
        self.media_socket = None

        self.bandwidth = Mumble.BANDWIDTH
        self.server_max_bandwidth = 0
        self.udp_active = False

        self.server_allow_html = True
        self.server_max_message_length = 5000
        self.server_max_image_message_length = 131072

        self.users = Users()
        self.channels = Channels()
        if self.sound_receive:
            self.sound_output = SoundOutput()
        else:
            self.sound_output = None

        self.command_queue = CommandQueue()
        self.ping = Ping(self)

    def run(self):
        self._mumble_thread = current_thread()
        while self.reconnect:
            self.init_connection()

            if self.connect() >= Status.FAILED:
                self._ready_lock.release()
                if not self.reconnect or not self._parent_thread.is_alive():
                    raise ConnectionRejectedError("Connection error with the Mumble (murmur) Server")
                else:
                    sleep(Mumble.CONNECTION_RETRY_INTERVAL)
            try:
                self.loop()
            except socket.error:
                self.connected = Status.NOT_CONNECTED

            # FIXME: Disconnected Callback
            sleep(Mumble.CONNECTION_RETRY_INTERVAL)

    def connect(self):
        try:
            server_info = socket.getaddrinfo(self.host, self.port, socket.AF_UNSPEC, socket.SOCK_STREAM)

            sock = socket.socket(server_info[0][0], socket.SOCK_STREAM)
            sock.settimeout(10)
        except socket.error:
            self.connected = Status.FAILED
            return self.connected

        try:
            self.control_socket = ssl.wrap_socket(sock, certfile=self.cert_file, keyfile=self.key_file,
                                                  ssl_version=ssl.PROTOCOL_TLS)
        except AttributeError:
            self.control_socket = ssl.wrap_socket(sock, certfile=self.cert_file, keyfile=self.key_file,
                                                  ssl_version=ssl.PROTOCOL_TLSv1)

        try:
            self.control_socket.connect((self.host, self.port))
            self.control_socket.setblocking(False)

            version = Version()
            version.version_v1 = (Mumble.PROTOCOL_VERSION[0] << 16) + (Mumble.PROTOCOL_VERSION[1] << 8) + \
                                 Mumble.PROTOCOL_VERSION[2]
            version.release = self.application
            version.os = Mumble.OS
            version.os_version = Mumble.OS_VERSION
            self.send_message(MessageType.Version, version)

            authenticate = Authenticate()
            authenticate.username = self.user
            authenticate.password = self.password
            authenticate.tokens.extend(self.tokens)
            authenticate.opus = True
            authenticate.client_type = self.client_type

            self.send_message(MessageType.Authenticate, authenticate)
        except socket.error:
            self.connected = Status.FAILED
            return self.connected
        self.connected = Status.AUTHENTICATING
        return self.connected

    def loop(self):
        self.exit = False

        # last_ping = time.time()

        while self.connected not in (
                Status.NOT_CONNECTED, Status.FAILED) and self._parent_thread.is_alive() and not self.exit:
            self.ping.send()
            if self.connected == Status.CONNECTED:
                while self.command_queue.has_cmd():
                    self.command_queue.treat_next()
                if self.sound_output:  # FIXME: move to another loop
                    self.sound_output.send_audio()
                (rlist, wlist, xlist) = select([self.control_socket], [], [self.control_socket], self.loop_rate)
                if self.control_socket in rlist:
                    self.read_control_messages()
                elif self.control_socket in xlist:
                    self.control_socket.close()
                    self.connected = Status.NOT_CONNECTED

    def send_message(self, _type: MessageType, message: Message):
        packet = pack("!HL", _type.value, message.ByteSize()) + message.SerializeToString()

        while len(packet) > 0:
            sent = self.control_socket.send(packet)
            if sent < 0:
                raise socket.error("Server socket error")
            packet = packet[sent:]

    def read_control_messages(self):
        try:
            buffer: bytes = self.control_socket.recv(Mumble.READ_BUFFER_SIZE)
            self.receive_buffer += buffer
        except socket.error:
            pass

        while len(self.receive_buffer) >= 6:
            header = self.receive_buffer[0:6]
            if len(header) < 6:
                break

            (_type, size) = struct.unpack("!HL", header)

            if len(self.receive_buffer) < size + 6:
                break

            message: bytes = self.receive_buffer[6:size + 6]
            self.receive_buffer = self.receive_buffer[size + 6:]

            self.dispatch_control_message(_type, message)

    def dispatch_control_message(self, _type: int, message: bytes):
        if _type == MessageType.UDPTunnel:
            if self.sound_output:
                self.sound_received(message)
        elif _type == MessageType.Version:
            packet = Version()
            packet.ParseFromString(message)
        elif _type == MessageType.Authenticate:
            packet = Authenticate()
            packet.ParseFromString(message)
        elif _type == MessageType.PingPacket:
            packet = PingPacket()
            packet.ParseFromString(message)
            self.ping.receive(packet)
        elif _type == MessageType.Reject:
            packet = Reject()
            packet.ParseFromString(message)
            self.connected = Status.FAILED
            self._ready_lock.release()
            raise ConnectionRejectedError(packet.reason)
        elif _type == MessageType.ServerSync:
            packet = ServerSync()
            packet.ParseFromString(message)
            # FIXME: packet.session = myself
            self.server_max_bandwidth = packet.max_bandwidth
            self.set_bandwidth(packet.max_bandwidth)

            if self.connected is Status.AUTHENTICATING:
                self.connected = Status.CONNECTED
                self._ready_lock.release()
                # FIXME: Connected Callback
        elif _type == MessageType.ChannelRemove:
            packet = ChannelRemove()
            packet.ParseFromString(packet)
            self.channels.remove(packet.channel_id)
        elif _type == MessageType.ChannelState:
            packet = ChannelState()
            packet.ParseFromString(packet)
            self.channels.update(packet)
        elif _type == MessageType.UserRemove:
            packet = UserRemove()
            packet.ParseFromString(message)
            self.users.remove(packet)
        elif _type == MessageType.UserState:
            packet = UserState()
            packet.ParseFromString(message)
            self.users.update(packet)
        elif _type == MessageType.BanList:
            packet = BanList()
            packet.ParseFromString(message)
        elif _type == MessageType.TextMessage:
            packet = TextMessage()
            packet.ParseFromString(message)
            # FIXME: CALLBACK MESSAGE
        elif _type == MessageType.PermissionDenied:
            packet = PermissionDenied()
            packet.ParseFromString(message)
            # FIXME: CALLBACK Permission Denied
        elif _type == MessageType.ACL:
            packet = ACL()
            packet.ParseFromString(message)
            self.channels[packet.channel_id].update_acl(packet)
            # FIXME: CALLBACK ACL
        elif _type == MessageType.QueryUsers:
            packet = QueryUsers()
            packet.ParseFromString(message)
        elif _type == MessageType.CryptSetup:
            packet = CryptSetup()
            packet.ParseFromString()
            self.ping.send()
        elif _type == MessageType.ContextActionModify:
            packet = ContextActionModify()
            packet.ParseFromString(message)
            # FIXME: CALLBACK ContextActionModify
        elif _type == MessageType.ContextAction:
            packet = ContextAction()
            packet.ParseFromString(message)
        elif _type == MessageType.UserList:
            packet = UserList()
            packet.ParseFromString(message)
        elif _type == MessageType.VoiceTarget:
            packet = VoiceTarget()
            packet.ParseFromString(message)
        elif _type == MessageType.PermissionQuery:
            packet = PermissionQuery()
            packet.ParseFromString(message)
        elif _type == MessageType.CodecVersion:
            packet = CodecVersion()
            packet.ParseFromString(message)
            if self.sound_output:
                self.sound_output.set_codec(packet)
        elif _type == MessageType.UserStats:
            packet = UserStats()
            packet.ParseFromString(message)
        elif _type == MessageType.RequestBlob:
            packet = RequestBlob()
            packet.ParseFromString(message)
        elif _type == MessageType.ServerConfig:
            packet = ServerConfig()
            packet.ParseFromString(message)
            for line in str(packet).split("\n"):
                try:
                    items = line.split(":")
                    if items[0] == 'allow_html':
                        self.server_allow_html = items[1].strip() == 'true'
                    elif items[0] == 'message_length':
                        self.server_max_message_length = int(items[1].strip())
                    elif items[0] == 'image_message_length':
                        self.server_max_image_message_length = int(items[1].strip())
                except:
                    pass  # FIXME: log error

    def set_bandwidth(self, bandwidth: int):
        if self.server_max_bandwidth is not None:
            self.bandwidth = min(bandwidth, self.server_max_bandwidth)

        if self.sound_output:
            self.sound_output.set_bandwidth(self.bandwidth)

    def sound_received(self, packet: bytes):
        pos = 0

        (header,) = struct.unpack("!B", bytes([packet[pos]]))
        _type = (header & 0b11100000) >> 5
        target = header & 0b00011111
        pos += 1

        if _type == AudioType.PING:
            return

        session = VarInt()
        pos += session.decode(packet[pos: pos + 10])

        sequence = VarInt()
        pos += sequence.decode(packet[pos:pos + 10])

        terminator = False

        while (pos < len(packet)) and not terminator:
            if _type == AudioType.OPUS:
                size = VarInt()
                pos += size.decode(packet[pos:pos + 10])
                size = size.value

                if not (size & 0x2000):
                    terminator = True
                size &= 0x1fff
            else:
                (header,) = struct.unpack("!B", packet[pos:pos + 1])
                if not (header & 0b10000000):
                    terminator = True
                size = header & 0b01111111
                pos += 1

            if size > 0:
                try:
                    sound = self.users[session.value].sound.add(packet[pos:pos + size], sequence.value, _type, target)
                    if sound is None:
                        return

                    # self.callbacks ON_SOUND_RECV

                    sequence.value += int(round(sound.duration / 100))
                except CodecNotSupportedError:
                    pass  # FIXME: log it
                except KeyError:
                    pass
            pos += size

    def set_application_string(self, string: str):
        self.application = string

    def set_loop_rate(self, rate: float):
        self.loop_rate = rate

    def set_codec_profile(self, profile: CodecProfile):
        self._opus_profile = profile

    def get_codec_profile(self) -> CodecProfile:
        return self._opus_profile

    def set_receive_sound(self, value: bool):
        self.sound_receive = value

    def is_ready(self):
        self._ready_lock.acquire()
        self._ready_lock.release()

    def execute_command(self, cmd: Command, blocking: bool = True):
        self.is_ready()

        lock = self.command_queue.push(cmd)
        if blocking and self._mumble_thread is not current_thread():
            lock.acquire()
            lock.release()
        return lock

    def treat_command(self, cmd: Command):
        if cmd.packet:
            self.send_message(MessageType.UserState, cmd.packet)
            cmd.response = True
            self.command_queue.answer(cmd)

    def get_max_message_length(self) -> int:
        return self.server_max_message_length

    def get_max_image_length(self) -> int:
        return self.server_max_message_length

    def denial_type(self, name: str):
        return PermissionDenied.DenyType.Name(name)

    def stop(self):
        self.reconnect = None
        self.exit = True
        self.control_socket.close()

