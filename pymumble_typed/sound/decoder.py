from logging import Logger
from multiprocessing import Process, Queue
from threading import Thread
from typing import Callable

from opuslib import Decoder as OpusDecoder, OpusError

from pymumble_typed.sound import SAMPLE_RATE, READ_BUFFER_SIZE, AudioType


def decode(logger: Logger, input_queue: Queue,
           output_queue: Queue):
    decoder = OpusDecoder(SAMPLE_RATE, 2)
    alive = True
    while alive:
        try:
            data, sequence, _type, target = input_queue.get(block=True, timeout=None)
            # FIXME: READ_BUFFER_SIZE?
            try:
                decoded = decoder.decode(data, READ_BUFFER_SIZE)
                output_queue.put((decoded, sequence, _type, target))
            except OpusError:
                logger.error("Error while decoding audio")
        except KeyboardInterrupt:
            alive = False


class Decoder(Thread):
    def __init__(self, on_decoded: Callable[[bytes, int, AudioType, int], None], logger: Logger):
        super().__init__(name="Decoder")
        self._input_queue: Queue[(bytes, int, AudioType, int)] = Queue()
        self._output_queue: Queue[(bytes, int, AudioType, int)] = Queue()
        self._process = Process(target=decode, args=[logger, self._input_queue, self._output_queue])
        self.alive = True
        self._on_decoded = on_decoded
        self.start()
        self._process.start()

    def decode(self, data: bytes, sequence: int, _type: AudioType, target: int):
        self._input_queue.put((data, sequence, _type, target), block=True)

    def run(self):
        while self.alive:
            pcm, sequence, _type, target = self._output_queue.get()
            self._on_decoded(pcm, sequence, _type, target)

    def __del__(self):
        self.alive = False
        self._process.kill()
