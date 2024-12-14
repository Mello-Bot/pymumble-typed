from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.pymumble_typed.mumble import Mumble
    from src.pymumble_typed.users import User
    from src.pymumble_typed.channels import Channel
    from src.pymumble_typed.protobuf import TextMessage


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
        try:
            self.channel: Channel | None = mumble.channels[message.channel_id.pop()]
        except KeyError:
            self.channel: Channel | None = None
        except IndexError:
            self.channel = None
        self.content: str = message.message
