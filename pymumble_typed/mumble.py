from __future__ import annotations

from logging import Logger, ERROR, DEBUG
from typing import TYPE_CHECKING

from pymumble_typed import MessageType

if TYPE_CHECKING:
    from ssl import SSLSocket
    from google.protobuf.message import Message

import socket
import ssl
import struct
from struct import pack
from time import sleep

from pymumble_typed.protobuf.Mumble_pb2 import Version, Authenticate, Ping as PingPacket, Reject, ServerSync, \
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
from threading import Thread, Lock, current_thread
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
                self.client._status = Status.NOT_CONNECTED
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


class Settings:
    def __init__(self):
        self.server_allow_html = True
        self.server_max_message_length = 5000
        self.server_max_image_message_length = 131072


class Mumble:
    LOOP_RATE = 0.01
    VERSION = (1, 1, 5)
    PROTOCOL_VERSION = (1, 2, 4)
    VERSION_STRING = f"PyMumble-Typed {VERSION}"
    BANDWIDTH = 50 * 1000
    CONNECTION_RETRY_INTERVAL = 10
    READ_BUFFER_SIZE = 4096
    OS = f"PyMumble {VERSION}"
    OS_VERSION = f"PyMumble"

    def __init__(self, host: str, user: str, port: int = 64738, password: str = '', cert_file: str = None,
                 key_file: str = None, reconnect: bool = False, tokens: list[str] = None, stereo: bool = False,
                 client_type: Type = Type.BOT, debug: bool = False, logger: Logger = None):
        super().__init__()
        self._command_limit = 5
        if tokens is None:
            tokens = []
        self._ready = False
        self._debug = debug
        self._parent_thread = current_thread()
        self._thread = Thread(target=self._run)
        self._logger = logger if logger else Logger("PyMumble-Typed")
        self._logger.setLevel(DEBUG if debug else ERROR)
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._cert_file = cert_file
        self._key_file = key_file
        self.reconnect = reconnect
        self._tokens = tokens
        self._opus_profile = CodecProfile.Audio
        self._stereo = stereo
        self._client_type = client_type

        self.sound_receive = False
        self._loop_rate = Mumble.LOOP_RATE
        self.application = Mumble.VERSION_STRING
        self._callbacks = Callbacks(self)

        self._ready_lock = Lock()
        self._ready_lock.acquire()

        self.positional = None

        self._status: Status = Status.NOT_CONNECTED

        self._control_socket: SSLSocket | None = None

        # self.media_socket: SSLSocket | None = None

        self._bandwidth = Mumble.BANDWIDTH
        self._server_max_bandwidth = 0
        # self.udp_active = False

        self.users: Users = Users(self)
        self.channels: Channels = Channels(self)
        self.settings = Settings()
        self.ping: Ping = Ping(self)
        self.sound_output = SoundOutput(self, AUDIO_PER_PACKET, self._bandwidth, stereo=self._stereo)

        self._command_queue: CommandQueue = CommandQueue()
        self._receive_buffer = bytes()

        self._exit = False
        self._first_connect = True

    @property
    def command_limit(self):
        return self._command_limit

    @command_limit.setter
    def command_limit(self, limit: int):
        if limit <= 0:
            self._logger.error("Command limit cannot be less than 0")
            return
        self._command_limit = limit

    @property
    def logger(self):
        return self._logger

    @property
    def callbacks(self):
        return self._callbacks

    @property
    def ready(self):
        return self._ready

    def _init_connection(self):
        self._ready = False
        self._first_connect = False
        self._ready_lock.acquire(False)
        self.ping = Ping(self)
        self._status = Status.NOT_CONNECTED

        self._control_socket = None
        # self.media_socket = None

        self._bandwidth = Mumble.BANDWIDTH
        self._server_max_bandwidth = 0
        # self.udp_active = False

        self.settings = Settings()
        self.users = Users(self)
        self.channels = Channels(self)
        self.sound_output = SoundOutput(self, AUDIO_PER_PACKET, self._bandwidth, stereo=self._stereo)

        self._command_queue = CommandQueue()

    def start(self):
        if not self._thread.is_alive():
            self._thread = Thread(target=self._run)
            self._thread.start()

    def _run(self):
        while (self.reconnect or self._first_connect) and not self._exit:
            self._init_connection()

            if self._connect() >= Status.FAILED:
                self._ready_lock.release()
                if not self.reconnect:
                    raise ConnectionRejectedError("Connection error with the Mumble (murmur) Server")
            else:
                try:
                    self._logger.debug("Starting loop")
                    self._loop()
                except socket.error:
                    self._logger.error("Error while executing loop", exc_info=True)
                    self._status = Status.NOT_CONNECTED

            self._callbacks.dispatch("on_disconnect")
            self._callbacks.disable()
            sleep(Mumble.CONNECTION_RETRY_INTERVAL)
        try:
            self._control_socket.close()
        except:
            self._logger.debug("Control socket already closed")

    def _connect(self):
        self._first_connect = True
        try:
            server_info = socket.getaddrinfo(self._host, self._port, socket.AF_UNSPEC, socket.SOCK_STREAM)

            sock = socket.socket(server_info[0][0], socket.SOCK_STREAM)
            sock.settimeout(10)
        except socket.error:
            self._status = Status.FAILED
            self._logger.error("Error while connecting", exc_info=True)
            return self._status

        try:
            self._control_socket = ssl.wrap_socket(sock, certfile=self._cert_file, keyfile=self._key_file,
                                                   ssl_version=ssl.PROTOCOL_TLS)
        except AttributeError:
            self._control_socket = ssl.wrap_socket(sock, certfile=self._cert_file, keyfile=self._key_file,
                                                   ssl_version=ssl.PROTOCOL_TLSv1)

        try:
            self._control_socket.connect((self._host, self._port))
            self._control_socket.setblocking(False)

            version = Version()
            if Mumble.PROTOCOL_VERSION[2] > 255:
                version.version_v1 = (Mumble.PROTOCOL_VERSION[0] << 16) + (Mumble.PROTOCOL_VERSION[1] << 8) + \
                                     Mumble.PROTOCOL_VERSION[2] + 255
            else:
                version.version_v1 = (Mumble.PROTOCOL_VERSION[0] << 16) + (Mumble.PROTOCOL_VERSION[1] << 8) + \
                                     Mumble.PROTOCOL_VERSION[2]
            version.version_v2 = (Mumble.PROTOCOL_VERSION[0] << 48) + (Mumble.PROTOCOL_VERSION[1] << 32) + \
                                 (Mumble.PROTOCOL_VERSION[2] << 16)
            version.release = self.application
            version.os = Mumble.OS
            version.os_version = Mumble.OS_VERSION
            self.send_message(MessageType.Version, version)

            authenticate = Authenticate()
            authenticate.username = self._user
            authenticate.password = self._password
            authenticate.tokens.extend(self._tokens)
            authenticate.opus = True
            authenticate.client_type = self._client_type

            self.send_message(MessageType.Authenticate, authenticate)
        except socket.error:
            self._logger.error("Error while authenticating", exc_info=True)
            self._status = Status.FAILED
            return self._status
        self._status = Status.AUTHENTICATING
        return self._status

    def _loop(self):
        self._exit = False
        while self._status not in (Status.NOT_CONNECTED, Status.FAILED) and not self._exit:
            self.ping.send()
            if self._status == Status.CONNECTED:
                if self._command_queue.has_next():
                    # FIXME: experimental, limit number of command per cycle to avoid too long processing
                    #   this may be useful on busy server or if the client is sending a lot of command
                    for _ in range(0, min(len(self._command_queue), self._command_limit)):
                        self._treat_command(self._command_queue.pop())
                self.sound_output.send_audio()

            (rlist, wlist, xlist) = select([self._control_socket], [], [self._control_socket], self._loop_rate)
            if self._control_socket in rlist:
                self._read_control_messages()
            elif self._control_socket in xlist:
                self._control_socket.close()
                self._status = Status.NOT_CONNECTED
            self._exit = not self._parent_thread.is_alive()

    def send_message(self, _type: MessageType, message: Message):
        if self._debug:
            self._logger.debug(str(message))
        packet = pack("!HL", _type.value, message.ByteSize()) + message.SerializeToString()

        while len(packet) > 0:
            sent = self._control_socket.send(packet)
            if sent < 0:
                raise socket.error("Server socket error")
            packet = packet[sent:]

    def _read_control_messages(self):
        try:
            buffer: bytes = self._control_socket.recv(Mumble.READ_BUFFER_SIZE)
            self._receive_buffer += buffer
        except socket.error:
            self._logger.error("Error while reading control messages", exc_info=True)
            return

        while len(self._receive_buffer) >= 6:
            header = self._receive_buffer[0:6]
            if len(header) < 6:
                break

            (_type, size) = struct.unpack("!HL", header)

            if len(self._receive_buffer) < size + 6:
                break

            message: bytes = self._receive_buffer[6:size + 6]
            self._receive_buffer = self._receive_buffer[size + 6:]

            self._dispatch_control_message(_type, message)

    def _dispatch_control_message(self, _type: int, message: bytes):
        if _type == MessageType.UDPTunnel:
            if self.sound_receive:
                self._sound_received(message)
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
            self._status = Status.FAILED
            self._ready_lock.release()
            raise ConnectionRejectedError(packet.reason)
        elif _type == MessageType.ServerSync:
            packet = ServerSync()
            packet.ParseFromString(message)
            self.users.set_myself(packet.session)
            self._server_max_bandwidth = packet.max_bandwidth
            self.set_bandwidth(packet.max_bandwidth)

            if self._status is Status.AUTHENTICATING:
                self._status = Status.CONNECTED
                self._ready = True

                # FIXME: experimental, using number of users as command limit per loop cycle
                #  since this is set on client startup minimum is 5 to avoid excessively low limit
                if len(self.users) > self._command_limit:
                    self._command_limit = len(self.users)
                self._ready_lock.release()
                self._callbacks.ready()
                self._callbacks.dispatch("on_connect")
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
            self._callbacks.dispatch("on_message", MessageContainer(self, packet))
        elif _type == MessageType.PermissionDenied:
            packet = PermissionDenied()
            packet.ParseFromString(message)
            # FIXME: CALLBACK Permission Denied
            self._callbacks.dispatch("on_permission_denied", packet.session, packet.channel_id, packet.name,
                                     packet.type, packet.reason)
        elif _type == MessageType.ACL:
            packet = ACL()
            packet.ParseFromString(message)
            self.channels[packet.channel_id].update_acl(packet)
            # FIXME: CALLBACK ACL
            self._callbacks.dispatch("on_acl_received")
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
            self._callbacks.dispatch("on_context_action")
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
                        self.settings.server_allow_html = items[1].strip() == 'true'
                    elif items[0] == 'message_length':
                        self.settings.server_max_message_length = int(items[1].strip())
                    elif items[0] == 'image_message_length':
                        self.settings.server_max_image_message_length = int(items[1].strip())
                except:
                    self._logger.error(f"Error while parsing server arguments: {str(packet)}", exc_info=True)

    def set_bandwidth(self, bandwidth: int):
        if self._server_max_bandwidth is not None:
            self._bandwidth = min(bandwidth, self._server_max_bandwidth)

        self.sound_output.set_bandwidth(self._bandwidth)

    def _sound_received(self, packet: bytes):
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
                    self._callbacks.dispatch("on_sound_received", user, sound)
                    sequence.value += int(round(sound.duration / 100))
                except CodecNotSupportedError:
                    self._logger.error("Codec not supported", exc_info=True)
                except KeyError:
                    pass
            pos += size

    def set_application_string(self, string: str):
        self.application = string

    def set_loop_rate(self, rate: float):
        self._loop_rate = rate

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
        lock = self._command_queue.push(cmd)
        if blocking and self._thread is not current_thread():
            lock.acquire()
            lock.release()
        return lock

    def _treat_command(self, cmd: Command):
        if cmd.packet:
            self.send_message(cmd.type, cmd.packet)
            cmd.response = True
            self._command_queue.answer(cmd)

    def get_max_message_length(self) -> int:
        return self.settings.server_max_message_length

    def get_max_image_length(self) -> int:
        return self.settings.server_max_message_length

    def denial_type(self, name: str):
        return PermissionDenied.DenyType.Name(name)

    def stop(self):
        self.reconnect = False
        self._exit = True
        self._control_socket.close()

    def request_blob(self, packet):
        self.send_message(MessageType.RequestBlob, packet)

    def reauthenticate(self, token):
        packet = Authenticate()
        packet.username = self._user
        packet.password = self._password
        packet.tokens.extend(self._tokens)
        packet.tokens.append(token)
        packet.opus = True
        packet.client_type = self._client_type
        self.send_message(MessageType.Authenticate, packet)

    def send_audio(self, udp_packet):
        tcp_packet = pack('!HL', MessageType.UDPTunnel.value, len(udp_packet)) + udp_packet
        while len(tcp_packet) > 0:
            sent = self._control_socket.send(tcp_packet)
            if sent < 0:
                raise socket.error("Server socket error while sending audio")
            tcp_packet = tcp_packet[sent:]
