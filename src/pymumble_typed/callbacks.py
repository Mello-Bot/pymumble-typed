from __future__ import annotations

from multiprocessing.pool import ThreadPool
from typing import TYPE_CHECKING, Callable, TypedDict, Literal

if TYPE_CHECKING:
    from typing import NotRequired
    from src.pymumble_typed.sound.soundqueue import SoundChunk
    from src.pymumble_typed.mumble import Mumble
    from src.pymumble_typed.users import User
    from src.pymumble_typed.messages import Message
    from src.pymumble_typed.channels import Channel

    CallbackLiteral = Literal[
        "on_connect", "on_disconnect",
        "on_channel_created", "on_channel_updated", "on_channel_removed",
        "on_user_created", "on_user_updated", "on_user_removed",
        "on_message", "on_sound_received", "on_context_action", "on_acl_received", "on_acl_received", "on_permission_denied"
    ]

    OnConnect = Callable[[None], None]
    OnDisconnect = Callable[[None], None]
    OnChannelCreated = Callable[[Channel], None]
    OnChannelUpdated = Callable[[Channel, dict], None]
    OnChannelRemoved = Callable[[Channel], None]
    OnUserCreated = Callable[[User], None]
    OnUserUpdated = Callable[[User, User, dict], None]
    OnUserRemoved = Callable[[User, User, bool, str], None]
    OnMessage = Callable[[Message], None]
    OnSoundReceived = Callable[[User, SoundChunk], None]
    OnContextAction = Callable[[None], None]
    OnACLReceived = Callable[[None], None]
    OnPermissionDenied = Callable[[int, int, str, str, str], None]


class CallbackDict(TypedDict, total=False):
    on_connect: NotRequired[OnConnect]
    on_disconnect: NotRequired[OnDisconnect]
    on_channel_created: NotRequired[OnChannelCreated]
    on_channel_updated: NotRequired[OnChannelUpdated]
    on_channel_removed: NotRequired[OnChannelRemoved]
    on_user_created: NotRequired[OnUserCreated]
    on_user_updated: NotRequired[OnUserUpdated]
    on_user_removed: NotRequired[OnUserRemoved]
    on_message: NotRequired[OnMessage]
    on_sound_received: NotRequired[OnSoundReceived]
    on_context_action: NotRequired[OnContextAction]
    on_acl_received: NotRequired[OnACLReceived]
    on_permission_denied: NotRequired[OnPermissionDenied]


class Callbacks:
    def __init__(self, client: Mumble):
        self._client = client
        self._temp = CallbackDict()
        self._callbacks = CallbackDict()
        self._pool = ThreadPool()

    def dispatch(self, _type: CallbackLiteral, *args):
        try:
            callback = self._callbacks[_type]
            self._pool.apply_async(callback, args)
        except KeyError:
            pass
        except TypeError:
            pass
        except Exception:
            self._client.logger.error("Error while executing callback", exc_info=True)

    def disable(self):
        self._callbacks = {}

    def ready(self):
        if self._client.ready:
            self._callbacks = self._temp

    def on_connect(self, func: OnConnect) -> None:
        self._temp["on_connect"] = func

    def on_disconnect(self, func: OnDisconnect) -> None:
        self._temp["on_disconnect"] = func

    def on_channel_created(self, func: OnChannelCreated) -> None:
        self._temp["on_channel_created"] = func

    def on_channel_updated(self, func: OnChannelUpdated) -> None:
        self._temp["on_channel_updated"] = func

    def on_channel_removed(self, func: OnChannelRemoved) -> None:
        self._temp["on_channel_removed"] = func

    def on_user_created(self, func: OnUserCreated) -> None:
        self._temp["on_user_created"] = func

    def on_user_updated(self, func: OnUserUpdated) -> None:
        self._temp["on_user_updated"] = func

    def on_user_removed(self, func: OnUserRemoved) -> None:
        self._temp["on_user_removed"] = func

    def on_message(self, func: OnMessage) -> None:
        self._temp["on_message"] = func

    def on_sound_received(self, func: OnSoundReceived) -> None:
        self._temp["on_sound_received"] = func

    def on_context_action(self, func: OnContextAction) -> None:
        self._temp["on_context_action"] = func

    def on_acl_received(self, func: OnACLReceived) -> None:
        self._temp["on_acl_received"] = func

    def on_permission_denied(self, func: OnPermissionDenied) -> None:
        self._temp["on_permission_denied"] = func
