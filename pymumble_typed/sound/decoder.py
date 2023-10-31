from logging import Logger
from multiprocessing import cpu_count
from multiprocessing.pool import ThreadPool

from typing import Callable

from opuslib import Decoder as OpusDecoder

from pymumble_typed.sound import SAMPLE_RATE, READ_BUFFER_SIZE, AudioType

decoder: OpusDecoder = None


def initializer():
    global decoder
    decoder = OpusDecoder(SAMPLE_RATE, 2)


def decode(data: bytes, sequence: int, _type: AudioType, target: int) -> (bytes, int, AudioType, int):
    decoded = decoder.decode(data, READ_BUFFER_SIZE)
    return decoded, sequence, _type, target


class Decoder:
    def __init__(self, on_decoded: Callable[[(bytes, int, AudioType, int)], None], logger: Logger):
        self._pool = ThreadPool(processes=cpu_count() - 1, initializer=initializer)
        self._on_decoded = on_decoded
        self._logger = logger

    def decode(self, data: bytes, sequence: int, _type: AudioType, target: int):
        self._pool.apply_async(decode, [data, sequence, _type, target], callback=self._on_decoded)

    def _error_cb(self, *_):
        self._logger.error("Error while decoding audio")
