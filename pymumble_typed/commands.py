from __future__ import annotations

from collections import deque
from threading import Lock

from google.protobuf.message import Message

from pymumble_typed.Mumble_pb2 import UserState, TextMessage as TextMessagePacket, ChannelState, ChannelRemove, \
    VoiceTarget as VoiceTargetPacket, UserRemove, ACL


class Command:
    def __init__(self):
        self.id = None
        self.lock = Lock()
        self.response = None
        self.packet: Message | None = None


class Move(Command):
    def __init__(self, session: int, channel_id: int):
        super().__init__()
        self.packet = UserState()
        self.packet.session = session
        self.packet.channel_id = channel_id


class TextMessage(Command):
    def __init__(self, session: int, channel_id: int, message: str):
        super().__init__()
        self.packet = TextMessagePacket()
        self.packet.session.append(session)
        self.packet.channel_id.append(channel_id)
        self.packet.message = message


class TextPrivateMessage(Command):
    def __init__(self, session: int, message: str):
        super().__init__()
        self.packet = TextMessagePacket()
        self.packet.session.append(session)
        self.packet.message.append(message)


class ModUserState(Command):
    def __init__(self, session: int, mute: bool | None = None, self_mute: bool | None = None, deaf: bool | None = None,
                 self_deaf: bool | None = None, suppress: bool | None = None, recording: bool | None = None,
                 comment: str | None = None, texture: str | None = None, user_id: int | None = None,
                 plugin_context: int | None = None, listening_channel_add: list[int] | None = None,
                 listening_channel_remove: list[int] | None = None):
        super().__init__()
        self.packet = UserState()
        self.packet.session = session

        if mute is not None:
            self.packet.mute = mute
        if self_mute is not None:
            self.packet.self_mute = self_mute
        if deaf is not None:
            self.packet.deaf = deaf
        if self_deaf is not None:
            self.packet.self_deaf = self_deaf
        if suppress is not None:
            self.packet.suppress = suppress
        if recording is not None:
            self.packet.recording = recording
        if comment is not None:
            self.packet.comment = comment
        if texture is not None:
            self.packet.texture = texture
        if user_id is not None:
            self.packet.user_id = user_id
        if plugin_context is not None:
            self.packet.plugin_context = plugin_context
        if listening_channel_add is not None:
            self.packet.listening_channel_add.extend(listening_channel_add)
        if listening_channel_remove is not None:
            self.packet.listening_channel_remove.extend(listening_channel_remove)


class RemoveUser(Command):
    def __init__(self, session: int, reason: str | None, ban: bool | None):
        super().__init__()
        self.packet = UserRemove()
        self.packet.session = session
        self.packet.reason = reason
        self.packet.ban = ban


class CreateChannel(Command):
    def __init__(self, parent: int, name: str, temporary: bool):
        super().__init__()
        self.packet = ChannelState()
        self.packet.parent = parent
        self.packet.name = name
        self.packet.temporary = temporary


class RemoveChannel(Command):
    def __init__(self, channel_id: int):
        super().__init__()
        self.packet = ChannelRemove()
        self.packet.channel_id = channel_id


class UpdateChannel(Command):
    # FIXME
    def __init__(self, TODO: str):
        super().__init__()
        self.packet = ChannelState()
        # FIXME: set key, values


class VoiceTarget(Command):
    def __init__(self, voice_id: int, targets: list[int]):
        super().__init__()
        self.packet = VoiceTargetPacket()
        self.packet.id = voice_id
        _targets: list[VoiceTargetPacket.Target] = []
        if voice_id == 1:
            target = VoiceTargetPacket.Target()
            target.channel_id = targets[0]
            _targets.append(target)
        else:
            for target in targets:
                target_ = VoiceTargetPacket.Target()
                target_.session.append(target)
                _targets.append(target_)
        self.packet.targets.extend(targets)


class LinkChannel(Command):
    def __init__(self, channel_id: int, add_ids: list[int]):
        super().__init__()
        self.packet = ChannelState()
        self.packet.channel_id = channel_id
        self.packet.links_add.extend(add_ids)


class UnlinkChannel(Command):
    # FIXME
    def __init__(self, channel_id: int, remove_ids: list[int]):
        super().__init__()
        self.packet = ChannelState()
        self.packet.channel_id = channel_id
        self.packet.links_remove.extend(remove_ids)


class QueryACL(Command):
    def __init__(self, channel_id: int):
        super().__init__()
        self.packet = ACL()
        self.packet.channel_id = channel_id
        self.packet.query = True


class ChannelGroup:
    def __init__(self, name: str, inherited: bool | None = None, inherit: bool | None = None,
                 inheritable: bool | None = None, add: list[int] | None = None, remove: list[int] | None = None):
        self.name = name
        self.inherited = inherited
        self.inherit = inherit
        self.inheritable = inheritable
        self.add = add if add is not None else []
        self.remove = remove if add is not None else []


class ChannelACL:
    def __init__(self, apply_here: bool | None = None, apply_subs: bool | None = None, inherited: bool | None = None,
                 user_id: int | None = None, group: str | None = None, grant: int | None = None,
                 deny: int | None = None):
        self.apply_here = apply_here
        self.apply_subs = apply_subs
        self.inherited = inherited
        self.user_id = user_id
        self.group = group
        self.grant = grant
        self.deny = deny


class UpdateACL(Command):
    def __init__(self, channel_id: int, inherit_acls, chan_group: list[ChannelGroup], chan_acl: list[ChannelACL]):
        super().__init__()

        self.packet = ACL()
        self.packet.channel_id = channel_id
        self.packet.inherit_acls = inherit_acls

        for msg_group in chan_group:
            chan_group = ACL.ChanGroup()
            chan_group.name = msg_group.name
            if msg_group.inherited is not None:
                chan_group.inherited = msg_group.inherited
            if msg_group.inherit is not None:
                chan_group.inherit = msg_group.inherit
            if msg_group.inheritable is not None:
                chan_group.inheritable = msg_group.inheritable
            chan_group.add.extend(msg_group.add)
            chan_group.remove.extend(msg_group.remove)

        for msg_acl in chan_acl:
            chan_acl = ACL.ChanACL()
            if msg_acl.apply_here is not None:
                chan_acl.apply_here = msg_acl.apply_here
            if msg_acl.apply_subs is not None:
                chan_acl.apply_subs = msg_acl.apply_subs
            if msg_acl.inherited is not None:
                chan_acl.inherited = msg_acl.inherited
            if msg_acl.user_id is not None:
                chan_acl.user_id = msg_acl.user_id
            if msg_acl.group is not None:
                chan_acl.group = msg_acl.group
            if msg_acl.grant is not None:
                chan_acl.grant = msg_acl.grant
            if msg_acl.deny is not None:
                chan_acl.deny = msg_acl.deny
            if not chan_acl.inherited:
                self.packet.acls.append(chan_acl)
        self.packet.query = False


class CommandQueue:
    def __init__(self):
        self.id = 0
        self.queue = deque()
        self.lock = Lock()

    def push(self, cmd: Command):
        self.lock.acquire()
        self.id += 1
        cmd.cmd_id = self.id
        self.queue.appendleft(cmd)
        cmd.lock.acquire()
        self.lock.release()
        return cmd.lock

    def has_next(self):
        return len(self.queue) > 0

    def pop(self):
        self.lock.acquire()
        try:
            return self.queue.pop()
        except IndexError:
            return None
        finally:
            self.lock.release()

    def answer(self, cmd: Command):
        cmd.lock.release()


