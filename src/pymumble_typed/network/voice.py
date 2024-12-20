from __future__ import annotations

from asyncio import new_event_loop
from threading import Thread, Lock
from time import sleep, time, time_ns
from typing import TYPE_CHECKING

from pymumble_typed import MessageType, UdpMessageType
from pymumble_typed.network.control import ControlStack
from pymumble_typed.network.udp_data import PingData, UDPData

from pymumble_typed.tools import VarInt

if TYPE_CHECKING:
    from logging import Logger
    from typing import Callable

from pymumble_typed.crypto.ocb2 import CryptStateOCB2
from socket import socket, AF_INET, SOCK_DGRAM, timeout, gaierror

from pymumble_typed.protobuf.Mumble_pb2 import CryptSetup
from pymumble_typed.protobuf.MumbleUDP_pb2 import Ping


class VoiceStack:
    def __init__(self, control: ControlStack, logger: Logger):
        self._listen_thread = None
        self.event_loop = new_event_loop()

        self.exit = False
        self.addr = (control.host, control.port)
        self.logger = logger
        self.ocb = CryptStateOCB2()
        self.socket = socket(AF_INET, SOCK_DGRAM)
        self.control = control
        self.active = False
        self._listen_thread = Thread(target=self._listen, name="VoiceStack:ListenLoop")
        self._conn_check_thread = Thread(target=self._conn_check, name="ControlStack:ConnCheck")
        self._crypt_lock = Lock()
        self._last_lost = 0
        self._protocol_switch_listeners: list[Callable[[bool], None]] = []
        self._dispatcher: Callable[[bytes], None] = lambda _: None
        self.last_ping: PingData = PingData()
        self.ping_sent = 0
        self.ping_recv = 0
        self.ping_lost = 0
        self._extended_info = False
        self._last_good_ping = time()
        self.ping_average: float = 0.
        self.ping_variance: float = 0.

    def on_protocol_switch(self, func: Callable[[bool], None]):
        self._protocol_switch_listeners.append(func)

    def crypt_setup(self, message: CryptSetup):
        self.logger.debug("VoiceStack: setting up crypto")
        self._crypt_lock.acquire(True)
        if message.key and message.client_nonce and message.server_nonce:
            self.ocb.set_key(
                message.key,
                bytearray(message.client_nonce),
                bytearray(message.server_nonce)
            )
        elif message.server_nonce:
            self.logger.debug("VoiceStack: updating decrypt IV")
            self.ocb.decrypt_iv = message.server_nonce
        else:
            packet = CryptSetup()
            packet.client_nonce = bytes(self.ocb.encrypt_iv)
            self.control.send_message(MessageType.CryptSetup, packet)
        self._crypt_lock.release()

    def _signal_protocol_change(self):
        for listener in self._protocol_switch_listeners:
            listener(self.active)

    async def _sync(self):
        self.socket.settimeout(3)
        await self.ping(True, False)
        try:
            response = self.socket.recv(2048)
        except timeout:
            self.logger.warning("VoiceStack: Couldn't initialize UDP connection. Falling back to TCP.")
            self.active = False
            self._signal_protocol_change()
            await self.event_loop.create_task(self._conn_check())
            return
        self._crypt_lock.acquire(True)
        decrypted = self.ocb.decrypt(response)
        self._crypt_lock.release()
        self._dispatcher(decrypted)
        self._conn_check_thread.start()

    def enable_udp(self):
        self.socket.settimeout(None)
        self.active = True
        self._signal_protocol_change()
        self._listen_thread = Thread(target=self._listen, name="VoiceStack:ListenLoop")
        self._listen_thread.start()

    async def sync(self):
        await self._sync()

    async def ping(self, enforce=False, request_extended_information=False):
        packet = PingData()
        packet.request_extended_information = request_extended_information
        self.ping_sent += 1
        self.last_ping = packet
        await self.send_packet(packet, enforce)

    async def send_packet(self, data: UDPData, enforce=False):
        if self.active or enforce:
            self.logger.debug(f"VoiceStack: sending {data.type.name}")
            packet = data.serialized_udp_packet if self.control.server_version >= (1, 5, 0) else data.legacy_udp_packet
            self._crypt_lock.acquire(True)
            encrypted = self.ocb.encrypt(packet)
            self._crypt_lock.release()
            try:
                self.socket.sendto(encrypted, self.addr)
            except (gaierror, timeout):
                self.logger.error("Exception occurred while sending UDP packet", exc_info=True)
        elif not data.is_ping:
            self.control.enqueue_audio(data)
        else:
            await self.control.ping.send()

    def _listen(self):
        while self.active and not self.exit and self.control.is_connected():
            try:
                response = self.socket.recv(512)
                decrypted = self.ocb.decrypt(response)
                self._dispatcher(decrypted)
            except BlockingIOError:
                self.logger.error("VoiceStack: BlockingIOError, packet may will be lost in the next seconds")
                sleep(1)
        self.logger.warning(
            f"VoiceStack: Exiting ListenLoop. Active: {self.active} Exit: {self.exit} Connected: {self.control.is_connected()}")

    def ping_response(self, ping: Ping):
        if ping.max_bandwidth_per_user:
            self._extended_info = True
        self._handle_ping(ping.timestamp)

    def ping_legacy_response(self, ping: bytes):
        timestamp = VarInt()
        timestamp.decode(ping)
        self._handle_ping(timestamp.value)

    def _handle_ping(self, timestamp: int):
        ping_time = None
        if self.last_ping.time != timestamp:
            self.logger.debug("VoiceStack: handling lost UDP ping")
            self.ping_lost += 1
            self.ping_recv += 1
        elif not self.active:
            self._last_good_ping = time()
            self.logger.debug("VoiceStack: handling UDP ping, resuming inactive connection")
            self.ping_recv = self.ping_sent
            self.enable_udp()
            ping_time = time_ns() - timestamp
        else:
            self._last_good_ping = time()
            self.logger.debug("VoiceStack: handling UDP ping")
            self.ping_recv += 1
            ping_time = time_ns() - timestamp
        if ping_time:
            try:
                ping_time = ping_time / 1000000
                self.ping_average = (self.ping_average * (self.ping_recv - 1) + ping_time) / self.ping_recv
            except ZeroDivisionError:
                pass
        self.control.ping.udp_good = self.ping_recv - self.ping_lost
        self.control.ping.udp_lost = 0  # TODO: handle late ping packets
        self.control.ping.udp_lost = self.ping_lost
        self.control.ping.udp_packets = self.ping_sent
        self.control.ping.udp_ping_average = self.ping_average
        self.control.ping.udp_ping_variance = self.ping_variance

    def _conn_check(self):
        while not self.exit and self.control.is_connected():
            sleep(10)
            if time() - self._last_good_ping > 15:
                self.active = False
                self._signal_protocol_change()
            self.event_loop.create_task(self.ping(True, False))  # not self._extended_info)

    def stop(self):
        self.exit = True
        self._listen_thread.join()
        self._conn_check_thread.join()

    def set_voice_message_dispatcher(self, _dispatch_voice_message: Callable[[UdpMessageType, bytes], None]):
        self._dispatcher = _dispatch_voice_message

    def __del__(self):
        self.exit = True
        self.active = False
