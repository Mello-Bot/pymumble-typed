from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from logging import Logger

from time import time

from pymumble_typed.sound import AudioType


class OpusPacket:
    def __init__(self, data: bytes, sequence: int, target: int, timestamp: float = time()):
        self.data = data
        self.sequence = sequence
        self.target = target
        self.timestamp = timestamp


class Audio:
    def __init__(self, callback: Callable[[OpusPacket], None], logger: Logger):
        super().__init__(logger)
        self._start_sequence = None
        self._start_time = time()
        self._callback = callback
        self._logger = logger

    def add(self, audio: bytes, sequence: int, _type: AudioType, target: int):
        if _type != AudioType.OPUS:
            self._logger.warning(f"Received unsupported audio format {_type.name}")
            return
        self._callback(OpusPacket(audio, sequence, target))
