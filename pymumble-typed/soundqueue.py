from enum import IntEnum


class Soundqueue(IntEnum):
    AUDIO_TYPE_CELT_ALPHA = 0
    AUDIO_TYPE_PING = 1
    AUDIO_TYPE_SPEEX = 2
    AUDIO_TYPE_CELT_BETA = 3
    AUDIO_TYPE_OPUS = 4
    AUDIO_TYPE_OPUS_PROFILE = "audio"  # "voip"


def set_soundqueue(s: Soundqueue):
    pass
