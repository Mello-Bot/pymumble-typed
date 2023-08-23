from __future__ import annotations

from threading import Thread, Lock
from typing import TYPE_CHECKING

from pymumble_typed import MessageType
from pymumble_typed.network.control import ControlStack

from pymumble_typed.network.udp_data import PingData, UDPData

if TYPE_CHECKING:
    from logging import Logger

from pymumble_typed.crypto.ocb2 import CryptStateOCB2
from socket import socket, AF_INET, SOCK_DGRAM, timeout, gaierror

from pymumble_typed.protobuf.Mumble_pb2 import CryptSetup


class VoiceStack:
    def __init__(self, control: ControlStack, logger: Logger):
        self.exit = False
        self.addr = (control.host, control.port)
        self.logger = logger
        self.ocb = CryptStateOCB2()
        self.socket = socket(AF_INET, SOCK_DGRAM)
        self.control = control
        self.active = False
        self._recv_thread = Thread(target=self._listen, name="ControlStack:ListenLoop")
        self._crypt_lock = Lock()
        self._last_lost = 0

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

    def _sync(self):
        self.socket.settimeout(3)
        self.ping(True, True)
        try:
            response = self.socket.recv(2048)
        except timeout:
            self.logger.warning("VoiceStack: Couldn't initialize UDP connection. Falling back to TCP.")
            self.active = False
            return
        self.ocb.decrypt(response, len(response) + 4)
        self.socket.settimeout(None)
        self.active = True
        self._recv_thread.start()

    def sync(self):
        thread = Thread(target=self._sync, name="VoiceStack:CryptSetup")
        thread.start()

    def ping(self, enforce=False, request_extended_information=False):
        packet = PingData()
        packet.request_extended_information = request_extended_information
        self.send_packet(packet, enforce)

    def send_packet(self, data: UDPData, enforce=False):
        if self.active or enforce:
            self.logger.debug(f"VoiceStack: sending {data.type.name}")
            self._crypt_lock.acquire(True)
            encrypted = self.ocb.encrypt(data.legacy_udp_packet)
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
        self.socket.settimeout(10)
        while not self.exit and self.control.is_connected():
            try:
                response = self.socket.recv(2048)
            except timeout:
                pass

    def stop(self):
        self.exit = True
        self._recv_thread.join()

