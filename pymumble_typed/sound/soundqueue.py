from __future__ import annotations

from threading import Lock
from typing import TYPE_CHECKING

from opuslib import Decoder

from pymumble_typed.sound import SAMPLE_RATE, AudioType, READ_BUFFER_SIZE, SEQUENCE_DURATION


if TYPE_CHECKING:
    from pymumble_typed.mumble import Mumble

from collections import deque

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
    def __init__(self, mumble: Mumble):
        self._mumble = mumble
        self._queue: deque[SoundChunk] = deque()
        self._start_sequence = None
        self._start_time = time()
        self._lock = Lock()
        self.decoders = {
            AudioType.OPUS: Decoder(SAMPLE_RATE, 1)
        }

    def add(self, audio, sequence, _type: AudioType, target):
        if not self._mumble.sound_receive:
            return None

        self._lock.acquire()
        try:
            pcm = self.decoders[_type].decode(audio, READ_BUFFER_SIZE)
            if not self._start_sequence or sequence <= self._start_sequence:
                self._start_time = time()
                self._start_sequence = sequence
                calculated_time = self._start_time
            else:
                calculated_time = self._start_time + (sequence - self._start_sequence) * SEQUENCE_DURATION

            sound = SoundChunk(pcm, sequence, calculated_time, _type, target)
            return sound
        except KeyError:
            self._mumble.logger.error("Invalid decoder")
        except Exception:
            self._mumble.logger.error("Error while decoding audio", exc_info=True)
        finally:
            self._lock.release()

    def has_sound(self):
        return len(self._queue) > 0

    def get_sound(self, duration: float = None):
        self._lock.acquire()
        result = None
        if self.has_sound():
            if duration is None or self.pop().duration <= duration:
                result = self._queue.pop()
            else:
                result = self.pop().extract_sound(duration)
        self._lock.release()
        return result

    def pop(self):
        try:
            return self._queue.pop()
        except IndexError:
            return None
