from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from concurrent.futures import Future

    from pymumble_typed.blobs import BlobDB
    from pymumble_typed.channels import Channel
    from pymumble_typed.mumble import Mumble
    from pymumble_typed.protobuf.Mumble_pb2 import UserRemove, UserState

from contextlib import suppress
from threading import Lock

from pymumble_typed.commands import ModUserState, Move, RemoveUser, RequestBlobCmd, TextPrivateMessage


class User:
    def __init__(self, mumble: Mumble, blob: BlobDB, packet: UserState):
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
        return ((not self.comment) == (not self._comment_hash)) or self._blob.is_user_comment_updated(
            self.hash, self._comment_hash.hex()
        )

    def is_avatar_updated(self):
        return ((not self.texture) == (not self._texture_hash)) or self._blob.is_user_texture_updated(
            self.hash, self._texture_hash.hex()
        )

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

    def get_avatar(self) -> Future[bytes]:
        """
        Fetch the user's avatar (Mumble calls it the "texture") and return a Future
        with the bytes. If the avatar is unset or already cached in BlobDB the Future is
        resolved immediately; otherwise a RequestBlob is sent and the Future resolves when
        the server delivers the data in a UserState.
        """
        if self._texture_hash and not self._blob.is_user_texture_updated(self.hash, self._texture_hash.hex()):
            return self._mumble._await_blob(
                "texture", self.session, RequestBlobCmd(user_texture_hashes=[self.session])
            )
        if self._texture_hash:
            self.texture = self._blob.get_user_texture(self.hash)
        return self._mumble._resolved_future(self.texture)

    def get_description(self) -> Future[str]:
        """
        Fetch the user's description (Mumble calls it the "comment") and return a Future
        with the string. Resolved immediately if unset or already cached, otherwise when
        the server delivers it in a UserState.
        """
        if self._comment_hash and not self._blob.is_user_comment_updated(self.hash, self._comment_hash.hex()):
            return self._mumble._await_blob(
                "comment", self.session, RequestBlobCmd(user_comment_hashes=[self.session])
            )
        if self._comment_hash:
            self.comment = self._blob.get_user_comment(self.hash)
        return self._mumble._resolved_future(self.comment)

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
                self._comment_hash = b""
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
                self._texture_hash = b""
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

    def mute(self, myself: bool = False, action: bool = True) -> Future[User]:
        if self.myself() and myself:
            command = ModUserState(self.session, self_mute=action)
        else:
            command = ModUserState(self.session, mute=action)
        return self._mumble.execute_command(command)

    def unmute(self, myself: bool = False) -> Future[User]:
        return self.mute(myself, False)

    def deafen(self, myself: bool = False, action: bool = True) -> Future[User]:
        if self.myself() and myself:
            command = ModUserState(self.session, self_deaf=action)
        else:
            command = ModUserState(self.session, deaf=action)
        return self._mumble.execute_command(command)

    def undeafen(self, myself: bool = False) -> Future[User]:
        return self.deafen(myself, False)

    def suppress(self, action: bool = True) -> Future[User]:
        command = ModUserState(self.session, suppress=action)
        return self._mumble.execute_command(command)

    def unsuppress(self) -> Future[User]:
        return self.suppress(False)

    def recording(self, action: bool = True) -> Future[User]:
        command = ModUserState(self.session, recording=action)
        return self._mumble.execute_command(command)

    def unrecording(self) -> Future[User]:
        return self.recording(False)

    def set_comment(self, comment: str) -> Future[User]:
        command = ModUserState(self.session, comment=comment)
        return self._mumble.execute_command(command)

    def set_texture(self, texture: str) -> Future[User]:
        command = ModUserState(self.session, texture=texture)
        return self._mumble.execute_command(command)

    def register(self) -> Future[User]:  # TODO(nico9889): check if this is correct
        command = ModUserState(self.session, user_id=0)
        return self._mumble.execute_command(command)

    def update_context(self, context_name: bytes) -> Future[User]:
        command = ModUserState(self.session, plugin_context=context_name)
        return self._mumble.execute_command(command)

    def move_in(self, channel: Channel, token: str | None = None) -> Future[User]:
        if token:
            self._mumble.reauthenticate(token)
        command = Move(self.session, channel.id)
        return self._mumble.execute_command(command)

    def send_text_message(self, message: str) -> Future[bool]:
        # Text messages are not echoed by the server: fire-and-forget, resolves to True.
        command = TextPrivateMessage(self._mumble, self.session, message)
        return self._mumble.execute_command(command)

    def kick(self, permanent: bool = False, reason: str = "") -> Future[bool]:
        # Resolves to True once the server confirms the UserRemove.
        command = RemoveUser(self.session, reason=reason, ban=permanent)
        return self._mumble.execute_command(command)

    def ban(self, reason: str = "") -> Future[bool]:
        return self.kick(True, reason)

    def add_listening_channel(self, channel: Channel) -> Future[User]:
        command = ModUserState(self.session, listening_channel_add=[channel.id])
        return self._mumble.execute_command(command)

    def remove_listening_channel(self, channel: Channel) -> Future[User]:
        command = ModUserState(self.session, listening_channel_remove=[channel.id])
        return self._mumble.execute_command(command)

    def __eq__(self, other: User):
        return self.hash == other.hash

    def __gt__(self, other: User):
        return self.session > other.session

    def __lt__(self, other: User):
        return self.session < other.session

    def __str__(self):
        return str(
            {
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
                "texture": self.texture,
            }
        )


class Users(dict[int, User]):
    def __init__(self, mumble: Mumble, blob: BlobDB):
        super().__init__()
        self._myself: User | None = None
        self._mumble = mumble
        self._blob = blob
        self._myself_session = None
        self._lock = Lock()
        self._logger = mumble.logger.getChild(self.__class__.__name__)

    @property
    def myself(self):
        if not self._myself:
            raise RuntimeError("Initialization error: missing bot user")
        return self._myself

    def handle_update(self, packet: UserState):
        with self._lock:
            try:
                user = self[packet.session]
            except KeyError:
                user = User(self._mumble, self._blob, packet)
                self[packet.session] = user
                if packet.session != self._myself_session:
                    self._mumble.callbacks.dispatch("on_user_created", user)
                else:
                    self._myself = user
                return
            # FIXME(nico9889): packet.session should be removed and a null actor passed.
            #  It's currently reported back as a self-update to avoid breaking changes
            try:
                actor = self[packet.actor or packet.session]
            except KeyError:
                # An unknown actor (e.g. one that already left) must not be mistaken for a
                # missing user and re-route this update into the creation branch.
                actor = user
            before = user.update(packet)
            # Avoid calling callback if no modification has been registered (like for hashes)
            if self._mumble.blob_greedy_update and not before:
                return
            self._mumble.callbacks.dispatch("on_user_updated", user, actor, before)

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
        with suppress(KeyError):
            self._myself = self[session]

    def count(self):
        return len(self)
