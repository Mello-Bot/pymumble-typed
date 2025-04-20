from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from logging import Logger

from pymumble_typed.sound import SAMPLE_RATE, AudioType, SEQUENCE_DURATION
from pymumble_typed.sound.decoder import Decoder

from time import time


class SoundChunk:
    def __init__(self, pcm, sequence, calculated_time, _type, target, timestamp: float = time()):
        self.time = calculated_time
        self.pcm = pcm
        self.sequence = sequence
        self.duration = float(len(pcm)) / 2 / SAMPLE_RATE
        self.type = _type
        self.target = target
        self.timestamp = timestamp

    def extract_sound(self, duration: float):
        size = int(duration * 2 * SAMPLE_RATE)
        result = SoundChunk(
            self.pcm[:size],
            self.sequence,
            self.time,
            self.type,
            self.target,
            self.timestamp
        )
        self.pcm = self.pcm[size:]
        self.duration -= duration
        self.time += duration
        return result


class SoundQueue:
    def __init__(self, logger: Logger):
        self._logger = logger

    def add(self, audio: bytes, sequence: int, _type: AudioType, target: int):
        pass


class LegacySoundQueue(SoundQueue):
    def __init__(self, callback: Callable[[SoundChunk], None], logger: Logger):
        super().__init__(logger)
        self._start_sequence = None
        self._start_time = time()
        self._decoder = Decoder(self._on_decoded, logger)
        self._callback = callback
        self._logger = logger

    def add(self, audio: bytes, sequence: int, _type: AudioType, target: int):
        if _type != AudioType.OPUS:
            self._logger.warning(f"Received unsupported audio format {_type.name}")
            return
        self._decoder.decode(audio, sequence, _type, target)

    def _on_decoded(self, data: (bytes, int, AudioType, int)):
        pcm, sequence, _type, target = data
        self._logger.debug(f"LegacySoundQueue: decoded audio {len(pcm)}")
        if not self._start_sequence or sequence <= self._start_sequence:
            self._start_time = time()
            self._start_sequence = sequence
            calculated_time = self._start_time
        else:
            calculated_time = self._start_time + (sequence - self._start_sequence) * SEQUENCE_DURATION
        sound = SoundChunk(pcm, sequence, calculated_time, _type, target)
        self._callback(sound)

