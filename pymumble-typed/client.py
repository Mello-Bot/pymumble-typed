from enum import IntEnum


class ClientConn(IntEnum):
    NOT_CONNECTED = 0
    AUTHENTICATING = 1
    CONNECTED = 2
    FAILED = 3


class ClientType(IntEnum):
    USER = 0
    BOT = 1


def set_clientconn(client: ClientConn):
    pass


def set_clienttype(client: ClientType):
    pass
