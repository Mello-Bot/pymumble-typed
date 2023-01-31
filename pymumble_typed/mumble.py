from __future__ import annotations

from logging import Logger, ERROR, DEBUG
from typing import TYPE_CHECKING

from pymumble_typed import MessageType

if TYPE_CHECKING:
    from ssl import SSLSocket
    from google.protobuf.message import Message

import platform
import socket
import ssl
import struct
import sys
from struct import pack
from time import sleep

from pymumble_typed.Mumble_pb2 import Version, Authenticate, Ping as PingPacket, Reject, ServerSync, \
    ChannelRemove, ChannelState, UserRemove, UserState, BanList, TextMessage, PermissionDenied, ACL, QueryUsers, \
    CryptSetup, ContextActionModify, ContextAction, UserList, VoiceTarget, PermissionQuery, CodecVersion, UserStats, \
    RequestBlob, ServerConfig

from pymumble_typed.callbacks import Callbacks
from pymumble_typed.channels import Channels
from pymumble_typed.commands import Command, CommandQueue
from pymumble_typed.messages import Message as MessageContainer
from pymumble_typed.sound.soundoutput import SoundOutput
from pymumble_typed.tools import VarInt
from pymumble_typed.users import Users

from enum import IntEnum
from threading import Thread, Lock
from pymumble_typed.sound import AudioType, CodecProfile, CodecNotSupportedError, AUDIO_PER_PACKET
from time import time
from select import select


class ConnectionRejectedError(Exception):
    """Thrown when server reject the connection"""

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)

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
        self.number = 1
        self.average = 0.
        self.variance = 0.
        self.last = 0
        self.client = client

    def send(self):
        if self.last + Ping.DELAY < time():
            ping = PingPacket()
            ping.timestamp = int(time())
            ping.tcp_ping_avg = self.average
            ping.tcp_ping_var = self.variance
            ping.tcp_packets = self.number

            self.client.send_message(MessageType.PingPacket, ping)
            self.time_send = int(time() * 1000)
            if self.last_receive != 0 and int(time() * 1000) > self.last_receive + 60000:
                self.client.connected = Status.NOT_CONNECTED
            self.last = time()

    def receive(self, _: PingPacket):
        self.last_receive = int(time() * 1000)
        ping = self.last_receive - self.time_send
        old_average = self.average
        number = self.number
        new_average = ((self.average * number) + ping) / (self.number + 1)
        self.variance = self.variance + pow(old_average - new_average, 2) + (1 / self.number) * pow(ping - new_average,
                                                                                                    2)
        self.average = new_average
        self.number += 1


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
                 client_type: Type = Type.BOT, callbacks: Callbacks = Callbacks(), debug: bool = False,
                 logger: Logger = None):
        super().__init__()
        if tokens is None:
            tokens = []
        self._debug = debug
        self._parent_thread = self
        self._loop_thread = Thread(target=self.loop)
        self._logger = logger if logger else Logger("PyMumble-Typed")
        self._logger.setLevel(DEBUG if debug else ERROR)
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

        self._callbacks = callbacks

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

        self.users: Users = Users(self, self._callbacks)
        self.channels: Channels = Channels(self, self._callbacks)

        self.sound_output: SoundOutput | None = None
        self.command_queue: CommandQueue = CommandQueue()

        self.receive_buffer = bytes()
        self.ping: Ping = Ping(self)
        self.exit = False
        self._first_connect = True

    def init_connection(self):
        self._first_connect = False
        self._ready_lock.acquire(False)
        self.ping = Ping(self)
        self.connected = Status.NOT_CONNECTED

        self.control_socket = None
        self.media_socket = None

        self.bandwidth = Mumble.BANDWIDTH
        self.server_max_bandwidth = 0
        self.udp_active = False

        self.server_allow_html = True
        self.server_max_message_length = 5000
        self.server_max_image_message_length = 131072

        self.users = Users(self, self._callbacks)
        self.channels = Channels(self, self._callbacks)
        if self.sound_receive:
            self.sound_output = SoundOutput(self, AUDIO_PER_PACKET, self.bandwidth, stereo=self.stereo)
        else:
            self.sound_output = None

        self.command_queue = CommandQueue()

    def run(self):
        while self.reconnect or self._first_connect:
            self.init_connection()

            if self.connect() >= Status.FAILED:
                self._ready_lock.release()
                if not self.reconnect or not self._parent_thread.is_alive():
                    raise ConnectionRejectedError("Connection error with the Mumble (murmur) Server")
                else:
                    sleep(Mumble.CONNECTION_RETRY_INTERVAL)
            try:
                self._logger.debug("Starting loop")
                if self._loop_thread:
                    if self._loop_thread.is_alive():
                        self._loop_thread.join()
                    self._loop_thread = Thread(target=self.loop)
                self._loop_thread.start()
                self._loop_thread.join()
            except socket.error:
                self._logger.error("Error while executing loop", exc_info=True)
                self.connected = Status.NOT_CONNECTED

            self._callbacks.on_disconnect()
            sleep(Mumble.CONNECTION_RETRY_INTERVAL)

    def connect(self):
        self._first_connect = True
        try:
            server_info = socket.getaddrinfo(self.host, self.port, socket.AF_UNSPEC, socket.SOCK_STREAM)

            sock = socket.socket(server_info[0][0], socket.SOCK_STREAM)
            sock.settimeout(10)
        except socket.error:
            self.connected = Status.FAILED
            self._logger.error("Error while connecting", exc_info=True)
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
            self._logger.error("Error while authenticating", exc_info=True)
            self.connected = Status.FAILED
            return self.connected
        self.connected = Status.AUTHENTICATING
        return self.connected

    def loop(self):
        self.exit = False
        while self.connected not in (Status.NOT_CONNECTED, Status.FAILED) and self._loop_thread.is_alive() and not self.exit:
            self.ping.send()
            if self.connected == Status.CONNECTED:
                while self.command_queue.has_next():
                    self.treat_command(self.command_queue.pop())
                if self.sound_output:  # FIXME: move to another loop
                    self.sound_output.send_audio()

            (rlist, wlist, xlist) = select([self.control_socket], [], [self.control_socket], self.loop_rate)
            if self.control_socket in rlist:
                self.read_control_messages()
            elif self.control_socket in xlist:
                self.control_socket.close()
                self.connected = Status.NOT_CONNECTED

    def send_message(self, _type: MessageType, message: Message):
        if self._debug:
            self._logger.debug(str(message))
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
            self._logger.error("Error while reading control messages", exc_info=True)
            return

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
            if self.sound_receive:
                self.sound_received(message)
        elif _type == MessageType.Version:
            packet = Version()
            packet.ParseFromString(message)
            self._logger.debug(f"Received version: {packet.version_v1}")
        elif _type == MessageType.Authenticate:
            packet = Authenticate()
            packet.ParseFromString(message)
            self._logger.debug(f"Received authenticate. Session: {packet.session}")
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
            self.users.set_myself(packet.session)
            self.server_max_bandwidth = packet.max_bandwidth
            self.set_bandwidth(packet.max_bandwidth)

            if self.connected is Status.AUTHENTICATING:
                self.connected = Status.CONNECTED
                self._ready_lock.release()
                self._callbacks.on_connect()
        elif _type == MessageType.ChannelRemove:
            packet = ChannelRemove()
            packet.ParseFromString(message)
            self.channels.remove(packet.channel_id)
        elif _type == MessageType.ChannelState:
            packet = ChannelState()
            packet.ParseFromString(message)
            self.channels.handle_update(packet)
        elif _type == MessageType.UserRemove:
            packet = UserRemove()
            packet.ParseFromString(message)
            self.users.remove(packet)
        elif _type == MessageType.UserState:
            packet = UserState()
            packet.ParseFromString(message)
            self.users.handle_update(packet)
        elif _type == MessageType.BanList:
            packet = BanList()
            packet.ParseFromString(message)
        elif _type == MessageType.TextMessage:
            packet = TextMessage()
            packet.ParseFromString(message)
            self._callbacks.on_message(MessageContainer(self, packet))
        elif _type == MessageType.PermissionDenied:
            packet = PermissionDenied()
            packet.ParseFromString(message)
            # FIXME: CALLBACK Permission Denied
            self._callbacks.on_permission_denied(packet.session, packet.channel_id, packet.name, packet.type,
                                                 packet.reason)
        elif _type == MessageType.ACL:
            packet = ACL()
            packet.ParseFromString(message)
            self.channels[packet.channel_id].update_acl(packet)
            # FIXME: CALLBACK ACL
            self._callbacks.on_acl_received()
        elif _type == MessageType.QueryUsers:
            packet = QueryUsers()
            packet.ParseFromString(message)
        elif _type == MessageType.CryptSetup:
            packet = CryptSetup()
            packet.ParseFromString(message)
            self.ping.send()
        elif _type == MessageType.ContextActionModify:
            packet = ContextActionModify()
            packet.ParseFromString(message)
            # FIXME: CALLBACK ContextActionModify
            self._callbacks.on_context_action()
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
                self.sound_output.set_default_codec(packet)
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
                    self._logger.error(f"Error while parsing server arguments: {str(packet)}", exc_info=True)

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
                    user = self.users[session.value]
                    sound = user.sound.add(packet[pos:pos + size], sequence.value, _type, target)
                    if sound is None:
                        return

                    self._callbacks.on_sound_received(user, sound)

                    sequence.value += int(round(sound.duration / 100))
                except CodecNotSupportedError:
                    self._logger.error("Codec not supported", exc_info=True)
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

    def execute_command(self, cmd: Command, blocking: bool = False):
        self.is_ready()
        lock = self.command_queue.push(cmd)
        if blocking:
            lock.acquire()
            lock.release()
        return lock

    def treat_command(self, cmd: Command):
        if cmd.packet:
            self.send_message(cmd.type, cmd.packet)
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

    def request_blob(self, packet):
        self.send_message(MessageType.RequestBlob, packet)

    def reauthenticate(self, token):
        packet = Authenticate()
        packet.username = self.user
        packet.password = self.password
        packet.tokens.extend(self.tokens)
        packet.tokens.append(token)
        packet.opus = True
        packet.client_type = self.client_type
        self.send_message(MessageType.Authenticate, packet)
