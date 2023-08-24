from __future__ import annotations

from threading import Thread, Lock
from time import sleep
from typing import TYPE_CHECKING

from pymumble_typed import MessageType
from pymumble_typed.network.control import ControlStack

from pymumble_typed.network.udp_data import PingData, UDPData
from pymumble_typed.protobuf.MumbleUDP_pb2 import Audio

if TYPE_CHECKING:
    from logging import Logger
    from typing import Callable

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
        self._listeners: list[Callable[[bool], None]] = []

    def on_protocol_switch(self, func: Callable[[bool], None]):
        self._listeners.append(func)

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
        for listener in self._listeners:
            listener(self.active)

    def _sync(self):
        self.socket.settimeout(3)
        self.ping(True, False)
        try:
            response = self.socket.recv(2048)
        except timeout:
            self.logger.warning("VoiceStack: Couldn't initialize UDP connection. Falling back to TCP.")
            self.active = False
            self._signal_protocol_change()
            return
        self.ocb.decrypt(response)
        self.socket.settimeout(None)
        self.active = True
        self._signal_protocol_change()
        self._recv_thread.start()

    def sync(self):
        thread = Thread(target=self._sync, name="VoiceStack:CryptSetup")
        thread.start()

    def ping(self, enforce=False, request_extended_information=False):
        packet = PingData()
        packet.request_extended_information = request_extended_information
        self.send_packet(packet, enforce)

    def send_packet(self, data: UDPData, enforce=True):
        if self.active or enforce:
            self.logger.debug(f"VoiceStack: sending {data.type.name}")
            self._crypt_lock.acquire(True)
            encrypted = self.ocb.encrypt(data.serialized_udp_packet)
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
        while not self.exit and self.control.is_connected():
            try:
                response = self.socket.recv(2048)
                decrypted = self.ocb.decrypt(response)
                packet = Audio()
                packet.ParseFromString(decrypted[1:])
                # TODO: handling incoming audio packets
            except BlockingIOError:
                self.logger.error("VoiceStack: BlockingIOError, packet may will be lost in the next seconds")
                sleep(1)

    def stop(self):
        self.exit = True
        self._recv_thread.join()
