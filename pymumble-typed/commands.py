from enum import Enum


class Command(Enum):
    MOVE = "move"
    MOD_USER_STATE = "update_user"
    TEXT_MESSAGE = "text_message"
    TEXT_PRIVATE_MESSAGE = "text_private_message"
    LINK_CHANNEL = "link"
    UNLINK_CHANNEL = "unlink"
    QUERY_ACL = "get_acl"
    UPDATE_ACL = "update_acl"
    REMOVE_USER = "remove_user"
    UPDATE_CHANNEL = "update_channel"