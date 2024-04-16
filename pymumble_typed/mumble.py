from __future__ import annotations

import struct
from asyncio import BaseEventLoop, get_running_loop
from enum import IntEnum
from logging import Logger, ERROR, DEBUG, StreamHandler
from threading import current_thread
from typing import Optional

from typing_extensions import TypedDict

from pymumble_typed import MessageType, UdpMessageType
from pymumble_typed.callbacks import Callbacks
from pymumble_typed.channels import Channels
from pymumble_typed.commands import Command
from pymumble_typed.messages import Message as MessageContainer
from pymumble_typed.network import ConnectionRejectedError
from pymumble_typed.network.control import ControlStack, Status
from pymumble_typed.network.voice import VoiceStack
from pymumble_typed.protobuf.MumbleUDP_pb2 import Audio, Ping as UdpPingPacket
from pymumble_typed.protobuf.Mumble_pb2 import Version, Authenticate, Ping as PingPacket, Reject, ServerSync, \
    ChannelRemove, ChannelState, UserRemove, UserState, BanList, TextMessage, PermissionDenied, ACL, QueryUsers, \
    CryptSetup, ContextActionModify, ContextAction, UserList, VoiceTarget, PermissionQuery, CodecVersion, UserStats, \
    RequestBlob, ServerConfig, UDPTunnel
from pymumble_typed.sound import AudioType, CodecProfile, CodecNotSupportedError, BANDWIDTH
from pymumble_typed.sound.voice import VoiceOutput
from pymumble_typed.tools import VarInt
from pymumble_typed.users import Users


class ClientType(IntEnum):
    USER = 0
    BOT = 1


class Settings(TypedDict):
    server_allow_html: bool
    server_max_message_length: int
    server_max_image_message_length: int


class Mumble:
    def __init__(self, host: str, user: str, port: int = 64738, password: str = '', cert_file: str = None,
                 key_file: str = None, reconnect: bool = False, tokens: list[str] = None, stereo: bool = False,
                 client_type: ClientType = ClientType.BOT, loop: Optional[BaseEventLoop] = None, debug: bool = False,
                 logger: Logger = None):
        super().__init__()
        if not loop:
            loop = get_running_loop()
        self._loop = loop
        self._command_limit = 5
        if tokens is None:
            tokens = []
        self._ready = False
        self._debug = debug
        self._parent_thread = current_thread()
        self._logger = logger if logger else Logger("PyMumble-Typed")
        self._logger.setLevel(DEBUG if debug else ERROR)
        if not logger:
            self._logger.addHandler(StreamHandler())
        self._opus_profile = CodecProfile.Audio
        self._stereo = stereo

        self.sound_receive = False
        self._callbacks = Callbacks(self)

        self._bandwidth = BANDWIDTH
        self._server_max_bandwidth = 0
        self.users: Users = Users(self)
        self.channels: Channels = Channels(self)
        self.settings = Settings(server_allow_html=True, server_max_message_length=5000,
                                 server_max_image_message_length=131072)
        self._control: ControlStack = ControlStack(host, port, user, password, tokens, cert_file, key_file, client_type, self._loop,
                                                   self._logger)
        self._voice: VoiceStack = VoiceStack(self._control, self._loop, self._logger)
        self.voice = VoiceOutput(self._control, self._voice)
        self._reconnect = reconnect

    @property
    def sound_output(self):
        return self.voice

    @property
    def voice_connection(self):
        return "udp" if self._voice.active else "tcp"

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

    async def start(self):
        self._init()
        await self._control.connect()

    def _init(self):
        self._bandwidth = BANDWIDTH
        self._server_max_bandwidth = BANDWIDTH

        self.settings = Settings(server_allow_html=True, server_max_message_length=5000,
                                 server_max_image_message_length=131072)
        self.users = Users(self)
        self.channels = Channels(self)
        if self._control:
            self._control.disconnect()
        self._control = self._control.reinit()
        self._control.set_control_message_dispatcher(self._dispatch_control_message)
        self._control.reconnect = self._reconnect
        self._voice: VoiceStack = VoiceStack(self._control, self._loop, self._logger)
        self.voice = VoiceOutput(self._control, self._voice)

    def _dispatch_voice_message(self, packet: bytes):
        _type = packet[0]
        message = packet[1:]
        try:
            self._logger.debug(f"Mumble: Received UDP packet type: {UdpMessageType(_type).name}")
        except ValueError:
            self._logger.debug(f"Mumble: Received UDP packet type: {_type}")
        else:
            if _type == UdpMessageType.Audio and self.sound_receive:
                packet = Audio()
                packet.ParseFromString(message)
                self._sound_received(packet)
            elif _type == UdpMessageType.Ping:
                packet = UdpPingPacket()
                packet.ParseFromString(message)
                if packet.max_bandwidth_per_user:
                    self._server_max_bandwidth = packet.max_bandwidth_per_user
                    self._logger.debug(f"Mumble: updated server max bandwidth per client {self._server_max_bandwidth}")
                self._voice.ping_response(packet)

    def _dispatch_legacy_voice_message(self, packet: bytes):
        pos = 0
        (header,) = struct.unpack("!B", bytes([packet[pos]]))
        _type = (header & 0b11100000) >> 5
        target = header & 0b00011111
        if _type == AudioType.PING:
            self._voice.ping_legacy_response(packet[1:])
        else:
            self._legacy_sound_received(_type, target, packet[1:])

    async def _dispatch_control_message(self, _type: int, message: bytes):
        try:
            self._logger.debug(f"Mumble: Received TCP packet type: {MessageType(_type).name}")
        except ValueError:
            self._logger.debug(f"Mumble: Received TCP packet type: {_type}")
        if _type == MessageType.UDPTunnel and self.sound_receive:
            if self._control.server_version < (1, 5, 0):
                self._dispatch_legacy_voice_message(message)
            else:
                packet = UDPTunnel()
                packet.ParseFromString(message)
                udp_packet = Audio()
                udp_packet.ParseFromString(packet.packet)
                self._sound_received(udp_packet)
        elif _type == MessageType.Version:
            packet = Version()
            packet.ParseFromString(message)
            self._control.set_version(packet)
            self._logger.debug(f"Mumble: Received version: {packet.version_v1}")
            if self._control.server_version < (1, 5, 0):
                self._voice.set_voice_message_dispatcher(self._dispatch_legacy_voice_message)
            else:
                self._voice.set_voice_message_dispatcher(self._dispatch_voice_message)
        elif _type == MessageType.Authenticate:
            packet = Authenticate()
            packet.ParseFromString(message)
            self._logger.debug(f"Mumble: Received authenticate. Session: {packet.session}")
        elif _type == MessageType.PingPacket:
            packet = PingPacket()
            packet.ParseFromString(message)
            self._control.ping.receive(packet)
        elif _type == MessageType.Reject:
            packet = Reject()
            packet.ParseFromString(message)
            self._control.status = Status.FAILED
            self._control.ready()
            raise ConnectionRejectedError(packet.reason)
        elif _type == MessageType.ServerSync:
            packet = ServerSync()
            packet.ParseFromString(message)
            await self._voice.sync()
            self.users.set_myself(packet.session)
            self.set_bandwidth(packet.max_bandwidth)
            if self._control.status == Status.AUTHENTICATING:
                self._control.status = Status.CONNECTED
                self._ready = True
                self._control.ready()
                self._callbacks.ready()
                await self._callbacks.dispatch("on_connect")
        elif _type == MessageType.ChannelRemove:
            packet = ChannelRemove()
            packet.ParseFromString(message)
            await self.channels.remove(packet.channel_id)
        elif _type == MessageType.ChannelState:
            packet = ChannelState()
            packet.ParseFromString(message)
            await self.channels.handle_update(packet)
        elif _type == MessageType.UserRemove:
            packet = UserRemove()
            packet.ParseFromString(message)
            self.users.remove(packet)
        elif _type == MessageType.UserState:
            packet = UserState()
            packet.ParseFromString(message)
            await self.users.handle_update(packet)
        elif _type == MessageType.BanList:
            packet = BanList()
            packet.ParseFromString(message)
        elif _type == MessageType.TextMessage:
            packet = TextMessage()
            packet.ParseFromString(message)
            await self._callbacks.dispatch("on_message", MessageContainer(self, packet))
        elif _type == MessageType.PermissionDenied:
            packet = PermissionDenied()
            packet.ParseFromString(message)
            # FIXME: CALLBACK Permission Denied
            await  self._callbacks.dispatch("on_permission_denied", packet.session, packet.channel_id, packet.name,
                                            packet.type, packet.reason)
        elif _type == MessageType.ACL:
            packet = ACL()
            packet.ParseFromString(message)
            self.channels[packet.channel_id].update_acl(packet)
            # FIXME: CALLBACK ACL
            await self._callbacks.dispatch("on_acl_received")
        elif _type == MessageType.QueryUsers:
            packet = QueryUsers()
            packet.ParseFromString(message)
        elif _type == MessageType.CryptSetup:
            packet = CryptSetup()
            packet.ParseFromString(message)
            self._voice.crypt_setup(packet)
            await self._voice.ping()
        elif _type == MessageType.ContextActionModify:
            packet = ContextActionModify()
            packet.ParseFromString(message)
            # FIXME: CALLBACK ContextActionModify
            await self._callbacks.dispatch("on_context_action")
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
        elif _type == MessageType.UserStats:
            packet = UserStats()
            packet.ParseFromString(message)
        elif _type == MessageType.RequestBlob:
            packet = RequestBlob()
            packet.ParseFromString(message)
        elif _type == MessageType.ServerConfig:
            packet = ServerConfig()
            packet.ParseFromString(message)
            if packet.HasField("max_bandwidth"):
                self._server_max_bandwidth = packet.max_bandwidth
            if packet.HasField("allow_html"):
                self.settings["server_allow_html"] = packet.allow_html
            if packet.HasField("message_length"):
                self.settings["server_max_message_length"] = packet.message_length
            if packet.HasField("image_message_length"):
                self.settings["server_max_image_message_length"] = packet.image_message_length

    def set_bandwidth(self, bandwidth: int):
        if self._server_max_bandwidth is not None:
            self._bandwidth = min(bandwidth, self._server_max_bandwidth)
        self.voice.encoder.bandwidth = self._bandwidth

    def _legacy_sound_received(self, _type: AudioType, target: int, packet: bytes):
        pos = 0
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
                    self._logger.error(f"Invalid user session {session.value}")
            pos += size

    def _sound_received(self, packet: Audio):
        try:
            user = self.users[packet.sender_session]
            user.sound.add(packet.opus_data, packet.frame_number, AudioType.OPUS, packet.target)
        except KeyError:
            self._logger.error(f"Invalid user session {packet.sender_session}")

    def set_application_string(self, string: str):
        self._control.set_application_string(string)

    def set_loop_rate(self, rate: float):
        self._control.loop_rate = rate

    def set_codec_profile(self, profile: CodecProfile):
        self._opus_profile = profile

    def get_codec_profile(self) -> CodecProfile:
        return self._opus_profile

    def set_receive_sound(self, value: bool):
        self.sound_receive = value

    def is_ready(self):
        self._control.is_ready()

    def execute_command(self, cmd: Command, blocking: bool = True):
        if blocking:
            self.is_ready()
        self._control.send_message(cmd.type, cmd.packet)
        return None

    def get_max_message_length(self) -> int:
        return self.settings["server_max_message_length"]

    def get_max_image_length(self) -> int:
        return self.settings["server_max_message_length"]

    def stop(self):
        self._control.disconnect()

    async def request_blob(self, packet):
        await self._control.send_message(MessageType.RequestBlob, packet)

    def reauthenticate(self, token):
        self._control.reauthenticate(token)

    def set_whisper(self, target_ids: list[int], channel=False):
        self.voice.target = 1 if channel else 2
        command = VoiceTarget()
        command.id = self.voice.target
        command.targets.extend(target_ids)
        self.execute_command(command)

    def remove_whisper(self):
        self.voice.target = 0
        command = VoiceTarget()
        command.id = self.voice.target
        self.execute_command(command)
