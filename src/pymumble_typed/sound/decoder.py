from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from logging import Logger

    from pymumble_typed.sound import AudioType

from multiprocessing.pool import ThreadPool
from threading import current_thread

from opuslib import Decoder as OpusDecoder

from pymumble_typed.sound import READ_BUFFER_SIZE, SAMPLE_RATE

decoder: OpusDecoder = OpusDecoder(SAMPLE_RATE, 2)


def initializer():
    global decoder
    thread = current_thread()
    thread.name = f"VoiceDecoder[{thread.ident}]"
    decoder = OpusDecoder(SAMPLE_RATE, 2)


def decode(data: bytes, sequence: int, _type: AudioType, target: int) -> tuple[bytes, int, AudioType, int]:
    global decoder
    decoded = decoder.decode(data, READ_BUFFER_SIZE)
    return decoded, sequence, _type, target


class Decoder:
    def __init__(self, on_decoded: Callable[[(bytes, int, AudioType, int)], None], logger: Logger):
        self._pool = ThreadPool(processes=1, initializer=initializer)
        self._on_decoded = on_decoded
        self._logger = logger

    def decode(self, data: bytes, sequence: int, _type: AudioType, target: int):
        self._pool.apply_async(decode, [data, sequence, _type, target], callback=self._on_decoded)
        # print(self._pool.size)

    def _error_cb(self, *_):
        self._logger.error("Error while decoding audio")
