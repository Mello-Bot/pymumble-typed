from enum import IntEnum


class Status(IntEnum):
    NOT_CONNECTED = 0
    AUTHENTICATING = 1
    CONNECTED = 2
    FAILED = 3


class Type(IntEnum):
    USER = 0
    BOT = 1
