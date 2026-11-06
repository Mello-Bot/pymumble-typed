import unittest
from hashlib import sha256

from Cryptodome.Cipher import AES

from pymumble_typed.crypto.ocb2 import S2, S3, CryptStateOCB2, ocb_decrypt, ocb_encrypt, xor

# Known-answer vectors captured from the original per-field implementation of the OCB2 helpers: the output of the
# cipher must stay byte-identical across any optimization of them.
KEY = bytes(range(16))
NONCE = bytes(range(0xF0, 0x100))

# (plaintext length, sha256 of the ciphertext, tag)
OCB_VECTORS = [
    (0, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "5e809d099651e21ba9444a63be7d54da"),
    (1, "4bf5122f344554c53bde2ebb8cd2b7e3d1600ad631c385a5d7cce23c7785459a", "c137629f87b3849ced724b6c72d024d1"),
    (15, "a2cdcd1785c461f4feeff911d6bd5537829ce38d017089c9b5c79b7608811beb", "9e9306d717bd096610c3b6e130fbc141"),
    (16, "33cf488d3e0b96f475ce2a80f533ce5edba98c41913baac15eae0950d593fa54", "6a848149df2376eb183d1bcfd775071e"),
    (17, "1f06d27021d412643351385e2f42298d658c08733e1d3f4329f93cbaa1961631", "8b85c314a8f38f2bb15873d6185179ad"),
    (31, "c2c22d79f1e7934890fc13493ad3abbcd03ae1d5d03930efdb4b33798f758b7a", "1b0a9c203ab547cd7b6edb03de994fef"),
    (32, "a89bffd27cdf0e3cbe4148b3a323413d4a830ea066a5914d4720e73f7d80117b", "18a8d6ef88a4f1aba4ca1bd6edc3086a"),
    (33, "167af4e45daab6cd0491ffc69c72edb477687aa1ccebb97e8f361c0af1415ea4", "022900819920a99756fbf48e3dc0b03a"),
    (100, "5dfa24c90be19c2eb10d6e09f5378296f80de766721a89c8d6eb465e7672a2fe", "7a8b3f655c780849c5e79972ae69586f"),
    (160, "6093df527d2b149243d980d3f1a4927d907e3af501b308bc683e260d9d7de27d", "c94b6527a5d1fbafe45af09818eb589a"),
    (1000, "274f83a98bd12a6177bfd599e7d7ccfa69c40ad6e6feee54c5e4c3a787d60b44", "fcd7075c171060c5cd026a8cc83d73a1"),
]


def plaintext(length: int) -> bytes:
    return bytes((i * 31 + 7) & 0xFF for i in range(length))


class TestOCB2Helpers(unittest.TestCase):
    def test_known_answers(self):
        a = bytes.fromhex("00112233445566778899aabbccddeeff")
        # The top bit set exercises the 0x87 reduction of the doubling.
        b = bytes.fromhex("8f1398da09292c2cd7876b0cdff843f1")

        self.assertEqual(xor(a, b).hex(), "8f02bae94d7c4a5b5f1ec1b71325ad0e")
        self.assertEqual(S2(a).hex(), "0022446688aaccef1133557799bbddfe")
        self.assertEqual(S2(b).hex(), "1e2731b412525859af0ed619bff08765")
        self.assertEqual(S3(b).hex(), "9134a96e1b7b74757889bd156008c494")


class TestOCB2(unittest.TestCase):
    def setUp(self):
        self.aes = AES.new(KEY, AES.MODE_ECB)

    def test_encrypt_known_answers(self):
        for length, digest, tag in OCB_VECTORS:
            with self.subTest(length=length):
                encrypted, encrypt_tag = ocb_encrypt(self.aes, plaintext(length), NONCE)

                self.assertEqual(sha256(encrypted).hexdigest(), digest)
                self.assertEqual(encrypt_tag.hex(), tag)

    def test_decrypt_round_trip(self):
        for length, _, tag in OCB_VECTORS:
            with self.subTest(length=length):
                encrypted, _ = ocb_encrypt(self.aes, plaintext(length), NONCE)

                plain, decrypt_tag = ocb_decrypt(self.aes, bytes(encrypted), NONCE, length)

                self.assertEqual(plain, plaintext(length))
                self.assertEqual(decrypt_tag.hex(), tag)

    def test_encrypt_flip_a_bit_known_answer(self):
        # The last full block before the final one has its first 15 bytes zeroed: the encryption flips a bit of it.
        plain = bytes(31) + b"\x05\x01\x02"

        encrypted, tag = ocb_encrypt(self.aes, plain, NONCE)

        self.assertEqual(encrypted.hex(), "575fb321df2abd6330aca50b8c30a1be4ccb1cd0e83f5b637407f8ecb74fb0e8c4da")
        self.assertEqual(tag.hex(), "0332d83ccd98de484646405869cc21e3")

    def test_crypt_state_packets(self):
        state = CryptStateOCB2()
        state.set_key(KEY, bytearray(NONCE), bytearray(16))

        self.assertEqual(
            sha256(state.encrypt(plaintext(120))).hexdigest(),
            "b8d70e1889d1dfaea759e6d45d3b6e7dbb6b4dd798f88723f023d9889d270d24",
        )
        self.assertEqual(
            sha256(state.encrypt(plaintext(200))).hexdigest(),
            "863ecf54378b207c972ca3544041053e1f6037749652edf1c46521dadd6557b4",
        )

    def test_crypt_state_round_trip(self):
        sender = CryptStateOCB2()
        sender.set_key(KEY, bytearray(NONCE), bytearray(16))
        receiver = CryptStateOCB2()
        receiver.set_key(KEY, bytearray(16), bytearray(NONCE))

        for length in (0, 1, 16, 17, 120, 200):
            with self.subTest(length=length):
                self.assertEqual(receiver.decrypt(sender.encrypt(plaintext(length))), plaintext(length))


if __name__ == "__main__":
    unittest.main()
