from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pymumble_typed.Mumble_pb2 import ChannelState, RequestBlob
    from pymumble_typed.mumble import Mumble
    from pymumble_typed.callbacks import Callbacks
    from pymumble_typed.users import User

from struct import unpack

from pymumble_typed.acl import ACL
from pymumble_typed.commands import CreateChannel, RemoveChannel, Move, TextMessage, LinkChannel, UnlinkChannel, \
    UpdateChannel, QueryACL

from pymumble_typed.Mumble_pb2 import RequestBlob

from threading import Lock


class Channel:
    def __init__(self, mumble: Mumble, packet: ChannelState):
        self._mumble = mumble
        self.id: int = packet.channel_id
        self.acl: ACL = ACL(mumble, packet.channel_id)
        self.name: str = packet.name
        self._parent: int = packet.parent
        self._description_hash: bytes = packet.description_hash
        self.description: str = ""
        self.temporary: bool = packet.temporary
        self.position = packet.position
        self.max_users = packet.max_users
        self.can_enter = packet.can_enter
        self.is_enter_restricted = packet.is_enter_restricted
        self.links: list[int] = packet.links
        self._get_description()

    def update(self, packet: ChannelState):
        actions = {}

        if packet.HasField("channel_id") and self.id != packet.channel_id:
            actions["id"] = packet.channel_id
            self.id = packet.channel_id
        if packet.HasField("name") and self.name != packet.name:
            actions["name"] = packet.name
            self.name = packet.name
        if packet.HasField("parent") and self._parent != packet.parent:
            actions["parent"] = packet.parent
            self._parent = packet.parent
        if packet.HasField("temporary") and self.temporary != packet.temporary:
            actions["temporary"] = packet.temporary
            self.temporary = packet.temporary
        if packet.HasField("position") and self.position != packet.position:
            actions["position"] = packet.position
            self.position = packet.position
        if packet.HasField("max_users") and self.max_users != packet.max_users:
            actions["max_users"] = packet.max_users
            self.max_users = packet.max_users
        if packet.HasField("can_enter") and self.can_enter != packet.can_enter:
            actions["can_enter"] = packet.can_enter
            self.can_enter = packet.can_enter
        if packet.HasField("is_enter_restricted") and self.is_enter_restricted != packet.is_enter_restricted:
            actions["is_enter_restricted"] = packet.is_enter_restricted
            self.is_enter_restricted = packet.is_enter_restricted
        if packet.HasExtension("links") and self.links != packet.links:
            actions["links"] = packet.links
            self.links = packet.links
        if packet.HasField("description_hash"):
            self._description_hash = packet.description_hash
            if packet.HasField("description"):
                self.description = packet.description
            else:
                self._get_description()
        return actions

    def _get_description(self):
        if not self._description_hash:
            return
        packet = RequestBlob()
        packet.channel_description.extend(unpack("!5I", self._description_hash))
        self._mumble.request_blob(packet)

    @property
    def parent(self) -> Channel | None:
        try:
            return self._mumble.channels[self._parent]
        except KeyError:
            return None

    def get_users(self) -> list[User]:
        return list([user for user in self._mumble.users.values() if user.channel_id == self.id])

    def move_in(self, user: User | None = None):
        if user is None:
            user = self._mumble.users.myself
        command = Move(user.session, self.id)
        self._mumble.execute_command(command)

    def remove(self):
        command = RemoveChannel(self.id)
        self._mumble.execute_command(command)

    def send_text_message(self, message: str):
        command = TextMessage(self._mumble, self._mumble.users.myself.session, channel_id=self.id, message=message)
        self._mumble.execute_command(command)

    def link(self, channels: list[Channel]):
        command = LinkChannel(self.id, add_ids=[channel.id for channel in channels])
        self._mumble.execute_command(command)

    def unlink(self, channels: list[Channel]):
        command = UnlinkChannel(self.id, remove_ids=[channel.id for channel in channels])
        self._mumble.execute_command(command)

    def unlink_all(self):
        command = UnlinkChannel(self.id, remove_ids=[link for link in self.links])
        self._mumble.execute_command(command)

    def rename(self, name: str):
        command = UpdateChannel(self.id, name=name)
        self._mumble.execute_command(command)

    def move(self, parent_id: int):
        command = UpdateChannel(self.id, parent=parent_id)
        self._mumble.execute_command(command)

    def set_position(self, position: int):
        command = UpdateChannel(self.id, position=position)
        self._mumble.execute_command(command)

    def set_max_users(self, max_users: int):
        command = UpdateChannel(self.id, max_users=max_users)
        self._mumble.execute_command(command)

    def set_description(self, description: str):
        command = UpdateChannel(self.id, description=description)
        self._mumble.execute_command(command)

    def request_acl(self):
        command = QueryACL(self.id)
        self._mumble.execute_command(command)

    def update_acl(self, packet):
        self.acl.update(packet)

    def __eq__(self, other: Channel):
        return self.id == other.id

    def __gt__(self, other: Channel):
        return self.id > other.id

    def __lt__(self, other: Channel):
        return self.id < other.id


class Channels(dict[int, Channel]):
    def __init__(self, mumble: Mumble):
        super().__init__()
        self._mumble = mumble
        self._lock = Lock()

    def current(self):
        return self._mumble.users.myself.channel()

    def handle_update(self, packet: ChannelState):
        self._lock.acquire()
        try:
            channel = self[packet.channel_id]
            actions = channel.update(packet)
            self._mumble.callbacks.on_channel_updated(channel, actions)
        except KeyError:
            channel = Channel(self._mumble, packet)
            self[packet.channel_id] = channel
            self._mumble.callbacks.on_channel_created(channel)
        self._lock.release()

    def remove(self, channel_id: int):
        self._lock.acquire()

        try:
            channel = self[channel_id]
            del self[channel_id]
            self._mumble.callbacks.on_channel_removed(channel)
        except KeyError:
            pass
        self._lock.release()

    def new_channel(self, parent_id: int, name: str, temporary: bool = False):
        command = CreateChannel(parent_id, name, temporary)
        self._mumble.execute_command(command)

    def remove_channel(self, channel_id: int):
        command = RemoveChannel(channel_id)
        self._mumble.execute_command(command)
