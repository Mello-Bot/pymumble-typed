from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Version(_message.Message):
    __slots__ = ("version_v1", "version_v2", "release", "os", "os_version")
    VERSION_V1_FIELD_NUMBER: _ClassVar[int]
    VERSION_V2_FIELD_NUMBER: _ClassVar[int]
    RELEASE_FIELD_NUMBER: _ClassVar[int]
    OS_FIELD_NUMBER: _ClassVar[int]
    OS_VERSION_FIELD_NUMBER: _ClassVar[int]
    version_v1: int
    version_v2: int
    release: str
    os: str
    os_version: str
    def __init__(self, version_v1: _Optional[int] = ..., version_v2: _Optional[int] = ..., release: _Optional[str] = ..., os: _Optional[str] = ..., os_version: _Optional[str] = ...) -> None: ...

class UDPTunnel(_message.Message):
    __slots__ = ("packet",)
    PACKET_FIELD_NUMBER: _ClassVar[int]
    packet: bytes
    def __init__(self, packet: _Optional[bytes] = ...) -> None: ...

class Authenticate(_message.Message):
    __slots__ = ("username", "password", "tokens", "celt_versions", "opus", "client_type")
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    PASSWORD_FIELD_NUMBER: _ClassVar[int]
    TOKENS_FIELD_NUMBER: _ClassVar[int]
    CELT_VERSIONS_FIELD_NUMBER: _ClassVar[int]
    OPUS_FIELD_NUMBER: _ClassVar[int]
    CLIENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    username: str
    password: str
    tokens: _containers.RepeatedScalarFieldContainer[str]
    celt_versions: _containers.RepeatedScalarFieldContainer[int]
    opus: bool
    client_type: int
    def __init__(self, username: _Optional[str] = ..., password: _Optional[str] = ..., tokens: _Optional[_Iterable[str]] = ..., celt_versions: _Optional[_Iterable[int]] = ..., opus: bool = ..., client_type: _Optional[int] = ...) -> None: ...

class Ping(_message.Message):
    __slots__ = ("timestamp", "good", "late", "lost", "resync", "udp_packets", "tcp_packets", "udp_ping_avg", "udp_ping_var", "tcp_ping_avg", "tcp_ping_var")
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    GOOD_FIELD_NUMBER: _ClassVar[int]
    LATE_FIELD_NUMBER: _ClassVar[int]
    LOST_FIELD_NUMBER: _ClassVar[int]
    RESYNC_FIELD_NUMBER: _ClassVar[int]
    UDP_PACKETS_FIELD_NUMBER: _ClassVar[int]
    TCP_PACKETS_FIELD_NUMBER: _ClassVar[int]
    UDP_PING_AVG_FIELD_NUMBER: _ClassVar[int]
    UDP_PING_VAR_FIELD_NUMBER: _ClassVar[int]
    TCP_PING_AVG_FIELD_NUMBER: _ClassVar[int]
    TCP_PING_VAR_FIELD_NUMBER: _ClassVar[int]
    timestamp: int
    good: int
    late: int
    lost: int
    resync: int
    udp_packets: int
    tcp_packets: int
    udp_ping_avg: float
    udp_ping_var: float
    tcp_ping_avg: float
    tcp_ping_var: float
    def __init__(self, timestamp: _Optional[int] = ..., good: _Optional[int] = ..., late: _Optional[int] = ..., lost: _Optional[int] = ..., resync: _Optional[int] = ..., udp_packets: _Optional[int] = ..., tcp_packets: _Optional[int] = ..., udp_ping_avg: _Optional[float] = ..., udp_ping_var: _Optional[float] = ..., tcp_ping_avg: _Optional[float] = ..., tcp_ping_var: _Optional[float] = ...) -> None: ...

class Reject(_message.Message):
    __slots__ = ("type", "reason")
    class RejectType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        None: _ClassVar[Reject.RejectType]
        WrongVersion: _ClassVar[Reject.RejectType]
        InvalidUsername: _ClassVar[Reject.RejectType]
        WrongUserPW: _ClassVar[Reject.RejectType]
        WrongServerPW: _ClassVar[Reject.RejectType]
        UsernameInUse: _ClassVar[Reject.RejectType]
        ServerFull: _ClassVar[Reject.RejectType]
        NoCertificate: _ClassVar[Reject.RejectType]
        AuthenticatorFail: _ClassVar[Reject.RejectType]
        NoNewConnections: _ClassVar[Reject.RejectType]
    None: Reject.RejectType
    WrongVersion: Reject.RejectType
    InvalidUsername: Reject.RejectType
    WrongUserPW: Reject.RejectType
    WrongServerPW: Reject.RejectType
    UsernameInUse: Reject.RejectType
    ServerFull: Reject.RejectType
    NoCertificate: Reject.RejectType
    AuthenticatorFail: Reject.RejectType
    NoNewConnections: Reject.RejectType
    TYPE_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    type: Reject.RejectType
    reason: str
    def __init__(self, type: _Optional[_Union[Reject.RejectType, str]] = ..., reason: _Optional[str] = ...) -> None: ...

class ServerSync(_message.Message):
    __slots__ = ("session", "max_bandwidth", "welcome_text", "permissions")
    SESSION_FIELD_NUMBER: _ClassVar[int]
    MAX_BANDWIDTH_FIELD_NUMBER: _ClassVar[int]
    WELCOME_TEXT_FIELD_NUMBER: _ClassVar[int]
    PERMISSIONS_FIELD_NUMBER: _ClassVar[int]
    session: int
    max_bandwidth: int
    welcome_text: str
    permissions: int
    def __init__(self, session: _Optional[int] = ..., max_bandwidth: _Optional[int] = ..., welcome_text: _Optional[str] = ..., permissions: _Optional[int] = ...) -> None: ...

class ChannelRemove(_message.Message):
    __slots__ = ("channel_id",)
    CHANNEL_ID_FIELD_NUMBER: _ClassVar[int]
    channel_id: int
    def __init__(self, channel_id: _Optional[int] = ...) -> None: ...

class ChannelState(_message.Message):
    __slots__ = ("channel_id", "parent", "name", "links", "description", "links_add", "links_remove", "temporary", "position", "description_hash", "max_users", "is_enter_restricted", "can_enter")
    CHANNEL_ID_FIELD_NUMBER: _ClassVar[int]
    PARENT_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    LINKS_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    LINKS_ADD_FIELD_NUMBER: _ClassVar[int]
    LINKS_REMOVE_FIELD_NUMBER: _ClassVar[int]
    TEMPORARY_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_HASH_FIELD_NUMBER: _ClassVar[int]
    MAX_USERS_FIELD_NUMBER: _ClassVar[int]
    IS_ENTER_RESTRICTED_FIELD_NUMBER: _ClassVar[int]
    CAN_ENTER_FIELD_NUMBER: _ClassVar[int]
    channel_id: int
    parent: int
    name: str
    links: _containers.RepeatedScalarFieldContainer[int]
    description: str
    links_add: _containers.RepeatedScalarFieldContainer[int]
    links_remove: _containers.RepeatedScalarFieldContainer[int]
    temporary: bool
    position: int
    description_hash: bytes
    max_users: int
    is_enter_restricted: bool
    can_enter: bool
    def __init__(self, channel_id: _Optional[int] = ..., parent: _Optional[int] = ..., name: _Optional[str] = ..., links: _Optional[_Iterable[int]] = ..., description: _Optional[str] = ..., links_add: _Optional[_Iterable[int]] = ..., links_remove: _Optional[_Iterable[int]] = ..., temporary: bool = ..., position: _Optional[int] = ..., description_hash: _Optional[bytes] = ..., max_users: _Optional[int] = ..., is_enter_restricted: bool = ..., can_enter: bool = ...) -> None: ...

class UserRemove(_message.Message):
    __slots__ = ("session", "actor", "reason", "ban")
    SESSION_FIELD_NUMBER: _ClassVar[int]
    ACTOR_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    BAN_FIELD_NUMBER: _ClassVar[int]
    session: int
    actor: int
    reason: str
    ban: bool
    def __init__(self, session: _Optional[int] = ..., actor: _Optional[int] = ..., reason: _Optional[str] = ..., ban: bool = ...) -> None: ...

class UserState(_message.Message):
    __slots__ = ("session", "actor", "name", "user_id", "channel_id", "mute", "deaf", "suppress", "self_mute", "self_deaf", "texture", "plugin_context", "plugin_identity", "comment", "hash", "comment_hash", "texture_hash", "priority_speaker", "recording", "temporary_access_tokens", "listening_channel_add", "listening_channel_remove", "listening_volume_adjustment")
    class VolumeAdjustment(_message.Message):
        __slots__ = ("listening_channel", "volume_adjustment")
        LISTENING_CHANNEL_FIELD_NUMBER: _ClassVar[int]
        VOLUME_ADJUSTMENT_FIELD_NUMBER: _ClassVar[int]
        listening_channel: int
        volume_adjustment: float
        def __init__(self, listening_channel: _Optional[int] = ..., volume_adjustment: _Optional[float] = ...) -> None: ...
    SESSION_FIELD_NUMBER: _ClassVar[int]
    ACTOR_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_ID_FIELD_NUMBER: _ClassVar[int]
    MUTE_FIELD_NUMBER: _ClassVar[int]
    DEAF_FIELD_NUMBER: _ClassVar[int]
    SUPPRESS_FIELD_NUMBER: _ClassVar[int]
    SELF_MUTE_FIELD_NUMBER: _ClassVar[int]
    SELF_DEAF_FIELD_NUMBER: _ClassVar[int]
    TEXTURE_FIELD_NUMBER: _ClassVar[int]
    PLUGIN_CONTEXT_FIELD_NUMBER: _ClassVar[int]
    PLUGIN_IDENTITY_FIELD_NUMBER: _ClassVar[int]
    COMMENT_FIELD_NUMBER: _ClassVar[int]
    HASH_FIELD_NUMBER: _ClassVar[int]
    COMMENT_HASH_FIELD_NUMBER: _ClassVar[int]
    TEXTURE_HASH_FIELD_NUMBER: _ClassVar[int]
    PRIORITY_SPEAKER_FIELD_NUMBER: _ClassVar[int]
    RECORDING_FIELD_NUMBER: _ClassVar[int]
    TEMPORARY_ACCESS_TOKENS_FIELD_NUMBER: _ClassVar[int]
    LISTENING_CHANNEL_ADD_FIELD_NUMBER: _ClassVar[int]
    LISTENING_CHANNEL_REMOVE_FIELD_NUMBER: _ClassVar[int]
    LISTENING_VOLUME_ADJUSTMENT_FIELD_NUMBER: _ClassVar[int]
    session: int
    actor: int
    name: str
    user_id: int
    channel_id: int
    mute: bool
    deaf: bool
    suppress: bool
    self_mute: bool
    self_deaf: bool
    texture: bytes
    plugin_context: bytes
    plugin_identity: str
    comment: str
    hash: str
    comment_hash: bytes
    texture_hash: bytes
    priority_speaker: bool
    recording: bool
    temporary_access_tokens: _containers.RepeatedScalarFieldContainer[str]
    listening_channel_add: _containers.RepeatedScalarFieldContainer[int]
    listening_channel_remove: _containers.RepeatedScalarFieldContainer[int]
    listening_volume_adjustment: _containers.RepeatedCompositeFieldContainer[UserState.VolumeAdjustment]
    def __init__(self, session: _Optional[int] = ..., actor: _Optional[int] = ..., name: _Optional[str] = ..., user_id: _Optional[int] = ..., channel_id: _Optional[int] = ..., mute: bool = ..., deaf: bool = ..., suppress: bool = ..., self_mute: bool = ..., self_deaf: bool = ..., texture: _Optional[bytes] = ..., plugin_context: _Optional[bytes] = ..., plugin_identity: _Optional[str] = ..., comment: _Optional[str] = ..., hash: _Optional[str] = ..., comment_hash: _Optional[bytes] = ..., texture_hash: _Optional[bytes] = ..., priority_speaker: bool = ..., recording: bool = ..., temporary_access_tokens: _Optional[_Iterable[str]] = ..., listening_channel_add: _Optional[_Iterable[int]] = ..., listening_channel_remove: _Optional[_Iterable[int]] = ..., listening_volume_adjustment: _Optional[_Iterable[_Union[UserState.VolumeAdjustment, _Mapping]]] = ...) -> None: ...

class BanList(_message.Message):
    __slots__ = ("bans", "query")
    class BanEntry(_message.Message):
        __slots__ = ("address", "mask", "name", "hash", "reason", "start", "duration")
        ADDRESS_FIELD_NUMBER: _ClassVar[int]
        MASK_FIELD_NUMBER: _ClassVar[int]
        NAME_FIELD_NUMBER: _ClassVar[int]
        HASH_FIELD_NUMBER: _ClassVar[int]
        REASON_FIELD_NUMBER: _ClassVar[int]
        START_FIELD_NUMBER: _ClassVar[int]
        DURATION_FIELD_NUMBER: _ClassVar[int]
        address: bytes
        mask: int
        name: str
        hash: str
        reason: str
        start: str
        duration: int
        def __init__(self, address: _Optional[bytes] = ..., mask: _Optional[int] = ..., name: _Optional[str] = ..., hash: _Optional[str] = ..., reason: _Optional[str] = ..., start: _Optional[str] = ..., duration: _Optional[int] = ...) -> None: ...
    BANS_FIELD_NUMBER: _ClassVar[int]
    QUERY_FIELD_NUMBER: _ClassVar[int]
    bans: _containers.RepeatedCompositeFieldContainer[BanList.BanEntry]
    query: bool
    def __init__(self, bans: _Optional[_Iterable[_Union[BanList.BanEntry, _Mapping]]] = ..., query: bool = ...) -> None: ...

class TextMessage(_message.Message):
    __slots__ = ("actor", "session", "channel_id", "tree_id", "message")
    ACTOR_FIELD_NUMBER: _ClassVar[int]
    SESSION_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_ID_FIELD_NUMBER: _ClassVar[int]
    TREE_ID_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    actor: int
    session: _containers.RepeatedScalarFieldContainer[int]
    channel_id: _containers.RepeatedScalarFieldContainer[int]
    tree_id: _containers.RepeatedScalarFieldContainer[int]
    message: str
    def __init__(self, actor: _Optional[int] = ..., session: _Optional[_Iterable[int]] = ..., channel_id: _Optional[_Iterable[int]] = ..., tree_id: _Optional[_Iterable[int]] = ..., message: _Optional[str] = ...) -> None: ...

class PermissionDenied(_message.Message):
    __slots__ = ("permission", "channel_id", "session", "reason", "type", "name")
    class DenyType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        Text: _ClassVar[PermissionDenied.DenyType]
        Permission: _ClassVar[PermissionDenied.DenyType]
        SuperUser: _ClassVar[PermissionDenied.DenyType]
        ChannelName: _ClassVar[PermissionDenied.DenyType]
        TextTooLong: _ClassVar[PermissionDenied.DenyType]
        H9K: _ClassVar[PermissionDenied.DenyType]
        TemporaryChannel: _ClassVar[PermissionDenied.DenyType]
        MissingCertificate: _ClassVar[PermissionDenied.DenyType]
        UserName: _ClassVar[PermissionDenied.DenyType]
        ChannelFull: _ClassVar[PermissionDenied.DenyType]
        NestingLimit: _ClassVar[PermissionDenied.DenyType]
        ChannelCountLimit: _ClassVar[PermissionDenied.DenyType]
        ChannelListenerLimit: _ClassVar[PermissionDenied.DenyType]
        UserListenerLimit: _ClassVar[PermissionDenied.DenyType]
    Text: PermissionDenied.DenyType
    Permission: PermissionDenied.DenyType
    SuperUser: PermissionDenied.DenyType
    ChannelName: PermissionDenied.DenyType
    TextTooLong: PermissionDenied.DenyType
    H9K: PermissionDenied.DenyType
    TemporaryChannel: PermissionDenied.DenyType
    MissingCertificate: PermissionDenied.DenyType
    UserName: PermissionDenied.DenyType
    ChannelFull: PermissionDenied.DenyType
    NestingLimit: PermissionDenied.DenyType
    ChannelCountLimit: PermissionDenied.DenyType
    ChannelListenerLimit: PermissionDenied.DenyType
    UserListenerLimit: PermissionDenied.DenyType
    PERMISSION_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_ID_FIELD_NUMBER: _ClassVar[int]
    SESSION_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    permission: int
    channel_id: int
    session: int
    reason: str
    type: PermissionDenied.DenyType
    name: str
    def __init__(self, permission: _Optional[int] = ..., channel_id: _Optional[int] = ..., session: _Optional[int] = ..., reason: _Optional[str] = ..., type: _Optional[_Union[PermissionDenied.DenyType, str]] = ..., name: _Optional[str] = ...) -> None: ...

class ACL(_message.Message):
    __slots__ = ("channel_id", "inherit_acls", "groups", "acls", "query")
    class ChanGroup(_message.Message):
        __slots__ = ("name", "inherited", "inherit", "inheritable", "add", "remove", "inherited_members")
        NAME_FIELD_NUMBER: _ClassVar[int]
        INHERITED_FIELD_NUMBER: _ClassVar[int]
        INHERIT_FIELD_NUMBER: _ClassVar[int]
        INHERITABLE_FIELD_NUMBER: _ClassVar[int]
        ADD_FIELD_NUMBER: _ClassVar[int]
        REMOVE_FIELD_NUMBER: _ClassVar[int]
        INHERITED_MEMBERS_FIELD_NUMBER: _ClassVar[int]
        name: str
        inherited: bool
        inherit: bool
        inheritable: bool
        add: _containers.RepeatedScalarFieldContainer[int]
        remove: _containers.RepeatedScalarFieldContainer[int]
        inherited_members: _containers.RepeatedScalarFieldContainer[int]
        def __init__(self, name: _Optional[str] = ..., inherited: bool = ..., inherit: bool = ..., inheritable: bool = ..., add: _Optional[_Iterable[int]] = ..., remove: _Optional[_Iterable[int]] = ..., inherited_members: _Optional[_Iterable[int]] = ...) -> None: ...
    class ChanACL(_message.Message):
        __slots__ = ("apply_here", "apply_subs", "inherited", "user_id", "group", "grant", "deny")
        APPLY_HERE_FIELD_NUMBER: _ClassVar[int]
        APPLY_SUBS_FIELD_NUMBER: _ClassVar[int]
        INHERITED_FIELD_NUMBER: _ClassVar[int]
        USER_ID_FIELD_NUMBER: _ClassVar[int]
        GROUP_FIELD_NUMBER: _ClassVar[int]
        GRANT_FIELD_NUMBER: _ClassVar[int]
        DENY_FIELD_NUMBER: _ClassVar[int]
        apply_here: bool
        apply_subs: bool
        inherited: bool
        user_id: int
        group: str
        grant: int
        deny: int
        def __init__(self, apply_here: bool = ..., apply_subs: bool = ..., inherited: bool = ..., user_id: _Optional[int] = ..., group: _Optional[str] = ..., grant: _Optional[int] = ..., deny: _Optional[int] = ...) -> None: ...
    CHANNEL_ID_FIELD_NUMBER: _ClassVar[int]
    INHERIT_ACLS_FIELD_NUMBER: _ClassVar[int]
    GROUPS_FIELD_NUMBER: _ClassVar[int]
    ACLS_FIELD_NUMBER: _ClassVar[int]
    QUERY_FIELD_NUMBER: _ClassVar[int]
    channel_id: int
    inherit_acls: bool
    groups: _containers.RepeatedCompositeFieldContainer[ACL.ChanGroup]
    acls: _containers.RepeatedCompositeFieldContainer[ACL.ChanACL]
    query: bool
    def __init__(self, channel_id: _Optional[int] = ..., inherit_acls: bool = ..., groups: _Optional[_Iterable[_Union[ACL.ChanGroup, _Mapping]]] = ..., acls: _Optional[_Iterable[_Union[ACL.ChanACL, _Mapping]]] = ..., query: bool = ...) -> None: ...

class QueryUsers(_message.Message):
    __slots__ = ("ids", "names")
    IDS_FIELD_NUMBER: _ClassVar[int]
    NAMES_FIELD_NUMBER: _ClassVar[int]
    ids: _containers.RepeatedScalarFieldContainer[int]
    names: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, ids: _Optional[_Iterable[int]] = ..., names: _Optional[_Iterable[str]] = ...) -> None: ...

class CryptSetup(_message.Message):
    __slots__ = ("key", "client_nonce", "server_nonce")
    KEY_FIELD_NUMBER: _ClassVar[int]
    CLIENT_NONCE_FIELD_NUMBER: _ClassVar[int]
    SERVER_NONCE_FIELD_NUMBER: _ClassVar[int]
    key: bytes
    client_nonce: bytes
    server_nonce: bytes
    def __init__(self, key: _Optional[bytes] = ..., client_nonce: _Optional[bytes] = ..., server_nonce: _Optional[bytes] = ...) -> None: ...

class ContextActionModify(_message.Message):
    __slots__ = ("action", "text", "context", "operation")
    class Context(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        Server: _ClassVar[ContextActionModify.Context]
        Channel: _ClassVar[ContextActionModify.Context]
        User: _ClassVar[ContextActionModify.Context]
    Server: ContextActionModify.Context
    Channel: ContextActionModify.Context
    User: ContextActionModify.Context
    class Operation(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        Add: _ClassVar[ContextActionModify.Operation]
        Remove: _ClassVar[ContextActionModify.Operation]
    Add: ContextActionModify.Operation
    Remove: ContextActionModify.Operation
    ACTION_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    OPERATION_FIELD_NUMBER: _ClassVar[int]
    action: str
    text: str
    context: int
    operation: ContextActionModify.Operation
    def __init__(self, action: _Optional[str] = ..., text: _Optional[str] = ..., context: _Optional[int] = ..., operation: _Optional[_Union[ContextActionModify.Operation, str]] = ...) -> None: ...

class ContextAction(_message.Message):
    __slots__ = ("session", "channel_id", "action")
    SESSION_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_ID_FIELD_NUMBER: _ClassVar[int]
    ACTION_FIELD_NUMBER: _ClassVar[int]
    session: int
    channel_id: int
    action: str
    def __init__(self, session: _Optional[int] = ..., channel_id: _Optional[int] = ..., action: _Optional[str] = ...) -> None: ...

class UserList(_message.Message):
    __slots__ = ("users",)
    class User(_message.Message):
        __slots__ = ("user_id", "name", "last_seen", "last_channel")
        USER_ID_FIELD_NUMBER: _ClassVar[int]
        NAME_FIELD_NUMBER: _ClassVar[int]
        LAST_SEEN_FIELD_NUMBER: _ClassVar[int]
        LAST_CHANNEL_FIELD_NUMBER: _ClassVar[int]
        user_id: int
        name: str
        last_seen: str
        last_channel: int
        def __init__(self, user_id: _Optional[int] = ..., name: _Optional[str] = ..., last_seen: _Optional[str] = ..., last_channel: _Optional[int] = ...) -> None: ...
    USERS_FIELD_NUMBER: _ClassVar[int]
    users: _containers.RepeatedCompositeFieldContainer[UserList.User]
    def __init__(self, users: _Optional[_Iterable[_Union[UserList.User, _Mapping]]] = ...) -> None: ...

class VoiceTarget(_message.Message):
    __slots__ = ("id", "targets")
    class Target(_message.Message):
        __slots__ = ("session", "channel_id", "group", "links", "children")
        SESSION_FIELD_NUMBER: _ClassVar[int]
        CHANNEL_ID_FIELD_NUMBER: _ClassVar[int]
        GROUP_FIELD_NUMBER: _ClassVar[int]
        LINKS_FIELD_NUMBER: _ClassVar[int]
        CHILDREN_FIELD_NUMBER: _ClassVar[int]
        session: _containers.RepeatedScalarFieldContainer[int]
        channel_id: int
        group: str
        links: bool
        children: bool
        def __init__(self, session: _Optional[_Iterable[int]] = ..., channel_id: _Optional[int] = ..., group: _Optional[str] = ..., links: bool = ..., children: bool = ...) -> None: ...
    ID_FIELD_NUMBER: _ClassVar[int]
    TARGETS_FIELD_NUMBER: _ClassVar[int]
    id: int
    targets: _containers.RepeatedCompositeFieldContainer[VoiceTarget.Target]
    def __init__(self, id: _Optional[int] = ..., targets: _Optional[_Iterable[_Union[VoiceTarget.Target, _Mapping]]] = ...) -> None: ...

class PermissionQuery(_message.Message):
    __slots__ = ("channel_id", "permissions", "flush")
    CHANNEL_ID_FIELD_NUMBER: _ClassVar[int]
    PERMISSIONS_FIELD_NUMBER: _ClassVar[int]
    FLUSH_FIELD_NUMBER: _ClassVar[int]
    channel_id: int
    permissions: int
    flush: bool
    def __init__(self, channel_id: _Optional[int] = ..., permissions: _Optional[int] = ..., flush: bool = ...) -> None: ...

class CodecVersion(_message.Message):
    __slots__ = ("alpha", "beta", "prefer_alpha", "opus")
    ALPHA_FIELD_NUMBER: _ClassVar[int]
    BETA_FIELD_NUMBER: _ClassVar[int]
    PREFER_ALPHA_FIELD_NUMBER: _ClassVar[int]
    OPUS_FIELD_NUMBER: _ClassVar[int]
    alpha: int
    beta: int
    prefer_alpha: bool
    opus: bool
    def __init__(self, alpha: _Optional[int] = ..., beta: _Optional[int] = ..., prefer_alpha: bool = ..., opus: bool = ...) -> None: ...

class UserStats(_message.Message):
    __slots__ = ("session", "stats_only", "certificates", "from_client", "from_server", "udp_packets", "tcp_packets", "udp_ping_avg", "udp_ping_var", "tcp_ping_avg", "tcp_ping_var", "version", "celt_versions", "address", "bandwidth", "onlinesecs", "idlesecs", "strong_certificate", "opus", "rolling_stats")
    class Stats(_message.Message):
        __slots__ = ("good", "late", "lost", "resync")
        GOOD_FIELD_NUMBER: _ClassVar[int]
        LATE_FIELD_NUMBER: _ClassVar[int]
        LOST_FIELD_NUMBER: _ClassVar[int]
        RESYNC_FIELD_NUMBER: _ClassVar[int]
        good: int
        late: int
        lost: int
        resync: int
        def __init__(self, good: _Optional[int] = ..., late: _Optional[int] = ..., lost: _Optional[int] = ..., resync: _Optional[int] = ...) -> None: ...
    class RollingStats(_message.Message):
        __slots__ = ("time_window", "from_client", "from_server")
        TIME_WINDOW_FIELD_NUMBER: _ClassVar[int]
        FROM_CLIENT_FIELD_NUMBER: _ClassVar[int]
        FROM_SERVER_FIELD_NUMBER: _ClassVar[int]
        time_window: int
        from_client: UserStats.Stats
        from_server: UserStats.Stats
        def __init__(self, time_window: _Optional[int] = ..., from_client: _Optional[_Union[UserStats.Stats, _Mapping]] = ..., from_server: _Optional[_Union[UserStats.Stats, _Mapping]] = ...) -> None: ...
    SESSION_FIELD_NUMBER: _ClassVar[int]
    STATS_ONLY_FIELD_NUMBER: _ClassVar[int]
    CERTIFICATES_FIELD_NUMBER: _ClassVar[int]
    FROM_CLIENT_FIELD_NUMBER: _ClassVar[int]
    FROM_SERVER_FIELD_NUMBER: _ClassVar[int]
    UDP_PACKETS_FIELD_NUMBER: _ClassVar[int]
    TCP_PACKETS_FIELD_NUMBER: _ClassVar[int]
    UDP_PING_AVG_FIELD_NUMBER: _ClassVar[int]
    UDP_PING_VAR_FIELD_NUMBER: _ClassVar[int]
    TCP_PING_AVG_FIELD_NUMBER: _ClassVar[int]
    TCP_PING_VAR_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    CELT_VERSIONS_FIELD_NUMBER: _ClassVar[int]
    ADDRESS_FIELD_NUMBER: _ClassVar[int]
    BANDWIDTH_FIELD_NUMBER: _ClassVar[int]
    ONLINESECS_FIELD_NUMBER: _ClassVar[int]
    IDLESECS_FIELD_NUMBER: _ClassVar[int]
    STRONG_CERTIFICATE_FIELD_NUMBER: _ClassVar[int]
    OPUS_FIELD_NUMBER: _ClassVar[int]
    ROLLING_STATS_FIELD_NUMBER: _ClassVar[int]
    session: int
    stats_only: bool
    certificates: _containers.RepeatedScalarFieldContainer[bytes]
    from_client: UserStats.Stats
    from_server: UserStats.Stats
    udp_packets: int
    tcp_packets: int
    udp_ping_avg: float
    udp_ping_var: float
    tcp_ping_avg: float
    tcp_ping_var: float
    version: Version
    celt_versions: _containers.RepeatedScalarFieldContainer[int]
    address: bytes
    bandwidth: int
    onlinesecs: int
    idlesecs: int
    strong_certificate: bool
    opus: bool
    rolling_stats: UserStats.RollingStats
    def __init__(self, session: _Optional[int] = ..., stats_only: bool = ..., certificates: _Optional[_Iterable[bytes]] = ..., from_client: _Optional[_Union[UserStats.Stats, _Mapping]] = ..., from_server: _Optional[_Union[UserStats.Stats, _Mapping]] = ..., udp_packets: _Optional[int] = ..., tcp_packets: _Optional[int] = ..., udp_ping_avg: _Optional[float] = ..., udp_ping_var: _Optional[float] = ..., tcp_ping_avg: _Optional[float] = ..., tcp_ping_var: _Optional[float] = ..., version: _Optional[_Union[Version, _Mapping]] = ..., celt_versions: _Optional[_Iterable[int]] = ..., address: _Optional[bytes] = ..., bandwidth: _Optional[int] = ..., onlinesecs: _Optional[int] = ..., idlesecs: _Optional[int] = ..., strong_certificate: bool = ..., opus: bool = ..., rolling_stats: _Optional[_Union[UserStats.RollingStats, _Mapping]] = ...) -> None: ...

class RequestBlob(_message.Message):
    __slots__ = ("session_texture", "session_comment", "channel_description")
    SESSION_TEXTURE_FIELD_NUMBER: _ClassVar[int]
    SESSION_COMMENT_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    session_texture: _containers.RepeatedScalarFieldContainer[int]
    session_comment: _containers.RepeatedScalarFieldContainer[int]
    channel_description: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, session_texture: _Optional[_Iterable[int]] = ..., session_comment: _Optional[_Iterable[int]] = ..., channel_description: _Optional[_Iterable[int]] = ...) -> None: ...

class ServerConfig(_message.Message):
    __slots__ = ("max_bandwidth", "welcome_text", "allow_html", "message_length", "image_message_length", "max_users", "recording_allowed")
    MAX_BANDWIDTH_FIELD_NUMBER: _ClassVar[int]
    WELCOME_TEXT_FIELD_NUMBER: _ClassVar[int]
    ALLOW_HTML_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_LENGTH_FIELD_NUMBER: _ClassVar[int]
    IMAGE_MESSAGE_LENGTH_FIELD_NUMBER: _ClassVar[int]
    MAX_USERS_FIELD_NUMBER: _ClassVar[int]
    RECORDING_ALLOWED_FIELD_NUMBER: _ClassVar[int]
    max_bandwidth: int
    welcome_text: str
    allow_html: bool
    message_length: int
    image_message_length: int
    max_users: int
    recording_allowed: bool
    def __init__(self, max_bandwidth: _Optional[int] = ..., welcome_text: _Optional[str] = ..., allow_html: bool = ..., message_length: _Optional[int] = ..., image_message_length: _Optional[int] = ..., max_users: _Optional[int] = ..., recording_allowed: bool = ...) -> None: ...

class SuggestConfig(_message.Message):
    __slots__ = ("version_v1", "version_v2", "positional", "push_to_talk")
    VERSION_V1_FIELD_NUMBER: _ClassVar[int]
    VERSION_V2_FIELD_NUMBER: _ClassVar[int]
    POSITIONAL_FIELD_NUMBER: _ClassVar[int]
    PUSH_TO_TALK_FIELD_NUMBER: _ClassVar[int]
    version_v1: int
    version_v2: int
    positional: bool
    push_to_talk: bool
    def __init__(self, version_v1: _Optional[int] = ..., version_v2: _Optional[int] = ..., positional: bool = ..., push_to_talk: bool = ...) -> None: ...

class PluginDataTransmission(_message.Message):
    __slots__ = ("senderSession", "receiverSessions", "data", "dataID")
    SENDERSESSION_FIELD_NUMBER: _ClassVar[int]
    RECEIVERSESSIONS_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    DATAID_FIELD_NUMBER: _ClassVar[int]
    senderSession: int
    receiverSessions: _containers.RepeatedScalarFieldContainer[int]
    data: bytes
    dataID: str
    def __init__(self, senderSession: _Optional[int] = ..., receiverSessions: _Optional[_Iterable[int]] = ..., data: _Optional[bytes] = ..., dataID: _Optional[str] = ...) -> None: ...
