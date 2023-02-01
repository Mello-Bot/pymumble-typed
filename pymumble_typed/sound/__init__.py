from enum import IntEnum, Enum

AUDIO_PER_PACKET = 0.01
READ_BUFFER_SIZE: int = 4096
SAMPLE_RATE: int = 48000
SEQUENCE_DURATION: float = 0.01
SEQUENCE_RESET_INTERVAL: int = 5


class CodecNotSupportedError(Exception):
    """Thrown when receiving an audio packet from an unsupported codec"""

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


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
