from __future__ import annotations

from asyncio import open_connection, create_task, BaseEventLoop
from enum import IntEnum
from socket import error as socket_error
from ssl import SSLContext, PROTOCOL_TLSv1, PROTOCOL_TLSv1_2
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
    from typing import Optional
    from asyncio import StreamReader, StreamWriter
    from pymumble_typed.mumble import ClientType
    from google.protobuf.message import Message
    from logging import Logger
    from typing import Callable


class Status(IntEnum):
    NOT_CONNECTED = 0
    AUTHENTICATING = 1
    CONNECTED = 2
    FAILED = 3


class ControlStack:
    def __init__(self, host: str, port: int, user: str, password: str | None, tokens: list[str], cert_file: str,
                 key_file: str, client_type: ClientType, loop: BaseEventLoop, logger: Logger):
        self.reader: Optional[StreamReader] = None
        self.writer: Optional[StreamWriter] = None
        self._tls_version = None
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
        self.eloop = loop

        self.receive_buffer: bytes = bytes()
        self._dispatch_control_message = lambda _, __: None
        self.thread = Thread(target=self.loop, name="ControlStack:Loop")

        self._ready = Lock()
        self._ready.acquire(True)
        self._server_version = (0, 0, 0)
        self._voice_dispatcher: Callable[[AudioData], None] = self.send_audio_legacy
        self.ping: Ping = Ping(self, self.eloop)

    def reinit(self) -> ControlStack:
        self.disconnect()
        return ControlStack(self.host, self.port, self.user, self.password, self.tokens, self.cert_file, self.key_file,
                            self.client_type, self.eloop, self.logger)

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

    async def connect(self):
        self.receive_buffer = bytes()
        self._disconnect = False
        self.logger.debug("ControlStack: Connecting to the server")
        if not self._tls_version or self._tls_version == PROTOCOL_TLSv1_2:
            try:
                self.logger.debug("ControlStack: Setting up TLS")
                context = SSLContext(PROTOCOL_TLSv1_2)
                context.load_cert_chain(certfile=self.cert_file, keyfile=self.key_file)
                reader, writer = await open_connection(self.host, self.port, ssl=context)
                self.reader = reader
                self.writer = writer
                self._tls_version = PROTOCOL_TLSv1_2
            except Exception as e:
                self._tls_version = PROTOCOL_TLSv1

        if self._tls_version == PROTOCOL_TLSv1:
            try:
                self.logger.warning("Invalid TLS version, trying TLSv1")
                context = SSLContext(PROTOCOL_TLSv1)
                context.load_cert_chain(certfile=self.cert_file, keyfile=self.key_file)
                reader, writer = await open_connection(self.host, self.port, ssl=context)
                self.reader = reader
                self.writer = writer
            except Exception as e:
                self.status = Status.FAILED
                self.logger.error("ControlStack: Error while upgrading to encrypted connection", exc_info=True)
                raise e

        try:
            self.logger.debug("ControlStack: Sending version")
            version = self._craft_version_packet()
            await self.send_message(MessageType.Version, version)
            self.logger.debug("ControlStack: Authenticating...")
            authenticate = self._craft_authentication_packet()
            await self.send_message(MessageType.Authenticate, authenticate)
        except socket_error as exc:
            self.status = Status.FAILED
            self.logger.error("ControlStack: Failed to send authentication messages", exc_info=True)
            raise exc
        self.status = Status.AUTHENTICATING
        _ = create_task(self.loop())


    def on_disconnect(self, func: Callable[[], None]):
        self._on_disconnect = func

    async def send_message(self, _type: MessageType, message: Message):
        self.logger.debug(f"ControlStack: sending TCP {_type.name}")
        packet = pack("!HL", _type.value, message.ByteSize()) + message.SerializeToString()
        try:
            self.writer.write(packet)
            await self.writer.drain()
        except Exception:
            self.logger.error(f"ControlStack: failed to send packet", exc_info=True)

    async def _read_control_messages(self):
        try:
            buffer: bytes = await self.reader.read(READ_BUFFER_SIZE)
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
            print("Message", _type, message)
            await self._dispatch_control_message(_type, message)
            print("Message dispatched")

    def send_command(self, cmd: Command):
        if cmd.packet:
            self.send_message(cmd.type, cmd.packet)
            cmd.response = True

    def send_audio_legacy(self, audio: AudioData):
        tcp_packet = audio.legacy_tcp_packet
        try:
            self.writer.write(tcp_packet)
        except Exception:
            self.logger.error("ControlStack: failed to send audio packet", exc_info=True)

    async def send_audio(self, audio: AudioData):
        self.logger.debug(f"ControlStack: sending audio protobuf")
        await self.send_message(MessageType.UDPTunnel, audio.tcp_packet)

    async def _listen(self):
        exit_ = False
        parent_thread = current_thread()
        while self.status != Status.NOT_CONNECTED and self.status != Status.FAILED and not self._disconnect:
            print("Listening")
            if not parent_thread.is_alive():
                self.disconnect()
            await self._read_control_messages()
        print(self.status, self._disconnect)
        self._ready.release()
        self.logger.debug(f"ControlStack: Exiting. Status: {self.status} Exit: {exit_}")

    async def loop(self):
        self.logger.debug("ControlStack: Entering loop")
        self.logger.debug(self.status)
        while (
                self.status == Status.NOT_CONNECTED or self.status == Status.AUTHENTICATING or self.reconnect) and not self._disconnect:

            if not self.is_connected():
                self.logger.debug("ControlStack: Reconnecting...")
                await self.connect()
            if not self.is_connected() and not self.reconnect:
                self.logger.debug("ControlStack: Connection rejected")
                raise ConnectionRejectedError("Connection refused while connecting to Mumble server (Murmur)")
            self.logger.debug(f"Connected: {self.is_connected()}")
            if self.is_connected():
                try:
                    self.logger.debug("ControlStack: Listening...")
                    self.ping = Ping(self, loop=self.eloop)
                    await self.ping.send()
                    self.ping.start()
                    await self._listen()
                    self.ping.cancel()
                    self._ready.acquire(True)
                except socket_error as e:
                    self.logger.error(
                        f"ControlStack: Exception {e} cause exit from control loop. Reconnect: {self.reconnect}")
                    self.status = Status.FAILED
            self._on_disconnect()
            sleep(CONNECTION_RETRY_INTERVAL)
        try:
            self.writer.close()
            await self.writer.wait_closed()
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
