from __future__ import annotations

from logging import Logger, ERROR, DEBUG, StreamHandler

from pymumble_typed import MessageType
from pymumble_typed.network import ConnectionRejectedError
from pymumble_typed.network.control import ControlStack, Status

import struct

from pymumble_typed.network.voice import VoiceStack
from pymumble_typed.protobuf.MumbleUDP_pb2 import Audio
from pymumble_typed.protobuf.Mumble_pb2 import Version, Authenticate, Ping as PingPacket, Reject, ServerSync, \
    ChannelRemove, ChannelState, UserRemove, UserState, BanList, TextMessage, PermissionDenied, ACL, QueryUsers, \
    CryptSetup, ContextActionModify, ContextAction, UserList, VoiceTarget, PermissionQuery, CodecVersion, UserStats, \
    RequestBlob, ServerConfig

from pymumble_typed.callbacks import Callbacks
from pymumble_typed.channels import Channels
from pymumble_typed.commands import Command
from pymumble_typed.messages import Message as MessageContainer
from pymumble_typed.sound.voice import VoiceOutput
from pymumble_typed.tools import VarInt
from pymumble_typed.users import Users

from enum import IntEnum
from threading import current_thread
from pymumble_typed.sound import AudioType, CodecProfile, CodecNotSupportedError, BANDWIDTH


class ClientType(IntEnum):
    USER = 0
    BOT = 1


class Settings:
    def __init__(self):
        self.server_allow_html = True
        self.server_max_message_length = 5000
        self.server_max_image_message_length = 131072


class Mumble:
    def __init__(self, host: str, user: str, port: int = 64738, password: str = '', cert_file: str = None,
                 key_file: str = None, reconnect: bool = False, tokens: list[str] = None, stereo: bool = False,
                 client_type: ClientType = ClientType.BOT, debug: bool = False, logger: Logger = None):
        super().__init__()
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

        self.positional = None

        self._bandwidth = BANDWIDTH
        self._server_max_bandwidth = 0

        self.users: Users = Users(self)
        self.channels: Channels = Channels(self)
        self.settings = Settings()
        self._control: ControlStack = ControlStack(host, port, user, password, tokens, cert_file, key_file, client_type,
                                                   self._logger)
        self._voice: VoiceStack = VoiceStack(self._control, self._logger)
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

    def start(self):
        self._init()
        self._control.connect()

    def _init(self):
        self._bandwidth = BANDWIDTH
        self._server_max_bandwidth = BANDWIDTH

        self.settings = Settings()
        self.users = Users(self)
        self.channels = Channels(self)
        if self._control:
            self._control.disconnect()
        self._control = self._control.reinit()
        self._control.set_control_message_dispatcher(self._dispatch_control_message)
        self._control.reconnect = self._reconnect
        self._voice: VoiceStack = VoiceStack(self._control, self._logger)
        self.voice = VoiceOutput(self._control, self._voice)

    def _dispatch_control_message(self, _type: int, message: bytes):
        try:
            self._logger.debug(f"Mumble: Received packet type: {MessageType(_type).name}")
        except ValueError:
            self._logger.debug(f"Mumble: Received packet type: {_type}")
        if _type == MessageType.UDPTunnel:
            if self.sound_receive:
                self._sound_received(message)
        elif _type == MessageType.Version:
            packet = Version()
            packet.ParseFromString(message)
            self._logger.debug(f"Mumble: Received version: {packet.version_v1}")
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
            self._voice.sync()
            self.users.set_myself(packet.session)
            self.set_bandwidth(packet.max_bandwidth)
            if self._control.status == Status.AUTHENTICATING:
                self._control.status = Status.CONNECTED
                self._ready = True

                # FIXME: experimental, using number of users as command limit per loop cycle
                #  since this is set on client startup minimum is 5 to avoid excessively low limit
                if len(self.users) > self._control.command_limit:
                    self._control.command_limit = len(self.users)
                self._control.ready()
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
            self._voice.crypt_setup(packet)
            self._voice.ping()
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
                self.settings.server_allow_html = packet.allow_html
            if packet.HasField("message_length"):
                self.settings.server_max_message_length = packet.message_length
            if packet.HasField("image_message_length"):
                self.settings.server_max_image_message_length = packet.image_message_length

    def set_bandwidth(self, bandwidth: int):
        if self._server_max_bandwidth is not None:
            self._bandwidth = min(bandwidth, self._server_max_bandwidth)
        self.voice.encoder.bandwidth = self._bandwidth

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
        self.is_ready()
        lock = self._control.command_queue.push(cmd)
        if blocking and self._control.thread is not current_thread():
            lock.acquire()
            lock.release()
        return lock

    def get_max_message_length(self) -> int:
        return self.settings.server_max_message_length

    def get_max_image_length(self) -> int:
        return self.settings.server_max_message_length

    def denial_type(self, name: str):
        return PermissionDenied.DenyType.Name(name)

    def stop(self):
        self._control.disconnect()

    def request_blob(self, packet):
        self._control.send_message(MessageType.RequestBlob, packet)

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
