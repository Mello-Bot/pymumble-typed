from enum import Enum
from typing import Callable


class Callbacks(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CHANNELCREATED = "channel_created"
    CHANNELUPDATED = "channel_updated"
    CHANNELREMOVED = "channel_remove"
    USERCREATED = "user_created"
    USERUPDATED = "user_updated"
    USERREMOVED = "user_removed"
    SOUNDRECEIVED = "sound_received"
    TEXTMESSAGERECEIVED = "text_received"
    CONTEXTACTIONRECEIVED = "contextAction_received"
    ACLRECEIVED = "acl_received"
    PERMISSIONDENIED = "permission_denied"


def set_callback(callback: Callbacks, callable: Callable):
    pass
