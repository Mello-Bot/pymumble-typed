from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pymumble_typed.network.control import ControlStack
    from pymumble_typed.network.voice import VoiceStack

from math import sqrt
from threading import Timer
from time import time

from pymumble_typed import MessageType
from pymumble_typed.protobuf.Mumble_pb2 import Ping as PingPacket


class RepeatTimer(Timer):
    def run(self):
        while not self.finished.wait(self.interval):
            self.function(*self.args, **self.kwargs)


class PingStats:
    def __init__(self):
        self.number: int = 0

        self.average: float = 0.
        self.average_square: float = 0.
        self.variance: float = 0.
        self.time_send = time()
        self.last_received: float = 0.

    def send(self):
        self.time_send = time()

    def update(self, ping: float | None = None):
        self.last_received = time()
        ping = ping or (self.last_received - self.time_send) * 1000
        self.average = ((self.average * self.number) + ping) / (self.number + 1)
        self.average_square = ((self.average_square * self.number) + (ping * ping)) / (self.number + 1)
        self.variance = sqrt(self.average_square - (self.average * self.average))
        self.number += 1


class Ping:
    DELAY = 10

    def __init__(self):
        self.tcp = PingStats()
        self.udp = PingStats()
        self._control: ControlStack | None = None
        self._voice: VoiceStack | None = None
        self._timer = RepeatTimer(Ping.DELAY, self.send)

    def set_voice(self, voice: VoiceStack):
        self._voice = voice

    def set_control(self, control: ControlStack):
        self._control = control

    def start(self):
        if not self._control or not self._voice:
            raise Exception(f"Cannot start ping timer. ControlStack = {self._control}, VoiceStack = {self._voice}")
        self._timer.start()

    def cancel(self):
        self._timer.cancel()
        self.reset()

    def reset(self):
        self.tcp = PingStats()
        self.udp = PingStats()
        if not self._timer.cancel():
            self._timer.cancel()
        self._timer = RepeatTimer(Ping.DELAY, self.send)

    def send(self):
        if not self._control.is_connected():
            return
        packet = PingPacket()
        packet.timestamp = int(time())
        packet.tcp_ping_avg = self.tcp.average
        packet.tcp_ping_var = self.tcp.variance
        packet.tcp_packets = self.tcp.number
        packet.udp_packets = self.udp.number
        packet.udp_ping_avg = self.udp.average
        packet.udp_ping_var = self.udp.variance
        packet.good = self._voice.ocb.ui_good
        packet.late = self._voice.ocb.ui_late
        packet.lost = self._voice.ocb.ui_lost

        # Send a TCP ping
        self.tcp.send()
        self._control.send_message(MessageType.Ping, packet)


        # Send a UDP ping to check connection
        if self._voice.check_connection:
            self.udp.send()
            self._voice.ping(True, False)


        if self._voice.check_connection and time() - self._voice.last_good_ping > 15:
            self._voice.active = False
            self._voice.signal_protocol_change()

        # If no TCP ping has been received for over 60 seconds, then connection is lost
        if (self.tcp.time_send != 0 and
                time() - self.tcp.time_send > 60000 and
                time() > self.tcp.last_received + 60):
            self._control.timeout()
            return
        return
