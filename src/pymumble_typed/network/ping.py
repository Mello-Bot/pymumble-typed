from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from asyncio import BaseEventLoop
    from pymumble_typed.network.control import ControlStack, Status

from time import time

from pymumble_typed import MessageType
from pymumble_typed.protobuf.Mumble_pb2 import Ping as PingPacket
from pymumble_typed.utils.timer import AsyncTimer

class Ping(AsyncTimer):
    DELAY = 10

    def __init__(self, control: ControlStack, loop: BaseEventLoop):
        super().__init__(Ping.DELAY, self.send, loop=loop)
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

    async def send(self):
        packet = PingPacket()
        packet.timestamp = int(time())
        packet.tcp_ping_avg = self.average
        packet.tcp_ping_var = self.variance
        packet.tcp_packets = self.number
        packet.udp_packets = self.udp_packets
        packet.udp_ping_avg = self.udp_ping_average
        packet.udp_ping_var = self.udp_ping_variance
        packet.good = self.udp_good
        packet.late = self.udp_late
        packet.lost = self.udp_lost
        self.time_send = int(time() * 1000)
        self.last = time()
        await self._control.send_message(MessageType.PingPacket, packet)
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
