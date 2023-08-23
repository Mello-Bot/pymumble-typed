from time import time
from pymumble_typed.protobuf.Mumble_pb2 import Ping as PingPacket


class Ping:
    DELAY = 10

    def __init__(self):
        self.last_receive = 0.
        self.time_send = 0.
        self.number = 1
        self.average = 0.
        self.variance = 0.
        self.last = 0
        self.packet = PingPacket()

    def send(self):
        if self.last + Ping.DELAY < time():
            self.packet = PingPacket()
            self.packet.timestamp = int(time())
            self.packet.tcp_ping_avg = self.average
            self.packet.tcp_ping_var = self.variance
            self.packet.tcp_packets = self.number
            self.time_send = int(time() * 1000)
            self.last = time()
            return True
        return False

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
