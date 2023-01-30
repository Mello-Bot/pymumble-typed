from enum import Enum


class Callback(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CHANNEL_CREATED = "channel_created"
    CHANNEL_UPDATED = "channel_updated"
    CHANNEL_REMOVED = "channel_remove"
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_REMOVED = "user_removed"
    SOUND_RECEIVED = "sound_received"
    TEXT_MESSAGE_RECEIVED = "text_received"
    CONTEXT_ACTION_RECEIVED = "contextAction_received"
    ACL_RECEIVED = "acl_received"
    PERMISSION_DENIED = "permission_denied"
