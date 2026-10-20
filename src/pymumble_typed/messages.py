from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pymumble_typed.channels import Channel
    from pymumble_typed.mumble import Mumble
    from pymumble_typed.protobuf import TextMessage
    from pymumble_typed.users import User


class TextTooLongError(Exception):
    def __init__(self, current: int, max_value: int):
        self._current = current
        self._max_value = max_value

    def __str__(self):
        return f"Current Text length: {self._current}\nMax Text Length: {self._max_value}"


class ImageTooBigError(TextTooLongError):
    def __init__(self, current: int, max_value: int):
        super().__init__(current, max_value)


class Message:
    def __init__(self, mumble: Mumble, message: TextMessage):
        try:
            self.author: User | None = mumble.users[message.actor]
        except KeyError:
            self.author: User | None = None
        # Targets as sent by the server: sessions addressed directly (a private message), channels, and channel trees
        # (a recursive message). Targets unknown to the local state are left out.
        self.sessions: list[int] = list(message.session)
        self.channels: list[Channel] = [
            mumble.channels[channel_id] for channel_id in message.channel_id if channel_id in mumble.channels
        ]
        self.trees: list[Channel] = [
            mumble.channels[tree_id] for tree_id in message.tree_id if tree_id in mumble.channels
        ]
        self.channel: Channel | None = self.channels[0] if self.channels else None
        self.content: str = message.message
