from enum import Enum


class Commands(Enum):
    MOVE = "move"
    MODUSERSTATE = "update_user"
    TEXTMESSAGE = "text_message"
    TEXTPRIVATEMESSAGE = "text_private_message"
    LINKCHANNEL = "link"
    UNLINKCHANNEL = "unlink"
    QUERYACL = "get_acl"
    UPDATEACL = "update_acl"
    REMOVEUSER = "remove_user"
    UPDATECHANNEL = "update_channel"


def set_command(command: Commands):
    pass
