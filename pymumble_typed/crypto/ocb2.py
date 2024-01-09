# 1st Source:
# 2nd Source: https://github.com/ianling/mumpy/blob/dev/mumpy/mumblecrypto.py
from math import ceil
from struct import pack, unpack
from time import time

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes

AES_BLOCK_SIZE = 128 // 8
AES_KEY_SIZE_BITS = 128
AES_KEY_SIZE_BYTES = AES_KEY_SIZE_BITS // 8
SHIFT_BITS = 63
UINT64_MAX_LIMIT = (1 << 64) - 1


class EncryptFailedException(Exception):
    pass


class DecryptFailedException(Exception):
    pass


class CryptStateOCB2:
    def __init__(self):
        self.ui_good = 0
        self.ui_late = 0
        self.ui_lost = 0
        self.t_last_good = 0

        self._aes: AES = None
        self._raw_key = get_random_bytes(AES_KEY_SIZE_BYTES)
        self._encrypt_iv: bytearray = bytearray(get_random_bytes(AES_BLOCK_SIZE))
        self._decrypt_iv: bytearray = bytearray(get_random_bytes(AES_BLOCK_SIZE))
        self.decrypt_history = bytearray(0x100)

    @property
    def raw_key(self):
        return self._raw_key

    @raw_key.setter
    def raw_key(self, raw_key: bytes):
        if len(raw_key) != AES_KEY_SIZE_BYTES:
            raise Exception('raw_key has wrong length')
        self._raw_key = bytes(raw_key)
        self._aes: AES = AES.new(self._raw_key, AES.MODE_ECB)

    @property
    def encrypt_iv(self):
        return self._encrypt_iv

    @encrypt_iv.setter
    def encrypt_iv(self, encrypt_iv: bytearray):
        if len(encrypt_iv) != AES_BLOCK_SIZE:
            raise Exception('encrypt_iv wrong length')
        self._encrypt_iv = bytearray(encrypt_iv)

    @property
    def decrypt_iv(self):
        return self._decrypt_iv

    @decrypt_iv.setter
    def decrypt_iv(self, decrypt_iv: bytearray):
        if len(decrypt_iv) != AES_BLOCK_SIZE:
            raise Exception('encrypt_iv wrong length')
        self._decrypt_iv = bytearray(decrypt_iv)

    def gen_key(self):
        self.raw_key = get_random_bytes(AES_KEY_SIZE_BYTES)
        self.encrypt_iv = get_random_bytes(AES_BLOCK_SIZE)
        self.decrypt_iv = get_random_bytes(AES_BLOCK_SIZE)

    def set_key(self, raw_key: bytes, encrypt_iv: bytearray, decrypt_iv: bytearray):
        self.raw_key = raw_key
        self.encrypt_iv = encrypt_iv
        self.decrypt_iv = decrypt_iv

    def encrypt(self, source: bytes):
        nonce = int.from_bytes(self.encrypt_iv, byteorder="little")
        nonce += 1
        self.encrypt_iv = nonce.to_bytes(AES_BLOCK_SIZE, byteorder="little")
        dst, tag = ocb_encrypt(self._aes, source, bytes(self.encrypt_iv))

        # dst[0] = encrypt_iv[0];
        # dst[1] = tag[0];
        # dst[2] = tag[1];
        # dst[3] = tag[2];
        return bytes((self.encrypt_iv[0], tag[0], tag[1], tag[2])) + dst

    def decrypt(self, source: bytes) -> bytes:
        if len(source) < 4:
            raise DecryptFailedException("Source <4 bytes long!")

        restore = False
        save_iv = self.decrypt_iv.copy()
        iv_byte = source[0]
        late = 0
        lost = 0
        # Received in order
        if (self.decrypt_iv[0] + 1) & 0xFF == iv_byte:
            if iv_byte > self.decrypt_iv[0]:
                self.decrypt_iv[0] = iv_byte
            elif iv_byte < self.decrypt_iv[0]:
                self.decrypt_iv[0] = iv_byte
                self.decrypt_iv = increment_iv(self.decrypt_iv, 1)
            else:
                self.decrypt_iv = save_iv
                raise DecryptFailedException("iv_byte == decrypt_iv[0]")
        # Received out of order or repeated
        else:
            diff = iv_byte - self.decrypt_iv[0]
            if diff > 128:
                diff -= 256
            elif diff < -128:
                diff += 256

            if iv_byte > self.decrypt_iv[0]:
                if -30 < diff < 0:
                    late = 1
                    lost = -1
                    self.decrypt_iv[0] = iv_byte
                    self.decrypt_iv = decrement_iv(self.decrypt_iv, 1)
                    restore = True
                elif diff > 0:
                    lost = iv_byte - self.decrypt_iv[0] - 1
                    self.decrypt_iv[0] = iv_byte
                else:
                    self.decrypt_iv = save_iv
                    raise DecryptFailedException("Lost too many packets?")
            elif iv_byte < self.decrypt_iv[0]:
                if -30 < diff < 0:
                    late = 1
                    lost = -1
                    self.decrypt_iv[0] = iv_byte
                    restore = True
                elif diff > 0:
                    lost = 256 - self.decrypt_iv[0] + iv_byte - 1
                    self.decrypt_iv[0] = iv_byte
                    self.decrypt_iv = increment_iv(self.decrypt_iv, 1)
                else:
                    self.decrypt_iv = save_iv
                    raise DecryptFailedException("Lost too many packets?")
            else:
                self.decrypt_iv = save_iv
                raise DecryptFailedException("iv_byte == decrypt_iv[0]")

            if self.decrypt_history[self.decrypt_iv[0]] == self.decrypt_iv[1]:
                self.decrypt_iv = save_iv
                raise DecryptFailedException("decrypt_iv in history")
        try:
            dst, tag = ocb_decrypt(self._aes, source[4:], bytes(self.decrypt_iv), len(source) - 4)
        except:
            self.decrypt_iv = save_iv
            raise DecryptFailedException("Decryption failed")

        if tag[:3] != source[1:4]:
            self.decrypt_iv = save_iv
            raise DecryptFailedException("Tag didn't match")

        self.decrypt_history[self.decrypt_iv[0]] = self.decrypt_iv[1]

        if restore:
            self.decrypt_iv = save_iv

        self.ui_late += late

        self.ui_good += 1
        self.ui_lost += lost

        self.t_last_good = time()
        return dst


def S2(block: bytes) -> bytes:
    ll, uu = unpack('>QQ', block)
    carry = ll >> 63
    block = pack('>QQ',
                 ((ll << 1) | (uu >> 63)) & UINT64_MAX_LIMIT,
                 ((uu << 1) ^ (carry * 0x87)) & UINT64_MAX_LIMIT)
    return block


def S3(block: bytes) -> bytes:
    return xor(block, S2(block))


def ocb_encrypt(aes: AES, plain: bytes, nonce: bytes, *, insecure=False) -> [bytes, bytes]:
    delta = aes.encrypt(nonce)
    checksum = bytes(AES_BLOCK_SIZE)

    pos = 0
    encrypted = bytearray(ceil(len(plain) / AES_BLOCK_SIZE) * AES_BLOCK_SIZE)
    length = len(plain)
    while length > AES_BLOCK_SIZE:
        block = plain[pos: pos + AES_BLOCK_SIZE]
        flip_a_bit = False
        if length - AES_BLOCK_SIZE <= AES_BLOCK_SIZE:
            sum_ = 0
            for i in range(0, AES_BLOCK_SIZE - 1):
                sum_ |= plain[pos + i - 1]
            flip_a_bit = not insecure and sum_ == 0

        delta = S2(delta)  # S2(delta);
        tmp = xor(delta, block)  # XOR(tmp, delta, reinterpret_cast< const subblock * >(plain));
        if flip_a_bit:
            tmp = bytearray(tmp)
            tmp[-1] = tmp[-1] ^ 1
            tmp = bytes(tmp)
            # tmp = xor(tmp, bytes((1,)))

        tmp = aes.encrypt(tmp)  # AESencrypt(tmp, tmp, raw_key);
        encrypted_block = xor(delta, tmp)  # XOR(reinterpret_cast< subblock * >(encrypted), delta, tmp);
        checksum = xor(checksum, block)  # XOR(checksum, checksum, reinterpret_cast< const subblock * >(plain));
        if flip_a_bit:
            checksum = bytearray(checksum)
            checksum[-1] = checksum[-1] ^ 1
            checksum = bytes(checksum)
            # checksum = xor(checksum, bytes((1,)))  # *reinterpret_cast< unsigned char * >(checksum) ^= 1;

        encrypted[pos: pos + AES_BLOCK_SIZE] = encrypted_block
        length -= AES_BLOCK_SIZE
        pos += AES_BLOCK_SIZE

    delta = S2(delta)  # S2(delta);
    # ZERO(tmp);
    # tmp[BLOCKSIZE - 1] = SWAPPED(len * 8);
    tmp = pack('>QQ', 0, length * 8)

    tmp = xor(tmp, delta)  # XOR(tmp, tmp, delta);
    pad = aes.encrypt(tmp)  # AESencrypt(tmp, pad, raw_key);
    tmp = plain[pos:pos + length]
    tmp += pad[length:AES_BLOCK_SIZE]
    checksum = xor(checksum, tmp)  # XOR(checksum, checksum, tmp);
    tmp = xor(pad, tmp)  # XOR(tmp, pad, tmp);
    encrypted[pos:] = tmp[0:length]  # memcpy(encrypted, tmp, len);
    """
    delta = S3(delta)  # S3(delta);
    tmp = xor(delta, checksum)  # XOR(tmp, delta, checksum);
    tag = aes.encrypt(tmp)  # AESencrypt(tmp, tag, raw_key);
    """
    delta = S3(delta)
    tag = aes.encrypt(xor(delta, checksum))
    return encrypted, tag


def ocb_decrypt(aes: AES, encrypted: bytes, nonce: bytes, len_plain: int, *, insecure=False) -> [bytes, bytes]:
    delta = aes.encrypt(nonce)  # AESencrypt(nonce, delta, raw_key);
    checksum = bytes(AES_BLOCK_SIZE)  # ZERO(checksum);

    plain = bytearray(len_plain)
    pos = 0
    while len_plain - pos > AES_BLOCK_SIZE:
        delta = S2(delta)  # S2(delta);
        encrypted_block = encrypted[pos:pos + AES_BLOCK_SIZE]  # reinterpret_cast< const subblock * >(encrypted)
        tmp = xor(delta, encrypted_block)  # XOR(tmp, delta, reinterpret_cast< const subblock * >(encrypted));
        tmp = aes.decrypt(tmp)  # AESdecrypt(tmp, tmp, raw_key);
        plain_block = xor(delta, tmp)  # XOR(checksum, checksum, reinterpret_cast< const subblock * >(plain));
        checksum = xor(checksum, plain_block)  # XOR(checksum, checksum, reinterpret_cast< const subblock * >(plain));

        plain[pos:pos + AES_BLOCK_SIZE] = plain_block
        pos += AES_BLOCK_SIZE

    len_remaining = len_plain - pos

    delta = S2(delta)  # S2(delta);

    # ZERO(tmp);
    # tmp[BLOCKSIZE - 1] = SWAPPED(len * 8);
    tmp = pack('>QQ', 0, len_remaining * 8)

    tmp = xor(tmp, delta)  # XOR(tmp, tmp, delta);
    pad = aes.encrypt(tmp)  # AESencrypt(tmp, pad, raw_key);
    encrypted_zeropad = encrypted[pos:] + bytes(AES_BLOCK_SIZE - len_remaining)
    plain_block = xor(encrypted_zeropad, pad)

    checksum = xor(checksum, plain_block)
    plain[pos:] = plain_block[:len_remaining]

    if not insecure and plain_block[:-1] == delta[:-1]:
        raise DecryptFailedException('Possibly tampered/able block, discarding.')

    '''
    delta = S3(delta)  # S3(delta);
    tmp = xor(delta, checksum)  # XOR(tmp, delta, checksum);
    tag = aes.encrypt(tmp)  # AESencrypt(tmp, tag, raw_key);
    '''
    delta = S3(delta)
    tag = aes.encrypt(xor(delta, checksum))

    return bytes(plain), tag


def increment_iv(iv: bytearray, start: int = 0) -> bytearray:
    for i in range(start, AES_BLOCK_SIZE):
        iv[i] = (iv[i] + 1) % 0x100
        if iv[i] != 0:
            break
    return iv


def decrement_iv(iv: bytearray, start: int = 0) -> bytearray:
    for i in range(start, AES_BLOCK_SIZE):
        pre = iv[i]
        iv[i] = (iv[i] - 1) % 0x100
        if pre:
            break
    return iv


def xor(a: bytes, b: bytes) -> bytes:
    a_ = int.from_bytes(a[0:AES_BLOCK_SIZE], byteorder="little")
    b_ = int.from_bytes(b[0:AES_BLOCK_SIZE], byteorder="little")
    res = a_ ^ b_
    return res.to_bytes(byteorder="little", length=AES_BLOCK_SIZE, signed=False)
