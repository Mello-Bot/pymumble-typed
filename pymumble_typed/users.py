from __future__ import annotations

from typing import TYPE_CHECKING

from pymumble_typed.channels import Channel
from pymumble_typed.sound.soundqueue import SoundQueue

if TYPE_CHECKING:
    from pymumble_typed.mumble import Mumble

from struct import unpack
from threading import Lock

from pymumble_typed.Mumble_pb2 import UserState, UserRemove, RequestBlob

from pymumble_typed.commands import ModUserState, Move, TextPrivateMessage, RemoveUser


class User:
    def __init__(self, mumble: Mumble, packet: UserState):
        self.sound = SoundQueue(mumble)
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
        if packet.HasField("channel_id") and self.channel_id != packet.channel_id:
            actions["channel_id"] = packet.channel_id
            self.channel_id: int = packet.channel_id
        if packet.HasField("name") and self.name != packet.name:
            actions["name"] = packet.name
            self.name = packet.name
        if packet.HasField("priority_speaker") and self.priority_speaker != packet.priority_speaker:
            actions["priority_speaker"] = packet.priority_speaker
            self.priority_speaker = packet.priority_speaker
        if packet.HasField("mute") and self.muted != packet.mute:
            actions["mute"] = packet.mute
            self.muted = packet.mute
        if packet.HasField("self_mute") and self.self_muted != packet.self_mute:
            actions["self_mute"] = packet.self_mute
            self.self_muted = packet.self_mute
        if packet.HasField("deaf") and self.deaf != packet.deaf:
            actions["deaf"] = packet.deaf
            self.deaf = packet.deaf
        if packet.HasField("self_deaf") and self.self_deaf != packet.self_deaf:
            actions["self_deaf"] = packet.self_deaf
            self.self_deaf = packet.self_deaf
        if packet.HasField("suppress") and self.suppressed != packet.suppress:
            actions["suppress"] = packet.suppress
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

    def channel(self):
        return self._mumble.channels[self.channel_id]

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
            self._mumble.reauthenticate(token)
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

    def __eq__(self, other: User):
        return self.hash == other.hash

    def __gt__(self, other: User):
        return self.session > other.session

    def __lt__(self, other: User):
        return self.session < other.session

    def __str__(self):
        return str({
            "hash": self.hash,
            "session": self.session,
            "name": self.name,
            "priority_speaker": self.priority_speaker,
            "channel_id": self.channel_id,
            "muted": self.muted,
            "self_muted": self.self_muted,
            "deaf": self.deaf,
            "self_deaf": self.self_deaf,
            "suppressed": self.suppressed,
            "comment": self.comment,
            "texture": self.texture
        })


class Users(dict[int, User]):
    def __init__(self, mumble: Mumble):
        super().__init__()
        self.myself: User | None = None
        self._mumble = mumble
        self._myself_session = None
        self._lock = Lock()

    def handle_update(self, packet: UserState):
        self._lock.acquire()
        try:
            user = self[packet.session]
            actor = self[packet.actor]
            actions = user.update(packet)
            self._mumble.callbacks.on_user_updated(user, actor, actions)
        except KeyError:
            user = User(self._mumble, packet)
            self[packet.session] = user
            if packet.session != self._myself_session:
                self._mumble.callbacks.on_user_created(user)
            else:
                self.myself = user
        self._lock.release()

    def remove(self, packet: UserRemove):
        self._lock.acquire()
        try:
            user = self[packet.session]
            actor = self[packet.actor]
            del self[packet.session]
            self._mumble.callbacks.on_user_removed(user, actor, packet.ban, packet.reason)
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
