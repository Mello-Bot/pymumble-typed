from __future__ import annotations

from enum import IntEnum
from socket import getaddrinfo, AF_UNSPEC, SOCK_STREAM, socket, error as socket_error
from ssl import SSLContext, PROTOCOL_TLSv1, PROTOCOL_TLSv1_2, SSLZeroReturnError
from struct import pack, unpack
from threading import Thread, current_thread, Lock
from time import sleep
from typing import TYPE_CHECKING

from pymumble_typed import MessageType
from pymumble_typed.commands import Command
from pymumble_typed.constants import PROTOCOL_VERSION, OS, OS_VERSION, VERSION
from pymumble_typed.network import ConnectionRejectedError, CONNECTION_RETRY_INTERVAL, READ_BUFFER_SIZE
from pymumble_typed.network.ping import Ping
from pymumble_typed.network.udp_data import AudioData
from pymumble_typed.protobuf.Mumble_pb2 import Version, Authenticate

if TYPE_CHECKING:
    from pymumble_typed.mumble import ClientType
    from google.protobuf.message import Message
    from logging import Logger
    from ssl import SSLSocket
    from typing import Callable


class Status(IntEnum):
    NOT_CONNECTED = 0
    AUTHENTICATING = 1
    CONNECTED = 2
    FAILED = 3


class ControlStack:
    def __init__(self, host: str, port: int, user: str, password: str | None, tokens: list[str], cert_file: str,
                 key_file: str, client_type: ClientType, logger: Logger):
        self.socket: SSLSocket | None = None
        self.user = user
        self.password = password
        self.tokens = tokens
        self.host = host
        self.port = port
        self.client_type = client_type
        self.cert_file = cert_file
        self.key_file = key_file
        self.logger = logger
        self.version_string: str = f"PyMumble-Typed {VERSION}"
        self.status = Status.NOT_CONNECTED
        self._disconnect = False
        self.reconnect = False
        self._on_disconnect: Callable[[], None] = lambda: None

        self.receive_buffer: bytes = bytes()
        self._dispatch_control_message = lambda _, __: None
        self.thread = Thread(target=self.loop, name="ControlStack:Loop")

        self._ready = Lock()
        self._ready.acquire(True)
        self._server_version = (0, 0, 0)
        self._voice_dispatcher: Callable[[AudioData], None] = self.send_audio_legacy
        self.ping: Ping = Ping(self)

    def reinit(self) -> ControlStack:
        self.disconnect()
        return ControlStack(self.host, self.port, self.user, self.password, self.tokens, self.cert_file, self.key_file,
                            self.client_type, self.logger)

    def set_version_string(self, version_string: str):
        self.version_string = version_string

    def set_control_message_dispatcher(self, dispatcher: Callable[[int, bytes], None]):
        self._dispatch_control_message = dispatcher

    def _craft_version_packet(self) -> Version:
        version = Version()
        if PROTOCOL_VERSION[2] > 255:
            version.version_v1 = (PROTOCOL_VERSION[0] << 16) + (PROTOCOL_VERSION[1] << 8) + \
                                 PROTOCOL_VERSION[2] + 255
        else:
            version.version_v1 = (PROTOCOL_VERSION[0] << 16) + (PROTOCOL_VERSION[1] << 8) + \
                                 PROTOCOL_VERSION[2]
        version.version_v2 = (PROTOCOL_VERSION[0] << 48) + (PROTOCOL_VERSION[1] << 32) + \
                             (PROTOCOL_VERSION[2] << 16)
        version.release = self.version_string
        version.os = OS
        version.os_version = OS_VERSION
        return version

    def _craft_authentication_packet(self) -> Authenticate:
        authenticate = Authenticate()
        authenticate.username = self.user
        authenticate.password = self.password
        authenticate.tokens.extend(self.tokens)
        authenticate.opus = True
        authenticate.client_type = self.client_type
        return authenticate

    def is_connected(self):
        return self.status != Status.FAILED and self.status != Status.NOT_CONNECTED

    def connect(self):
        self.receive_buffer = bytes()
        self._disconnect = False
        try:
            self.logger.debug("ControlStack: Connecting to the server")
            info = getaddrinfo(self.host, self.port, AF_UNSPEC, SOCK_STREAM)
            socket_ = socket(info[0][0], SOCK_STREAM)
            socket_.settimeout(10)
        except socket_error as exc:
            self.status = Status.FAILED
            self.logger.error("Failed to connect to the server", exc_info=True)
            raise exc

        try:
            self.logger.debug("ControlStack: Setting up TLS")
            context = SSLContext(PROTOCOL_TLSv1_2)
            context.load_cert_chain(certfile=self.cert_file, keyfile=self.key_file)
            self.socket = context.wrap_socket(socket_)
        except AttributeError:
            self.logger.warning("Invalid TLS version, trying TLSv1")
            context = SSLContext(PROTOCOL_TLSv1)
            context.load_cert_chain(certfile=self.cert_file, keyfile=self.key_file)
            self.socket = context.wrap_socket(socket_)

        try:
            self.socket.connect((self.host, self.port))
        except socket_error as se:
            self.status = Status.FAILED
            self.logger.error("ControlStack: Error while upgrading to encrypted connection", exc_info=True)
            raise se

        try:
            self.logger.debug("ControlStack: Sending version")
            version = self._craft_version_packet()
            self.send_message(MessageType.Version, version)
            self.logger.debug("ControlStack: Authenticating...")
            authenticate = self._craft_authentication_packet()
            self.send_message(MessageType.Authenticate, authenticate)
        except socket_error as exc:
            self.status = Status.FAILED
            self.logger.error("ControlStack: Failed to send authentication messages", exc_info=True)
            raise exc
        self.status = Status.AUTHENTICATING
        if not self.thread.is_alive():
            self.thread = Thread(target=self.loop, name="ControlStack:ListenLoop")
            self.thread.start()

    def on_disconnect(self, func: Callable[[], None]):
        self._on_disconnect = func

    def send_message(self, _type: MessageType, message: Message):
        self.logger.debug(f"ControlStack: sending TCP {_type.name}")
        packet = pack("!HL", _type.value, message.ByteSize()) + message.SerializeToString()
        while len(packet) > 0:
            try:
                sent = self.socket.send(packet)
                if sent < 0:
                    raise socket_error("ControlStack: Server socket error")
                packet = packet[sent:]
            except SSLZeroReturnError:
                self.status = Status.FAILED

    def _read_control_messages(self):
        try:
            buffer: bytes = self.socket.recv(READ_BUFFER_SIZE)
            self.receive_buffer += buffer
        except TimeoutError:
            return
        except socket_error:
            self.logger.error("ControlStack: Error while reading control messages", exc_info=True)
            return

        while len(self.receive_buffer) >= 6:
            header = self.receive_buffer[0:6]

            if len(header) < 6:
                break

            (_type, size) = unpack("!HL", header)

            if len(self.receive_buffer) < size + 6:
                break

            message: bytes = self.receive_buffer[6:size + 6]
            self.receive_buffer = self.receive_buffer[size + 6:]
            self._dispatch_control_message(_type, message)

    def send_command(self, cmd: Command):
        if cmd.packet:
            self.send_message(cmd.type, cmd.packet)
            cmd.response = True

    def send_audio_legacy(self, audio: AudioData):
        tcp_packet = audio.legacy_tcp_packet
        while len(tcp_packet) > 0:
            sent = self.socket.send(tcp_packet)
            self.logger.debug(f"ControlStack: audio sent {sent}")
            if sent < 0:
                raise socket_error("ControlStack: Server socket error while sending audio")
            tcp_packet = tcp_packet[sent:]

    def send_audio(self, audio: AudioData):
        self.logger.debug(f"ControlStack: sending audio protobuf")
        self.send_message(MessageType.UDPTunnel, audio.tcp_packet)

    def _listen(self):
        exit_ = False
        parent_thread = current_thread()
        while self.status != Status.NOT_CONNECTED and self.status != Status.FAILED and not self._disconnect:
            if not parent_thread.is_alive():
                self.disconnect()
            self._read_control_messages()
        self._ready.release()
        self.logger.debug(f"ControlStack: Exiting. Status: {self.status} Exit: {exit_}")

    def loop(self):
        self.logger.debug("ControlStack: Entering loop")
        self.logger.debug(self.status)
        while (
                self.status == Status.NOT_CONNECTED or self.status == Status.AUTHENTICATING or self.reconnect) and not self._disconnect:
            self.ping = Ping(self)
            if not self.is_connected():
                self.logger.debug("ControlStack: Reconnecting...")
                self.connect()
            if not self.is_connected() and not self.reconnect:
                self.logger.debug("ControlStack: Connection rejected")
                raise ConnectionRejectedError("Connection refused while connecting to Mumble server (Murmur)")
            self.logger.debug(f"Connected: {self.is_connected()}")
            if self.is_connected():
                try:
                    self.logger.debug("ControlStack: Listening...")
                    self.ping.start()
                    self._listen()
                    self.ping.cancel()
                    self._ready.acquire(True)
                except socket_error as e:
                    self.logger.error(
                        f"ControlStack: Exception {e} cause exit from control loop. Reconnect: {self.reconnect}")
                    self.status = Status.FAILED
            self._on_disconnect()
            sleep(CONNECTION_RETRY_INTERVAL)
        try:
            self.socket.close()
        except socket_error:
            self.logger.debug("ControlStack: Trying to close already close socket!")

    def disconnect(self):
        try:
            self._ready.release()
        except RuntimeError:
            self.logger.debug("ControlStack: ready lock already released")
        self._disconnect = True
        if self.thread.is_alive():
            self.thread.join(timeout=10)
        self.logger.debug("ControlSocket: disconnected")

    def set_application_string(self, string):
        self.version_string = string

    def reauthenticate(self, token):
        packet = Authenticate()
        packet.username = self.user
        packet.password = self.password
        packet.tokens.extend(self.tokens)
        packet.tokens.append(token)
        packet.opus = True
        packet.client_type = self.client_type
        self.send_message(MessageType.Authenticate, packet)

    def enqueue_audio(self, data: AudioData):
        self._voice_dispatcher(data)

    def ready(self):
        self.logger.debug("ControlStack: releasing ready lock")
        try:
            self._ready.release()
        except RuntimeError:
            pass

    def is_ready(self):
        self.logger.debug("ControlStack: checking if ready")
        self._ready.acquire(True)
        self._ready.release()
        self.logger.debug("ControlStack: ready released")

    def __del__(self):
        self.disconnect()

    def set_version(self, packet: Version):
        if packet.version_v2:
            version = packet.version_v2
            self._server_version = (version >> 48 & 65535), (version >> 32 & 65535), (version >> 16 & 65535)
        else:
            version = packet.version_v1
            self._server_version = ((version >> 16 & 255), (version >> 8 & 255), (version & 255))
        if self._server_version >= (1, 5, 0) and PROTOCOL_VERSION >= (1, 5, 0):
            self._voice_dispatcher = self.send_audio
        else:
            self._voice_dispatcher = self.send_audio_legacy

    @property
    def server_version(self):
        return self._server_version
