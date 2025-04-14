from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class Audio(_message.Message):
    __slots__ = ("target", "context", "sender_session", "frame_number", "opus_data", "positional_data", "volume_adjustment", "is_terminator")
    TARGET_FIELD_NUMBER: _ClassVar[int]
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    SENDER_SESSION_FIELD_NUMBER: _ClassVar[int]
    FRAME_NUMBER_FIELD_NUMBER: _ClassVar[int]
    OPUS_DATA_FIELD_NUMBER: _ClassVar[int]
    POSITIONAL_DATA_FIELD_NUMBER: _ClassVar[int]
    VOLUME_ADJUSTMENT_FIELD_NUMBER: _ClassVar[int]
    IS_TERMINATOR_FIELD_NUMBER: _ClassVar[int]
    target: int
    context: int
    sender_session: int
    frame_number: int
    opus_data: bytes
    positional_data: _containers.RepeatedScalarFieldContainer[float]
    volume_adjustment: float
    is_terminator: bool
    def __init__(self, target: _Optional[int] = ..., context: _Optional[int] = ..., sender_session: _Optional[int] = ..., frame_number: _Optional[int] = ..., opus_data: _Optional[bytes] = ..., positional_data: _Optional[_Iterable[float]] = ..., volume_adjustment: _Optional[float] = ..., is_terminator: bool = ...) -> None: ...

class Ping(_message.Message):
    __slots__ = ("timestamp", "request_extended_information", "server_version_v2", "user_count", "max_user_count", "max_bandwidth_per_user")
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    REQUEST_EXTENDED_INFORMATION_FIELD_NUMBER: _ClassVar[int]
    SERVER_VERSION_V2_FIELD_NUMBER: _ClassVar[int]
    USER_COUNT_FIELD_NUMBER: _ClassVar[int]
    MAX_USER_COUNT_FIELD_NUMBER: _ClassVar[int]
    MAX_BANDWIDTH_PER_USER_FIELD_NUMBER: _ClassVar[int]
    timestamp: int
    request_extended_information: bool
    server_version_v2: int
    user_count: int
    max_user_count: int
    max_bandwidth_per_user: int
    def __init__(self, timestamp: _Optional[int] = ..., request_extended_information: bool = ..., server_version_v2: _Optional[int] = ..., user_count: _Optional[int] = ..., max_user_count: _Optional[int] = ..., max_bandwidth_per_user: _Optional[int] = ...) -> None: ...
