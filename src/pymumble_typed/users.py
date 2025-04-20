from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pymumble_typed.blobs import BlobDB
    from pymumble_typed.channels import Channel
    from pymumble_typed.mumble import Mumble
    from pymumble_typed.protobuf.Mumble_pb2 import UserState, UserRemove

from threading import Lock

from pymumble_typed.sound.soundqueue import LegacySoundQueue
from pymumble_typed.commands import ModUserState, Move, TextPrivateMessage, RemoveUser, RequestBlobCmd


class User:
    def __init__(self, mumble: Mumble, blob: BlobDB, packet: UserState):
        self.sound = LegacySoundQueue(lambda sound: mumble.callbacks.dispatch("on_sound_received", self, sound),
                                      mumble.logger)
        self._mumble: Mumble = mumble
        self._blob = blob
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
        self.is_recording = packet.recording

        self._comment_hash = packet.comment_hash
        self.comment = packet.comment
        if not (packet.HasField("comment") or packet.HasField("comment_hash")):
            self._blob.update_user_comment(self.hash, "", "")
        elif self._blob.is_user_comment_updated(self.hash, self._comment_hash.hex()):
            self.comment = self._blob.get_user_comment(self.hash)

        self._texture_hash = packet.texture_hash
        self.texture = packet.texture
        if not (packet.HasField("texture") or packet.HasField("texture_hash")):
            self._blob.update_user_comment(self.hash, "", "")
        elif self._blob.is_user_texture_updated(self.hash, self._texture_hash.hex()):
            self.texture = self._blob.get_user_texture(self.hash)
        self._users = self._mumble.users
        if self._mumble.ready:
            self.request_comment()
            self.request_texture()

    @property
    def avatar_hash(self) -> bytes:
        return self._texture_hash

    @property
    def texture_hash(self) -> bytes:
        return self._texture_hash

    @property
    def comment_hash(self) -> bytes:
        return self._comment_hash

    @property
    def avatar(self):
        return self.texture

    def needs_update(self):
        return not (self.is_comment_updated() and self.is_avatar_updated())

    def is_comment_updated(self):
        return ((not self.comment) == (not self._comment_hash)) or self._blob.is_user_comment_updated(self.hash,
                                                                                                      self._comment_hash.hex())

    def is_avatar_updated(self):
        return ((not self.texture) == (not self._texture_hash)) or self._blob.is_user_texture_updated(self.hash,
                                                                                                      self._texture_hash.hex())

    def request_comment(self):
        if not self._comment_hash:
            return
        if self._mumble.blob_greedy_update and not self.is_comment_updated():
            self._update_comment()
        else:
            self.comment = self._blob.get_user_comment(self.hash)

    def request_texture(self):
        if not self._texture_hash:
            return
        if self._mumble.blob_greedy_update and not self.is_avatar_updated():
            self._update_texture()
        else:
            self.texture = self._blob.get_user_texture(self.hash)

    def myself(self):
        return self._users.myself.session == self.session

    def update(self, packet: UserState):
        actions = {}
        if packet.HasField("channel_id") and self.channel_id != packet.channel_id:
            actions["channel_id"] = self.channel_id
            self.channel_id: int = packet.channel_id
        if packet.HasField("name") and self.name != packet.name:
            actions["name"] = self.name
            self.name = packet.name
        if packet.HasField("priority_speaker") and self.priority_speaker != packet.priority_speaker:
            actions["priority_speaker"] = self.priority_speaker
            self.priority_speaker = packet.priority_speaker
        if packet.HasField("mute") and self.muted != packet.mute:
            actions["mute"] = self.muted
            self.muted = packet.mute
        if packet.HasField("self_mute") and self.self_muted != packet.self_mute:
            actions["self_mute"] = self.self_muted
            self.self_muted = packet.self_mute
        if packet.HasField("deaf") and self.deaf != packet.deaf:
            actions["deaf"] = self.deaf
            self.deaf = packet.deaf
        if packet.HasField("self_deaf") and self.self_deaf != packet.self_deaf:
            actions["self_deaf"] = self.self_deaf
            self.self_deaf = packet.self_deaf
        if packet.HasField("suppress") and self.suppressed != packet.suppress:
            actions["suppress"] = self.suppressed
            self.suppressed = packet.suppress
        if packet.HasField("comment_hash"):
            self._comment_hash = packet.comment_hash
            self.request_comment()
            return None
        if packet.HasField("comment"):
            actions["comment"] = self.comment
            self.comment = packet.comment
            if not self.comment:
                self._comment_hash = b''
                self._blob.update_user_comment(self.hash, self._comment_hash.hex(), self.comment)
            if self._comment_hash:
                self._blob.update_user_comment(self.hash, self._comment_hash.hex(), self.comment)
        if packet.HasField("texture_hash"):
            self._texture_hash = packet.texture_hash
            self.request_texture()
            return None
        if packet.HasField("texture"):
            actions["texture"] = self.texture
            actions["avatar"] = self.texture
            self.texture = packet.texture
            if not self.texture:
                self._texture_hash = b''
                self._blob.update_user_texture(self.hash, self._texture_hash.hex(), self.texture)
            if self._texture_hash:
                self._blob.update_user_texture(self.hash, self._texture_hash.hex(), self.texture)

        return actions

    def channel(self):
        return self._mumble.channels[self.channel_id]

    def _update_comment(self):
        if not self._comment_hash:
            return
        cmd = RequestBlobCmd(user_comment_hashes=[self.session])
        self._mumble.execute_command(cmd, False)

    def _update_texture(self):
        if not self._texture_hash:
            return
        cmd = RequestBlobCmd(user_texture_hashes=[self.session])
        self._mumble.execute_command(cmd, False)

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

    def set_comment(self, comment: str):
        command = ModUserState(self.session, comment=comment)
        self._mumble.execute_command(command)

    def set_texture(self, texture: str):
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
    def __init__(self, mumble: Mumble, blob: BlobDB):
        super().__init__()
        self.myself: User | None = None
        self._mumble = mumble
        self._blob = blob
        self._myself_session = None
        self._lock = Lock()
        self._logger = mumble.logger.getChild(self.__class__.__name__)

    def handle_update(self, packet: UserState):
        with self._lock:
            try:
                user = self[packet.session]
                # FIXME: packet.session should be removed and a null actor passed.
                #  It's currently reported back as a self-update to avoid breaking changes
                actor = self[packet.actor or packet.session]
                before = user.update(packet)
                # Avoid calling callback if no modification has been registered (like for hashes)
                if self._mumble.blob_greedy_update and not before:
                    return
                self._mumble.callbacks.dispatch("on_user_updated", user, actor, before)
            except KeyError:
                user = User(self._mumble, self._blob, packet)
                self[packet.session] = user
                if packet.session != self._myself_session:
                    self._mumble.callbacks.dispatch("on_user_created", user)
                else:
                    self.myself = user

    def remove(self, packet: UserRemove):
        with self._lock:
            try:
                user = self[packet.session]
                try:
                    actor = self[packet.actor]
                except KeyError:
                    actor = user
                del self[packet.session]
                self._mumble.callbacks.dispatch("on_user_removed", user, actor, packet.ban, packet.reason)
            except KeyError:
                self._logger.warning(f"cannot remove user {packet.session}: user do not exist")

    def set_myself(self, session: int):
        self._myself_session = session
        try:
            self.myself = self[session]
        except KeyError:
            pass

    def count(self):
        return len(self)
