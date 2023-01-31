from enum import IntEnum


class AudioType(IntEnum):
    CELT_ALPHA = 0
    PING = 1
    SPEEX = 2
    CELT_BETA = 3
    OPUS = 4
    OPUS_PROFILE = "audio"  # "voip"
