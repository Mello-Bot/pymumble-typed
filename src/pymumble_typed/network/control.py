from __future__ import annotations

from enum import IntEnum
from queue import Queue, Empty
from socket import getaddrinfo, AF_UNSPEC, SOCK_STREAM, socket, error as socket_error
from ssl import SSLContext, PROTOCOL_TLSv1, PROTOCOL_TLSv1_2, SSLError, SSLEOFError
from struct import pack, unpack
from threading import Thread, current_thread, Lock
from time import sleep
from typing import TYPE_CHECKING

from pymumble_typed import MessageType
from pymumble_typed.commands import Command
from pymumble_typed.constants import PROTOCOL_VERSION, OS, OS_VERSION, VERSION
from pymumble_typed.network import ConnectionRejectedError, READ_BUFFER_SIZE
from pymumble_typed.network.ping import Ping
from pymumble_typed.network.udp_data import AudioData
from pymumble_typed.protobuf.Mumble_pb2 import Version, Authenticate

if TYPE_CHECKING:
    from pymumble_typed.mumble import ClientType
    from google.protobuf.message import Message
    from logging import Logger
    from ssl import SSLSocket
    from collections.abc import Callable


class Status(IntEnum):
    NOT_CONNECTED = 0
    AUTHENTICATING = 1
    CONNECTED = 2
    FAILED = 3


class ControlStack:
    # This is twice the ping delay because it shouldn't timeout before receiving ping responses
    TIMEOUT = Ping.DELAY * 2

    def __init__(self, host: str, port: int, user: str, password: str | None, tokens: list[str], cert_file: str,
                 key_file: str, ping: Ping, client_type: ClientType, logger: Logger):
        self.socket: SSLSocket | None = None
        self.user = user
        self.password = password
        self.tokens = tokens
        self.host = host
        self.port = port
        self.client_type = client_type
        self.cert_file = cert_file
        self.key_file = key_file
        self.logger = logger.getChild(self.__class__.__name__)
        self.version_string: str = f"PyMumble-Typed {VERSION}"
        self.status = Status.NOT_CONNECTED
        self._disconnect = False
        self.reconnect = False
        self._on_disconnect: Callable[[], None] = lambda: None
        self.msg_queue: Queue[Command | AudioData] = Queue(maxsize=20)
        self.audio_queue: Queue[AudioData] = Queue(maxsize=20)
        self.receive_buffer: bytes = b''
        self._dispatch_control_message = lambda _, __: None
        self.thread = Thread(target=self.loop, name="ControlStack:Loop")

        self._ready = Lock()
        self._ready.acquire(True)
        self._server_version = (0, 0, 0)
        self._voice_dispatcher: Callable[[AudioData], None] = self.send_audio_legacy
        self.ping = ping
        self.backoff = 1

    def reinit(self) -> ControlStack:
        self.disconnect()
        return ControlStack(self.host, self.port, self.user, self.password, self.tokens, self.cert_file, self.key_file,
                            self.ping, self.client_type, self.logger.parent)

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
        self.receive_buffer = b''
        self._disconnect = False
        try:
            self.logger.debug("connecting to the server")
            info = getaddrinfo(self.host, self.port, AF_UNSPEC, SOCK_STREAM)
            socket_ = socket(info[0][0], SOCK_STREAM)
            socket_.settimeout(self.TIMEOUT)
        except socket_error as exc:
            self.status = Status.FAILED
            self.logger.error("failed to connect to the server", exc_info=True)
            raise exc

        try:
            self.logger.debug("setting up TLS")
            context = SSLContext(PROTOCOL_TLSv1_2)
            context.load_cert_chain(certfile=self.cert_file, keyfile=self.key_file)
            self.socket = context.wrap_socket(socket_)
        except AttributeError:
            self.logger.warning("invalid TLS version, trying TLSv1")
            context = SSLContext(PROTOCOL_TLSv1)
            context.load_cert_chain(certfile=self.cert_file, keyfile=self.key_file)
            self.socket = context.wrap_socket(socket_)

        try:
            self.socket.connect((self.host, self.port))
        except socket_error as se:
            self.status = Status.FAILED
            self.logger.error("error while upgrading to encrypted connection", exc_info=True)
            raise se

        try:
            self.logger.debug("sending version")
            version = self._craft_version_packet()
            self.send_message(MessageType.Version, version)
            self.logger.debug("authenticating...")
            authenticate = self._craft_authentication_packet()
            self.send_message(MessageType.Authenticate, authenticate)
        except socket_error as exc:
            self.status = Status.FAILED
            self.logger.error("failed to send authentication messages", exc_info=True)
            raise exc
        self.status = Status.AUTHENTICATING
        if not self.thread.is_alive():
            self.thread = Thread(target=self.loop, name="ControlStack:ListenLoop")
            self.thread.start()

    def on_disconnect(self, func: Callable[[], None]):
        self._on_disconnect = func

    def _tcp_failed(self, _type: MessageType = None, message: Message = None):
        if _type:
            self.logger.error(
                f"an error occurred while sending {_type.name}. Attempting to reconnect and resend the packet.",
                exc_info=True)
        else:
            self.logger.error(
                f"an error occurred while sending a TCP Packet. Attempting to reconnect and resend the packet.",
                exc_info=True)
        self.status = Status.FAILED
        if not _type or not message:
            return
        # Attempt to resend the message on connection failed
        cmd = Command()
        cmd.type = _type
        cmd.packet = message
        self.msg_queue.put(cmd)

    def send_message(self, _type: MessageType, message: Message):
        self.logger.debug(f"sending TCP {_type.name}")
        packet = pack("!HL", _type.value, message.ByteSize()) + message.SerializeToString()
        try:
            while len(packet) > 0:
                sent = self.socket.send(packet)
                if sent > 0:
                    packet = packet[sent:]
                else:
                    self._tcp_failed(_type, message)
                    packet = bytes()
        except (SSLError, TimeoutError):
            self._tcp_failed(_type, message)

    def _read_control_messages(self):
        try:
            buffer: bytes = self.socket.recv(READ_BUFFER_SIZE)
            self.receive_buffer += buffer
        except (ConnectionResetError, TimeoutError, SSLEOFError):
            self.logger.warning("Server terminated the connection", exc_info=True)
            self.status = Status.FAILED
            return
        except socket_error:
            self.logger.error("error while reading control messages", exc_info=True)
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
            self.msg_queue.put(cmd)

    def send_audio_legacy(self, audio: AudioData):
        tcp_packet = audio.legacy_tcp_packet
        while len(tcp_packet) > 0:
            try:
                sent = self.socket.send(tcp_packet)
                if sent > 0:
                    tcp_packet = tcp_packet[sent:]
                else:
                    self._tcp_failed()
                    tcp_packet = bytes()
                tcp_packet = tcp_packet[sent:]
            except SSLError:
                self.status = Status.FAILED
                return

    def send_audio(self, audio: AudioData):
        self.logger.debug(f"sending audio protobuf")
        self.send_message(MessageType.UDPTunnel, audio.tcp_packet)

    def _listen(self):
        exit_ = False
        parent_thread = current_thread()
        while self.is_connected() and not self._disconnect:
            if not parent_thread.is_alive():
                self.disconnect()
            self._read_control_messages()
        try:
            self._ready.release()
        except RuntimeError:
            pass
        self.logger.debug(f"exiting listen loop. Status: {self.status} Exit: {exit_}")

    def _send(self):
        exit_ = False
        parent_thread = current_thread()
        while self.is_connected() and not self._disconnect:
            if not parent_thread.is_alive():
                self.disconnect()
            try:
                something = self.msg_queue.get(timeout=self.TIMEOUT)
                if type(something) is AudioData:
                    self._voice_dispatcher(something)
                else:
                    self.send_message(something.type, something.packet)
            except (TimeoutError, Empty):
                pass
        try:
            self._ready.release()
        except RuntimeError:
            pass
        self.logger.debug(f"exiting send loop. Status: {self.status} Exit: {exit_}")

    def timeout(self):
        self.status = Status.FAILED

    def loop(self):
        self.logger.debug("entering loop")
        self.logger.debug(self.status)
        while (
                self.status == Status.NOT_CONNECTED or self.status == Status.AUTHENTICATING or self.reconnect) and not self._disconnect:
            self.ping.reset()
            if not self.is_connected():
                self.logger.debug("reconnecting...")
                try:
                    self.connect()
                    self.backoff = 1
                except socket_error:
                    self.status = Status.FAILED
                    if self.backoff < 60:
                        self.backoff *= 2

            if not self.is_connected() and not self.reconnect:
                self.logger.debug("connection rejected")
                raise ConnectionRejectedError("connection refused while connecting to Mumble Server (Murmur)")
            self.logger.debug(f"connected: {self.is_connected()}")
            if self.is_connected():
                try:
                    self.logger.debug("listening...")
                    self.ping.start()
                    listen_thread = Thread(target=self._listen, name="Control:Listen")
                    send_thread = Thread(target=self._send, name="Control:Send")
                    listen_thread.start()
                    send_thread.start()
                    listen_thread.join()
                    send_thread.join()
                    self.ping.cancel()
                    self._ready.acquire(True)
                except socket_error as e:
                    self.logger.error(
                        f"exception {e} cause exit from control loop. Reconnect: {self.reconnect}")
                    self.status = Status.FAILED
            self._on_disconnect()
            if self.reconnect:
                self.logger.error(f"Connection failed. Retrying in {self.backoff} seconds...")
                sleep(self.backoff)
        try:
            self.socket.close()
        except socket_error:
            self.logger.debug("trying to close already close socket!")

    def disconnect(self):
        try:
            self._ready.release()
        except RuntimeError:
            self.logger.debug("ready lock already released")
        self._disconnect = True
        if self.thread.is_alive():
            self.thread.join(timeout=self.TIMEOUT)
        self.logger.debug("disconnected")

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
        self.msg_queue.put(data)

    def ready(self):
        self.logger.debug("releasing ready lock")
        try:
            self._ready.release()
        except RuntimeError:
            pass

    def is_ready(self):
        self.logger.debug("checking if ready")
        self._ready.acquire(True)
        self._ready.release()
        self.logger.debug("ready released")

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
