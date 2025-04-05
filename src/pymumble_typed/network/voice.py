from __future__ import annotations

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
        self.exit = False
        self.addr = (control.host, control.port)
        self.logger = logger.getChild(self.__class__.__name__)
        self.ocb = CryptStateOCB2()
        self.socket = socket(AF_INET, SOCK_DGRAM)
        self.control = control
        self.active = False
        self._listen_thread = Thread(target=self._listen, name="VoiceStack:ListenLoop")
        self.check_connection = False
        self._crypt_lock = Lock()
        self._last_lost = 0
        self._protocol_switch_listeners: list[Callable[[bool], None]] = []
        self._dispatcher: Callable[[bytes], None] = lambda _: None
        self.last_ping: PingData = PingData()
        self._extended_info = False
        self.last_good_ping = time()

    def on_protocol_switch(self, func: Callable[[bool], None]):
        self._protocol_switch_listeners.append(func)

    def crypt_setup(self, message: CryptSetup):
        self.logger.debug("setting up crypto")
        self._crypt_lock.acquire(True)
        if message.key and message.client_nonce and message.server_nonce:
            self.ocb.set_key(
                message.key,
                bytearray(message.client_nonce),
                bytearray(message.server_nonce)
            )
        elif message.server_nonce:
            self.logger.debug("updating decrypt IV")
            self.ocb.decrypt_iv = message.server_nonce
        else:
            packet = CryptSetup()
            packet.client_nonce = bytes(self.ocb.encrypt_iv)
            self.control.send_message(MessageType.CryptSetup, packet)
        self._crypt_lock.release()

    def signal_protocol_change(self):
        for listener in self._protocol_switch_listeners:
            listener(self.active)

    def _sync(self):
        self.socket.settimeout(3)
        self.ping(True, False)
        try:
            response = self.socket.recv(2048)
        except timeout:
            self.logger.warning("couldn't initialize UDP connection. Falling back to TCP.")
            self.active = False
            self.signal_protocol_change()
            self.check_connection = True
            return
        self._crypt_lock.acquire(True)
        decrypted = self.ocb.decrypt(response)
        self._crypt_lock.release()
        self._dispatcher(decrypted)
        self.check_connection = True

    def enable_udp(self):
        self.socket.settimeout(None)
        self.active = True
        self.signal_protocol_change()
        self._listen_thread = Thread(target=self._listen, name="VoiceStack:ListenLoop")
        self._listen_thread.start()

    def sync(self):
        thread = Thread(target=self._sync, name="VoiceStack:CryptSetup")
        thread.start()

    def ping(self, enforce=False, request_extended_information=False):
        packet = PingData()
        packet.request_extended_information = request_extended_information
        self.last_ping = packet
        self.send_packet(packet, enforce)

    def send_packet(self, data: UDPData, enforce=False):
        if self.active or enforce:
            self.logger.debug(f"sending {data.type.name}")
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
            self.control.ping.send()

    def _listen(self):
        while self.active and not self.exit and self.control.is_connected():
            try:
                response = self.socket.recv(512)
                decrypted = self.ocb.decrypt(response)
                self._dispatcher(decrypted)
            except BlockingIOError:
                self.logger.error("blockingIOError, packet may will be lost in the next seconds")
                sleep(1)
        self.logger.warning(
            f"exiting ListenLoop. Active: {self.active} Exit: {self.exit} Connected: {self.control.is_connected()}")

    def ping_response(self, ping: Ping):
        if ping.max_bandwidth_per_user:
            self._extended_info = True
        self._handle_ping(ping.timestamp)

    def ping_legacy_response(self, ping: bytes):
        timestamp = VarInt()
        timestamp.decode(ping)
        self._handle_ping(timestamp.value)

    def _handle_ping(self, timestamp: int):
        if self.last_ping.time != timestamp:
            self.logger.debug("handling lost UDP ping")
            self.control.ping.udp.lost += 1
            return
        elif not self.active:
            self.last_good_ping = time()
            self.logger.debug("handling UDP ping, resuming inactive connection")
            self.enable_udp()
            ping_time = time_ns() - timestamp
        else:
            self.last_good_ping = time()
            self.logger.debug("handling UDP ping")
            ping_time = time_ns() - timestamp
        self.control.ping.udp.update(ping_time / 1000000)

    def stop(self):
        self.exit = True
        self._listen_thread.join()

    def set_voice_message_dispatcher(self, _dispatch_voice_message: Callable[[UdpMessageType, bytes], None]):
        self._dispatcher = _dispatch_voice_message

    def __del__(self):
        self.exit = True
        self.active = False
