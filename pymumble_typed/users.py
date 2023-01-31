from __future__ import annotations

from typing import TYPE_CHECKING

from pymumble_typed.channels import Channel
from pymumble_typed.sound.soundqueue import SoundQueue

if TYPE_CHECKING:
    from pymumble_typed.mumble import Mumble
    from pymumble_typed.callbacks import Callbacks

from struct import unpack
from threading import Lock

from pymumble_typed.Mumble_pb2 import UserState, UserRemove, RequestBlob, Authenticate

from pymumble_typed.commands import ModUserState, Move, TextPrivateMessage, RemoveUser


class User:
    def __init__(self, mumble: Mumble, callbacks: Callbacks, packet: UserState):
        self.sound = SoundQueue(mumble, callbacks)
        self._mumble: Mumble = mumble
        self.hash: str = packet.hash
        self.session: int = packet.session
        self.name = packet.name
        self.priority_speaker = packet.priority_speaker
        self.channel_id: int = packet.channel_id
        self.muted: bool = packet.mute
        self.self_muted = packet.self_mute
        self.deaf = packet.deaf
        self.self_deaf = packet.self_deaf
        self.suppressed = packet.suppress
        self._texture_hash = packet.texture_hash
        self._comment_hash = packet.comment_hash
        self.comment: str = ""
        self.texture: str = ""
        self._update_comment()
        self._update_texture()
        self._users = self._mumble.users

    def myself(self):
        return self._users.myself.session == self.session

    def update(self, packet: UserState):
        actions = {}
        if self.channel_id != packet.channel_id:
            actions["channel_id"] = packet.channel_id
            self.channel_id: int = packet.channel_id
        if self.name != packet.name:
            actions["name"] = packet.name
            self.name = packet.name
        if self.priority_speaker != packet.priority_speaker:
            actions["priority_speaker"] = packet.priority_speaker
            self.priority_speaker = packet.priority_speaker
        if self.muted != packet.muted:
            actions["muted "] = packet.mute
            self.muted = packet.mute
        if self.self_muted != packet.self_muted:
            actions["self_muted "] = packet.self_mute
            self.self_muted = packet.self_mute
        if self.deaf != packet.deaf:
            actions["deaf "] = packet.deaf
            self.deaf = packet.deaf
        if self.self_deaf != packet.self_deaf:
            actions["self_deaf "] = packet.deaf
            self.self_deaf = packet.deaf
        if self.suppressed != packet.suppressed:
            actions["suppressed "] = packet.suppress
            self.suppressed = packet.suppress

        if packet.HasField("comment_hash"):
            if packet.HasField("comment"):
                self.comment = packet.comment
            else:
                self._update_comment()
        if packet.HasField("texture_hash"):
            if packet.HasField("texture"):
                self.texture = packet.texture
            else:
                self._update_texture()
        return actions

    def _update_comment(self):
        if not self._comment_hash:
            return
        packet = RequestBlob()
        packet.session_comment.extend(unpack("!51", self._comment_hash))
        self._mumble.request_blob(packet)

    def _update_texture(self):
        if not self._texture_hash:
            return
        packet = RequestBlob()
        packet.session_texture.extend(unpack("!51", self._texture_hash))
        self._mumble.request_blob(packet)

    def mute(self, myself: bool = False, action: bool = True):
        if self.myself() and myself:
            command = ModUserState(self.session, self_mute=action)
        else:
            command = ModUserState(self.session, mute=action)
        self._mumble.execute_command(command)

    def unmute(self, myself: bool = False):
        self.mute(myself, False)

    def deafen(self, myself: bool = False, action: bool = True):
        if self.myself() and myself:
            command = ModUserState(self.session, self_deaf=action)
        else:
            command = ModUserState(self.session, deaf=action)
        self._mumble.execute_command(command)

    def undeafen(self, myself: bool = False):
        self.deafen(myself, False)

    def suppress(self, action: bool = True):
        command = ModUserState(self.session, suppress=action)
        self._mumble.execute_command(command)

    def unsuppress(self):
        self.suppress(False)

    def recording(self, action: bool = True):
        command = ModUserState(self.session, recording=action)
        self._mumble.execute_command(command)

    def unrecording(self):
        self.recording(False)

    def comment(self, comment: str):
        command = ModUserState(self.session, comment=comment)
        self._mumble.execute_command(command)

    def texture(self, texture: str):
        command = ModUserState(self.session, texture=texture)
        self._mumble.execute_command(command)

    def register(self):  # TODO: check if this is correct
        command = ModUserState(self.session, user_id=0)
        self._mumble.execute_command(command)

    def update_context(self, context_name: bytes):
        command = ModUserState(self.session, plugin_context=context_name)
        self._mumble.execute_command(command)

    def move_in(self, channel: Channel, token: str = None):
        if token:
            packet = Authenticate()
            packet.username = self._mumble.user
            packet.password = self._mumble.password
            packet.tokens.extend(self._mumble.tokens)
            packet.tokens.append(token)
            packet.opus = True
            packet.client_type = self._mumble.client_type
            self._mumble.send_message(MessageType.Authenticate, packet)
        command = Move(self.session, channel.id)
        self._mumble.execute_command(command)

    def send_text_message(self, message: str):
        command = TextPrivateMessage(self._mumble, self.session, message)
        self._mumble.execute_command(command)

    def kick(self, permanent: bool = False, reason: str = ""):
        command = RemoveUser(self.session, reason=reason, ban=permanent)
        self._mumble.execute_command(command)

    def ban(self, reason: str = ""):
        self.kick(True, reason)

    def add_listening_channel(self, channel: Channel):
        command = ModUserState(self.session, listening_channel_add=[channel.id])
        self._mumble.execute_command(command)

    def remove_listening_channel(self, channel: Channel):
        command = ModUserState(self.session, listening_channel_remove=[channel.id])
        self._mumble.execute_command(command)


class Users(dict[int, User]):
    def __init__(self, mumble: Mumble, callbacks: Callbacks):
        super().__init__()
        self.myself: User | None = None
        self._mumble = mumble
        self._myself_session = None
        self._lock = Lock()
        self._callbacks = callbacks

    def handle_update(self, packet: UserState):
        self._lock.acquire()
        try:
            user = self[packet.session]
            actions = user.update(packet)
            self._callbacks.on_user_update(user, actions)
        except KeyError:
            user = User(self._mumble, self._callbacks, packet)
            self[packet.session] = user
            if packet.session != self._myself_session:
                self._callbacks.on_user_created(user)
            else:
                self.myself = user
        self._lock.release()

    def remove(self, packet: UserRemove):
        self._lock.acquire()
        try:
            user = self[packet.session]
            actor = self[packet.actor]
            del self[packet.session]
            self._callbacks.on_user_removed(user, actor, packet.ban, packet.reason)
        except KeyError:
            pass
        self._lock.release()

    def set_myself(self, session: int):
        self._myself_session = session
        try:
            self.myself = self[session]
        except KeyError:
            pass

    def count(self):
        return len(self)