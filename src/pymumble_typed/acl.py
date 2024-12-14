from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pymumble_typed.protobuf import (ACL as ACLPacket)
    from pymumble_typed.mumble import Mumble

from threading import Lock


class ChannelGroup:
    def __init__(self, group: ACLPacket.ChanGroup):
        self.name = group.name
        self.inherited = group.inherited
        self.inherit = group.inherit
        self.inheritable = group.inheritable
        self.add: list[int] = list([add for add in group.add])
        self.remove: list[int] = list([remove for remove in group.remove])
        self.inherited_members: list[int] = list([member for member in group.inherited_members])

    def update(self, packet: ACLPacket.ChanGroup):
        self.name = packet.name

        if packet.HasField("inherit"):
            self.inherit = packet.inherit
        if packet.HasField("inherited"):
            self.inherited = packet.inherited
        if packet.HasField("inheritable"):
            self.inheritable = packet.inheritable

        if packet.add:
            self.add: list[int] = list([add for add in packet.add])
        if packet.remove:
            self.remove: list[int] = list([remove for remove in packet.remove])
        if packet.inherited_members:
            self.inherited_members: list[int] = list([member for member in packet.inherited_members])


class ChannelACL:
    def __init__(self, acl: ACLPacket.ChanACL):
        self.apply_here: bool = acl.apply_here
        self.apply_subs: bool = acl.apply_subs
        self.inherited: bool = acl.inherited
        self.user_id: int = acl.user_id
        self.group: str = acl.group
        self.grant: int = acl.grant
        self.deny: int = acl.deny

    def update(self, acl: ACLPacket.ChanACL):
        if acl.HasField("apply_here"):
            self.apply_here = acl.apply_here
        if acl.HasField("apply_subs"):
            self.apply_subs = acl.apply_subs
        if acl.HasField("inherited"):
            self.inherited = acl.inherited
        if acl.HasField("user_id"):
            self.user_id = acl.user_id
        if acl.HasField("group"):
            self.group = acl.group
        if acl.HasField("grant"):
            self.grant = acl.grant
        if acl.HasField("deny"):
            self.deny = acl.deny


class ACL:
    def __init__(self, mumble: Mumble, channel_id: int):
        self._mumble = mumble
        self._channel_id = channel_id
        self.inherit_acls = False
        self.groups = {}
        self.acls = {}
        self._lock = Lock()

    def update(self, packet: ACLPacket):
        self._lock.acquire()
        self.inherit_acls = bool(packet.inherit_acls)
        for group in packet.groups:
            try:
                self.groups[group.name].update(group)
            except KeyError:
                self.groups[group.name] = ChannelGroup(group)

        for acl in packet.acls:
            try:
                self.acls[acl.group].update(acl)
            except KeyError:
                self.groups[acl.group] = ChannelACL(acl)
        self._lock.release()
