from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from pymumble_typed.network.control import ControlStack
    from pymumble_typed.network.voice import VoiceStack

from math import sqrt
from threading import Timer
from time import time

from pymumble_typed import MessageType
from pymumble_typed.protobuf.Mumble_pb2 import Ping as PingPacket


class RepeatTimer(Timer):
    def __init__(self, interval: float, function: Callable[[], None], *args, **kwargs):
        super().__init__(interval, function, args, kwargs)
        self.daemon = True

    def run(self):
        while not self.finished.wait(self.interval):
            self.function(*self.args, **self.kwargs)


class PingStats:
    def __init__(self):
        self.number: int = 0

        # Mean and standard deviation of the pings, in milliseconds, over the whole connection: the *_ping_var fields of
        # the Ping message carry the standard deviation, as the Mumble client does.
        self.average: float = 0.0
        self.deviation: float = 0.0
        # Sum of the squared distances from the mean (Welford): unlike the mean of the squares minus the squared mean,
        # it never goes below zero through rounding, which would make sqrt raise.
        self._squared_distances: float = 0.0
        self.started = time()
        self.time_send = time()
        self.last_received: float = 0.0
        self.lost: int = 0

    def send(self):
        self.time_send = time()

    def update(self, ping: float | None = None):
        self.last_received = time()
        # A ping of 0.0 is a measure (a clock too coarse for a local round trip), not a missing one.
        if ping is None:
            ping = (self.last_received - self.time_send) * 1000
        self.number += 1
        distance = ping - self.average
        self.average += distance / self.number
        self._squared_distances += distance * (ping - self.average)
        self.deviation = sqrt(self._squared_distances / self.number)

    def silent_for(self) -> float:
        """Seconds since the last answer, or since the stats started when none came yet."""
        return time() - (self.last_received or self.started)


class Ping:
    DELAY = 10
    # Seconds without an answer to the TCP pings after which the connection counts as lost.
    TIMEOUT = 60

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
        if not self._control:
            return

        if not self._control.is_connected():
            return
        packet = PingPacket()
        packet.timestamp = int(time())
        packet.tcp_ping_avg = self.tcp.average
        packet.tcp_ping_var = self.tcp.deviation
        packet.tcp_packets = self.tcp.number
        packet.udp_packets = self.udp.number
        packet.udp_ping_avg = self.udp.average
        packet.udp_ping_var = self.udp.deviation

        # Send a TCP ping
        self.tcp.send()
        self._control.send_message(MessageType.Ping, packet)

        if not self._voice:
            return

        packet.good = self._voice.ocb.ui_good
        packet.late = self._voice.ocb.ui_late
        packet.lost = self._voice.ocb.ui_lost

        # Send a UDP ping to check connection
        if self._voice.check_connection:
            self.udp.send()
            self._voice.ping(True, False)

        if self._voice.check_connection and time() - self._voice.last_good_ping > 15:
            if self._voice.active:
                self._control.logger.warning(
                    "No UDP ping response received in the last 15s, falling back to TCP for voice"
                )
                self._voice.active = False
                self._voice.signal_protocol_change()
            else:
                # Already on the TCP fallback: VoiceStack._listen's loop condition includes
                # `active`, so its listener thread exited the moment we fell back and nothing is
                # left receiving UDP responses. sync() performs its own bounded receive and calls
                # enable_udp() (restarting the listener) if a response arrives, so retrying it
                # here every DELAY seconds is what gives UDP a chance to recover instead of
                # staying downgraded for the rest of the connection.
                self._voice.sync()

        # If no TCP ping has been received for over 60 seconds, then connection is lost
        if self.tcp.silent_for() > Ping.TIMEOUT:
            self._control.timeout()
