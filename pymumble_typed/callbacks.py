from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from pymumble_typed.users import User
    from pymumble_typed.messages import Message
    from pymumble_typed.channels import Channel


class Callbacks:
    def on_connect(self):
        pass

    def on_disconnect(self):
        pass

    def on_channel_created(self, channel: Channel):
        pass

    def on_channel_updated(self, channel: Channel, actions: dict):
        pass

    def on_channel_removed(self, channel: Channel):
        pass

    def on_user_created(self, user: User):
        pass

    def on_user_update(self, user: User, actions: dict):
        pass

    def on_user_removed(self, user: User, actor: User, ban: bool, reason: str):
        pass

    def on_sound_received(self, user: User, chunk: bytes):
        pass

    def on_message(self, message: Message):
        pass

    def on_context_action(self):
        pass

    def on_acl_received(self):
        pass

    def on_permission_denied(self, session: int, channel_id: int, name: str, _type: str, reason: str):
        pass




