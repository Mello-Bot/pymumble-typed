from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from logging import Logger

import struct
import sys
from concurrent.futures import Future
from contextlib import suppress
from enum import IntEnum
from logging import DEBUG, ERROR, Formatter, StreamHandler, getLogger
from signal import SIGINT, signal
from threading import Lock, current_thread

from google.protobuf.message import DecodeError

from pymumble_typed import MessageType, UdpMessageType
from pymumble_typed.blobs import BlobDB
from pymumble_typed.callbacks import Callbacks
from pymumble_typed.channels import Channels
from pymumble_typed.commands import Command, RequestBlobCmd, VoiceTarget
from pymumble_typed.exceptions import ConnectionLostError, PermissionDeniedError
from pymumble_typed.messages import Message as MessageContainer
from pymumble_typed.network import ConnectionRejectedError
from pymumble_typed.network.control import ControlStack, Status
from pymumble_typed.network.ping import Ping
from pymumble_typed.network.voice import VoiceStack
from pymumble_typed.protobuf import Mumble_pb2
from pymumble_typed.protobuf.MumbleUDP_pb2 import Audio
from pymumble_typed.protobuf.MumbleUDP_pb2 import Ping as UdpPingPacket
from pymumble_typed.sound import BANDWIDTH, AudioType, CodecNotSupportedError, CodecProfile
from pymumble_typed.sound.audio import OpusPacket
from pymumble_typed.sound.voice import VoiceOutput
from pymumble_typed.tools import InvalidVarIntError, VarInt
from pymumble_typed.users import Users


class ClientType(IntEnum):
    USER = 0
    BOT = 1


class Settings(TypedDict):
    server_allow_html: bool
    server_max_message_length: int
    server_max_image_message_length: int


class Mumble:
    # Command types the server echoes back as a state change (or rejects with
    # PermissionDenied); their futures resolve when that reply arrives. Every other
    # command type gets no confirmation and is resolved immediately (fire-and-forget).
    _CONFIRMED_TYPES = frozenset(
        (
            MessageType.UserState,
            MessageType.ChannelState,
            MessageType.ChannelRemove,
            MessageType.UserRemove,
        )
    )
    # PermissionDenied types for a channel creation that may carry no channel_id; such a
    # denial is matched by command kind (ChannelState) instead. Only confirmed (tracked)
    # commands are matched, so this is limited to ChannelState.
    _CHANNEL_CREATION_DENY_TYPES = frozenset(
        (
            Mumble_pb2.PermissionDenied.ChannelName,
            Mumble_pb2.PermissionDenied.TemporaryChannel,
            Mumble_pb2.PermissionDenied.NestingLimit,
            Mumble_pb2.PermissionDenied.ChannelCountLimit,
        )
    )

    def __init__(
        self,
        host: str,
        user: str,
        port: int = 64738,
        password: str = "",
        cert_file: str | None = None,
        key_file: str | None = None,
        reconnect: bool = False,
        tokens: list[str] | None = None,
        stereo: bool = False,
        client_type: ClientType = ClientType.BOT,
        db_path: str = ":memory:",
        blob_greedy_update: bool = False,
        max_processes: int = 1,
        debug: bool = False,
        logger: Logger | None = None,
    ):
        super().__init__()
        self._command_limit = 5
        # Commands awaiting a server state echo (or PermissionDenied), in insertion (FIFO)
        # order. Guarded by _pending_lock. Only commands whose type the server echoes back
        # are tracked here; everything else is resolved immediately (see execute_command).
        self._pending_commands: list[Command] = []
        # Blob requests awaiting their data, keyed by (kind, target id) where kind is
        # "texture"/"comment" (user, by session) or "description" (channel, by id). The
        # data arrives in a later UserState/ChannelState. Guarded by _pending_lock.
        self._pending_blobs: dict[tuple[str, int], list[Future]] = {}
        self._pending_lock = Lock()
        if tokens is None:
            tokens = []
        self._ready = False
        self._debug = debug
        self._parent_thread = current_thread()
        formatter = Formatter("%(asctime)s - %(name)s - %(levelname)s: %(message)s")
        handler = StreamHandler(stream=sys.stdout)
        handler.setFormatter(formatter)
        self.max_processes = max_processes
        self._logger = logger.getChild("PyMumble-Typed") if logger else getLogger("PyMumble-Typed")
        self._logger.setLevel(DEBUG if debug else ERROR)
        if not self._logger.handlers:
            self._logger.addHandler(handler)
        self.blob_greedy_update = blob_greedy_update
        self._blob = BlobDB(self._logger, db_path)
        self._opus_profile = CodecProfile.Audio
        self._stereo = stereo

        self.sound_receive = False
        self._callbacks = Callbacks(self)

        self._bandwidth = BANDWIDTH
        self._server_max_bandwidth = 0
        self.users: Users = Users(self, self._blob)
        self.channels: Channels = Channels(self, self._blob)
        self.settings = Settings(
            server_allow_html=True, server_max_message_length=5000, server_max_image_message_length=131072
        )
        self._ping: Ping = Ping()
        self._control: ControlStack = ControlStack(
            host, port, user, password, tokens, cert_file, key_file, self._ping, client_type, self._logger
        )
        self._voice: VoiceStack = VoiceStack(self._control, self._logger)
        self._ping.set_voice(self._voice)
        self._ping.set_control(self._control)
        self.voice = VoiceOutput(self._control, self._voice)
        self._reconnect = reconnect

        with suppress(ValueError):  # Workaround for Python 3.14, signal worked on Python <=3.13
            signal(SIGINT, lambda _, __: self.stop())

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

    def is_connected(self) -> bool:
        if not self._control:
            return False
        return self._control.is_connected()

    def start(self):
        self._init()
        self._control.connect()

    def _init(self):
        self._bandwidth = BANDWIDTH
        self._server_max_bandwidth = BANDWIDTH

        self.settings = Settings(
            server_allow_html=True, server_max_message_length=5000, server_max_image_message_length=131072
        )
        self.users = Users(self, self._blob)
        self.channels = Channels(self, self._blob)
        if self._control:
            self._control.disconnect()
        self._control = self._control.reinit()
        self._control.set_control_message_dispatcher(self._dispatch_control_message)
        self._control.reconnect = self._reconnect
        self._voice: VoiceStack = VoiceStack(self._control, self._logger)
        self.voice = VoiceOutput(self._control, self._voice)
        self._control.set_disconnect_action(self._handle_disconnect)
        self._ping.set_control(self._control)
        self._ping.set_voice(self._voice)
        self._ping.reset()

    def _dispatch_voice_message(self, packet: bytes):
        _type = packet[0]
        message = packet[1:]
        try:
            self._logger.debug(f"received UDP packet type: {UdpMessageType(_type).name}")
        except ValueError:
            self._logger.debug(f"received UDP packet type: {_type}")
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
                    self._logger.debug(f"updated server max bandwidth per client {self._server_max_bandwidth}")
                self._voice.ping_response(packet)

    def _dispatch_legacy_voice_message(self, packet: bytes):
        try:
            pos = 0
            (header,) = struct.unpack("!B", bytes([packet[pos]]))
            _type = (header & 0b11100000) >> 5
            target = header & 0b00011111
            if _type == AudioType.PING:
                self._voice.ping_legacy_response(packet[1:])
            else:
                self._legacy_sound_received(_type, target, packet[1:])
        except (InvalidVarIntError, struct.error, IndexError):
            self._logger.warning("dropping malformed legacy voice packet", exc_info=True)

    def _dispatch_control_message(self, _type: int, message: bytes):
        try:
            self._logger.debug(f"received TCP packet type: {MessageType(_type).name}")
        except ValueError:
            self._logger.debug(f"received TCP packet type: {_type}")
        if _type == MessageType.UDPTunnel and self.sound_receive:
            if self._control.server_version < (1, 5, 0):
                self._dispatch_legacy_voice_message(message)
            else:
                packet = Mumble_pb2.UDPTunnel()
                packet.ParseFromString(message)
                udp_packet = Audio()
                udp_packet.ParseFromString(packet.packet)
                self._sound_received(udp_packet)
            return

        try:
            msg_type = MessageType(_type)
        except ValueError:
            self._logger.warning("unknown control message type %d, skipping", _type)
            return
        MsgClass = getattr(Mumble_pb2, msg_type.name)  # noqa: N806
        packet = MsgClass()
        try:
            packet.ParseFromString(message)
        except DecodeError:
            self._logger.warning("malformed %s payload, skipping", msg_type.name)
            return
        match msg_type:
            case MessageType.Version:
                # FIXME(nico9889): this is a workaround, I didn't consider that the users would change their session ID
                #    after a reconnect. Without clearing the user map, the user would be set duplicated.
                #    We are clearing the channels map as well for good measure.
                #    At this time there's no usable callback to the Mumble class to clear the user map, so we clear that
                #    once the Version packet is received, as the connection is starting at this point.
                self.users.clear()
                self.channels.clear()
                self._control.set_version(packet)
                self._logger.debug(f"received version: {packet.version_v1}")
                if self._control.server_version < (1, 5, 0):
                    self._voice.set_voice_message_dispatcher(self._dispatch_legacy_voice_message)
                else:
                    self._voice.set_voice_message_dispatcher(self._dispatch_voice_message)
            case MessageType.Authenticate:
                self._logger.debug(f"received authenticate. Session: {packet.session}")
            case MessageType.Ping:
                self._control.ping.tcp.update()
            case MessageType.Reject:
                self._control.status = Status.FAILED
                self._control.ready()
                raise ConnectionRejectedError(packet.reason)
            case MessageType.ServerSync:
                if self.blob_greedy_update:
                    user_comment_sessions = [
                        user.session for user in self.users.values() if not user.is_comment_updated()
                    ]
                    user_texture_sessions = [
                        user.session for user in self.users.values() if not user.is_avatar_updated()
                    ]
                    channel_ids = [channel.id for channel in self.channels.values() if channel.needs_update()]
                    if user_comment_sessions or user_texture_sessions or channel_ids:
                        self._logger.debug(
                            f"requesting blob updates for UsersComment({user_comment_sessions}), "
                            f"UsersTexture({user_texture_sessions}), Channels({channel_ids})"
                        )
                        cmd = RequestBlobCmd(
                            user_texture_hashes=user_texture_sessions,
                            user_comment_hashes=user_comment_sessions,
                            channel_comment_hashes=channel_ids,
                        )
                        self.execute_command(cmd, False)
                self._voice.sync()
                self.users.set_myself(packet.session)
                self.set_bandwidth(packet.max_bandwidth)
                if self._control.status == Status.AUTHENTICATING:
                    self._control.status = Status.CONNECTED
                    self._ready = True
                    self._control.ready()
                    self._callbacks.ready()
                    self._callbacks.dispatch("on_connect")
            case MessageType.ChannelRemove:
                self.channels.remove(packet.channel_id)
                self._handle_channel_remove_success(packet.channel_id)
            case MessageType.ChannelState:
                self.channels.handle_update(packet)
                self._handle_channel_state_success(packet)
                self._handle_channel_blob(packet)
            case MessageType.UserRemove:
                self.users.remove(packet)
                self._handle_user_remove_success(packet)
            case MessageType.UserState:
                self.users.handle_update(packet)
                self._handle_user_state_success(packet)
                self._handle_user_blob(packet)
            case MessageType.BanList:
                pass
            case MessageType.TextMessage:
                self._callbacks.dispatch("on_message", MessageContainer(self, packet))
            case MessageType.PermissionDenied:
                self._handle_permission_denied(packet)
                self._callbacks.dispatch(
                    "on_permission_denied", packet.session, packet.channel_id, packet.name, packet.type, packet.reason
                )
            case MessageType.ACL:
                self.channels[packet.channel_id].update_acl(packet)
                # FIXME(nico9889): CALLBACK ACL
                self._callbacks.dispatch("on_acl_received")
            case MessageType.QueryUsers:
                pass
            case MessageType.CryptSetup:
                self._voice.crypt_setup(packet)
            case MessageType.ContextActionModify:
                # FIXME(nico9889): CALLBACK ContextActionModify
                self._callbacks.dispatch("on_context_action")
            case (
                MessageType.ContextAction
                | MessageType.UserList
                | MessageType.VoiceTarget
                | MessageType.PermissionQuery
                | MessageType.CodecVersion
                | MessageType.UserStats
            ):
                pass
            case MessageType.ServerConfig:
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
        pos += session.decode(packet[pos : pos + 10])

        sequence = VarInt()
        pos += sequence.decode(packet[pos : pos + 10])

        terminator = False

        while (pos < len(packet)) and not terminator:
            if _type == AudioType.OPUS:
                size = VarInt()
                pos += size.decode(packet[pos : pos + 10])
                size = size.value

                if not (size & 0x2000):
                    terminator = True
                size &= 0x1FFF
            else:
                (header,) = struct.unpack("!B", packet[pos : pos + 1])
                if not (header & 0b10000000):
                    terminator = True
                size = header & 0b01111111
                pos += 1

            if size > 0:
                try:
                    user = self.users[session.value]
                    if _type != AudioType.OPUS:
                        raise CodecNotSupportedError(f"Codec not supported: {_type.name}")
                    packet = OpusPacket(packet[pos : pos + size], sequence.value, target)
                    self._callbacks.dispatch("on_sound_received", user, packet)
                    sequence.value += 1
                except CodecNotSupportedError:
                    self._logger.error("codec not supported", exc_info=True)
                except KeyError:
                    self._logger.error(f"invalid user session {session.value}")
            pos += size

    def _sound_received(self, packet: Audio):
        try:
            user = self.users[packet.sender_session]
            wrapper = OpusPacket(packet.opus_data, packet.frame_number, packet.target)
            self._callbacks.dispatch("on_sound_received", user, wrapper)
        except CodecNotSupportedError:
            self._logger.error("codec not supported", exc_info=True)
        except KeyError:
            self._logger.error(f"Invalid user session {packet.sender_session}")

    def set_application_string(self, string: str):
        self._control.set_application_string(string)

    def set_codec_profile(self, profile: CodecProfile):
        self._opus_profile = profile

    def get_codec_profile(self) -> CodecProfile:
        return self._opus_profile

    def set_receive_sound(self, value: bool):
        self.sound_receive = value

    def is_ready(self):
        self._control.is_ready()

    def execute_command(self, cmd: Command, blocking: bool = True) -> Future:
        """
        Enqueue a command and return a Future for its outcome.

        Commands the server echoes back as a state change (``_CONFIRMED_TYPES``) are
        tracked: their future resolves with the resulting state object when the echo
        arrives, or raises PermissionDeniedError if the server rejects them (and
        ConnectionLostError if the connection drops first). Every other command gets no
        confirmation from the server, so it is sent fire-and-forget and its future is
        resolved immediately with ``True`` (see docs/async-commands.md for the full list).
        """
        if blocking:
            self.is_ready()
        future: Future = Future()
        cmd.future = future
        if cmd.type in self._CONFIRMED_TYPES:
            with self._pending_lock:
                self._pending_commands.append(cmd)
            self._control.send_command(cmd)
        else:
            # Fire-and-forget: the server sends no reply for this command, so there is
            # nothing to wait for — resolve as soon as it is enqueued.
            self._control.send_command(cmd)
            future.set_result(True)
        return future

    @staticmethod
    def _effective_actor(packet) -> int:
        """
        Session that caused a UserState/UserRemove change. The server sets ``actor`` only
        when the change is made *by another* user (e.g. an admin moves/mutes us); a user's
        *own* changes come back with ``actor`` unset, so an absent actor maps back to the
        affected session.
        """
        return packet.actor or packet.session

    def _pop_pending(self, predicate) -> Command | None:
        """Remove and return the first pending command matching ``predicate`` (FIFO)."""
        if not self._pending_commands:
            # Lock-free fast path: nothing is tracked, so every state message would
            # otherwise pay a lock acquire + full scan for no reason.
            return None
        with self._pending_lock:
            for index, pending in enumerate(self._pending_commands):
                if not pending.future.done() and predicate(pending):
                    del self._pending_commands[index]
                    return pending
        return None

    def _resolve_pending(self, predicate, result) -> None:
        """Resolve the first pending command matching ``predicate`` with ``result``."""
        pending = self._pop_pending(predicate)
        if pending is not None:
            pending.future.set_result(result)

    def _handle_user_state_success(self, packet):
        myself = self.users.myself
        # Our own changes (e.g. move_in() / self-mute) come back with `actor` unset, which
        # _effective_actor maps back to our session — so they still count as caused by us
        # instead of hanging until disconnect cleanup.
        if myself is None or self._effective_actor(packet) != myself.session:
            return
        self._resolve_pending(
            lambda p: p.type == MessageType.UserState and p.target_session == packet.session,
            self.users.get(packet.session),
        )

    def _handle_user_remove_success(self, packet):
        myself = self.users.myself
        if myself is None or not packet.HasField("actor") or packet.actor != myself.session:
            return
        self._resolve_pending(
            lambda p: p.type == MessageType.UserRemove and p.target_session == packet.session,
            True,
        )

    def _handle_channel_state_success(self, packet):
        def matches(command: Command) -> bool:
            if command.type != MessageType.ChannelState:
                return False
            command_packet = command.packet
            if command_packet.HasField("channel_id"):
                return command_packet.channel_id == packet.channel_id
            # Create: the request has no channel_id, so match on name and, only when the
            # echo carries it, parent. The server omits parent for some channels (e.g. at
            # the root), and requiring it would leave the create's future unresolved
            # rather than handing back the new Channel.
            if not (command_packet.HasField("name") and packet.HasField("name")):
                return False
            if command_packet.name != packet.name:
                return False
            if command_packet.HasField("parent") and packet.HasField("parent"):
                return command_packet.parent == packet.parent
            return True

        self._resolve_pending(matches, self.channels.get(packet.channel_id))

    def _handle_channel_remove_success(self, channel_id: int):
        self._resolve_pending(
            lambda p: p.type == MessageType.ChannelRemove and p.target_channel == channel_id,
            True,
        )

    @staticmethod
    def _resolved_future(value) -> Future:
        """A Future already resolved with ``value`` (for blobs already cached locally)."""
        future: Future = Future()
        future.set_result(value)
        return future

    def _await_blob(self, kind: str, target_id: int, command: Command) -> Future:
        """
        Send a RequestBlob and return a Future resolved when the data arrives in the
        matching UserState/ChannelState (keyed by ``(kind, target_id)``)."""
        future: Future = Future()
        with self._pending_lock:
            self._pending_blobs.setdefault((kind, target_id), []).append(future)
        self._control.send_command(command)
        return future

    def _resolve_blobs(self, kind: str, target_id: int, value):
        if not self._pending_blobs:
            return  # lock-free fast path: no blob fetch is waiting
        with self._pending_lock:
            futures = self._pending_blobs.pop((kind, target_id), [])
        for future in futures:
            if not future.done():
                future.set_result(value)

    def _handle_user_blob(self, packet):
        if not (packet.HasField("comment") or packet.HasField("texture")):
            return
        user = self.users.get(packet.session)
        if user is None:
            return
        if packet.HasField("comment"):
            self._resolve_blobs("comment", packet.session, user.comment)
        if packet.HasField("texture"):
            self._resolve_blobs("texture", packet.session, user.texture)

    def _handle_channel_blob(self, packet):
        if not packet.HasField("description"):
            return
        channel = self.channels.get(packet.channel_id)
        if channel is not None:
            self._resolve_blobs("description", packet.channel_id, channel.description)

    def _handle_permission_denied(self, packet):
        def denied_channels(command: Command) -> tuple[int, ...]:
            # target_channel covers the ChannelState/ChannelRemove channel_id; the rest are
            # the channels only a denial cares about: a create's parent and a move's target.
            if command.target_channel is not None:
                return (command.target_channel,)
            packet_ = command.packet
            if packet_ is None:
                return ()
            if command.type == MessageType.ChannelState and packet_.HasField("parent"):
                return (packet_.parent,)  # CreateChannel carries parent, not channel_id
            if command.type == MessageType.UserState and packet_.HasField("channel_id"):
                return (packet_.channel_id,)  # move destination
            return ()

        def matches(command: Command) -> bool:
            # target_session covers the UserState/UserRemove session fields.
            if packet.HasField("session") and command.target_session == packet.session:
                return True
            if packet.HasField("channel_id") and packet.channel_id in denied_channels(command):
                return True
            # Creation denials may carry no channel_id; match by the command kind.
            if packet.type in self._CHANNEL_CREATION_DENY_TYPES:
                return command.type == MessageType.ChannelState
            return False

        # Only tracked (confirmed) commands are matched; fire-and-forget commands have
        # already resolved, so a denial that matches none simply fires the callback below.
        pending = self._pop_pending(matches)
        if pending is not None:
            channel_id = packet.channel_id if packet.HasField("channel_id") else None
            session = packet.session if packet.HasField("session") else None
            pending.future.set_exception(
                PermissionDeniedError(packet.type, packet.reason, channel_id, session)
            )

    def _cleanup_pending_commands(self):
        """
        Fail every outstanding command and blob future. Called when the connection is lost
        so callers awaiting confirmation never hang."""
        with self._pending_lock:
            pending = self._pending_commands
            self._pending_commands = []
            blobs = [future for futures in self._pending_blobs.values() for future in futures]
            self._pending_blobs = {}
        for command in pending:
            if not command.future.done():
                command.future.set_exception(
                    ConnectionLostError("connection lost before the command was confirmed")
                )
        for future in blobs:
            if not future.done():
                future.set_exception(ConnectionLostError("connection lost before the blob arrived"))

    def _handle_disconnect(self):
        self._cleanup_pending_commands()
        self.callbacks.dispatch("on_disconnect")

    def get_max_message_length(self) -> int:
        return self.settings["server_max_message_length"]

    def get_max_image_length(self) -> int:
        return self.settings["server_max_message_length"]

    def stop(self):
        self.logger.debug("Received Termination Signal. Stopping Mumble client...")
        self._control.disconnect(True)
        self._voice.stop()

    def request_blob(self, packet):
        self._control.send_message(MessageType.RequestBlob, packet)

    def reauthenticate(self, token):
        self._control.reauthenticate(token)

    def set_whisper(self, target_ids: list[int], channel=False) -> Future[bool]:
        # VoiceTarget is not echoed by the server: fire-and-forget, resolves to True.
        self.voice.target = 1 if channel else 2
        command = VoiceTarget(self.voice.target, target_ids)
        return self.execute_command(command)

    def remove_whisper(self) -> Future[bool]:
        self.voice.target = 0
        command = VoiceTarget(self.voice.target, [])
        return self.execute_command(command)
