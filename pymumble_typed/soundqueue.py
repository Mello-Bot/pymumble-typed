from enum import IntEnum, Enum


class AudioType(IntEnum):
    CELT_ALPHA = 0
    PING = 1
    SPEEX = 2
    CELT_BETA = 3
    OPUS = 4


class CodecProfile(str, Enum):
    Audio = "audio"
    Voip = "voip"
    RestrictedLowDelay = "restricted_lowdelay"
