from __future__ import annotations

from threading import Timer
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from asyncio import AbstractEventLoop
    from pymumble_typed.network.control import ControlStack, Status

from time import time
from asyncio import run_coroutine_threadsafe
from pymumble_typed import MessageType
from pymumble_typed.protobuf.Mumble_pb2 import Ping as PingPacket
from pymumble_typed.commands import Ping as PingCommand

class Ping(Timer):
    DELAY = 10

    def __init__(self, control: ControlStack, loop: AbstractEventLoop):
        super().__init__(Ping.DELAY, self.send)
        self.last_receive = 0.
        self.time_send = 0.
        self.number = 1
        self.average = 0.
        self.variance = 0.
        self.udp_packets: int = 0
        self.udp_ping_average: float = 0.
        self.udp_ping_variance: float = 0.
        self.udp_good: int = 0
        self.udp_late: int = 0
        self.udp_lost: int = 0
        self.last = 0
        self._control = control
        self._loop = loop
        self._logger = self._control.logger.getChild("Ping")

    def send(self):
        self._logger.debug("Sending ping")
        cmd = PingCommand(
            self.average,
            self.variance,
            self.number,
            self.udp_packets,
            self.udp_ping_average,
            self.udp_ping_variance,
            self.udp_good,
            self.udp_late,
            self.udp_lost
        )
        self.time_send = int(time() * 1000)
        self.last = time()
        self._control.logger.debug("Sending ping")
        run_coroutine_threadsafe(self._control.enqueue_command(cmd), self._loop)
        if self.last_receive != 0 and time() > self.last_receive + 60:
            self._control.status = Status.NOT_CONNECTED
        return True

    def receive(self, _: PingPacket):
        self.last_receive = int(time() * 1000)
        ping = self.last_receive - self.time_send
        old_average = self.average
        number = self.number
        new_average = ((self.average * number) + ping) / (self.number + 1)
        self.variance = self.variance + pow(old_average - new_average, 2) + (1 / self.number) * pow(ping - new_average,
                                                                                                    2)
        self.average = new_average
        self.number += 1
