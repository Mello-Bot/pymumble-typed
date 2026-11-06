from __future__ import annotations

from typing import TYPE_CHECKING, Literal, TypedDict

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import NotRequired

    from pymumble_typed.channels import Channel
    from pymumble_typed.messages import Message
    from pymumble_typed.mumble import Mumble
    from pymumble_typed.sound.audio import OpusPacket
    from pymumble_typed.users import User

    CallbackLiteral = Literal[
        "on_connect",
        "on_disconnect",
        "on_channel_created",
        "on_channel_updated",
        "on_channel_removed",
        "on_user_created",
        "on_user_updated",
        "on_user_removed",
        "on_message",
        "on_sound_received",
        "on_context_action",
        "on_acl_received",
        "on_acl_received",
        "on_permission_denied",
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
    OnSoundReceived = Callable[[User, OpusPacket], None]
    OnContextAction = Callable[[None], None]
    OnACLReceived = Callable[[None], None]
    OnPermissionDenied = Callable[[int, int, str, str, str], None]

from multiprocessing.pool import ThreadPool
from threading import Lock, current_thread


def initializer(name: str):
    def _init():
        thread = current_thread()
        thread.name = f"{name}[{thread.ident}]"

    return _init


class _BoundedPool:
    """
    A ThreadPool wrapper that logs handler exceptions and bounds its backlog.

    ``multiprocessing.pool.ThreadPool.apply_async`` has an unbounded work queue, so a
    server that floods events (or audio frames) can enqueue tasks faster than the
    workers drain them, growing memory without limit. This wrapper tracks the number of
    outstanding tasks and sheds new ones once ``limit`` is reached, logging the
    saturation periodically instead of silently growing.

    User handlers are run through :meth:`_run`, which logs any exception they raise — a
    raw ``apply_async`` would capture it in the (never awaited) ``AsyncResult`` and
    discard it silently.
    """

    def __init__(self, workers: int, limit: int, logger, name: str):
        self._pool = ThreadPool(workers, initializer=initializer(name))
        self._limit = limit
        self._logger = logger
        self._name = name
        self._lock = Lock()
        self._pending = 0
        self._shed = 0

    def submit(self, callback: Callable, args: tuple, sheddable: bool = True) -> None:
        with self._lock:
            if sheddable and self._pending >= self._limit:
                self._shed += 1
                # Log on the first shed and then sparsely, to avoid flooding the log
                # while still surfacing the condition.
                if self._shed == 1 or self._shed % 100 == 0:
                    self._logger.warning(
                        "%s callback queue saturated (%d pending), shed %d task(s) so far",
                        self._name,
                        self._pending,
                        self._shed,
                    )
                return
            self._pending += 1
        self._pool.apply_async(self._run, (callback, args))

    def _run(self, callback: Callable, args: tuple) -> None:
        try:
            callback(*args)
        except Exception:
            self._logger.error("Unhandled exception in %r callback", callback, exc_info=True)
        finally:
            with self._lock:
                self._pending -= 1

    def close(self) -> None:
        self._pool.close()

    def terminate(self) -> None:
        self._pool.terminate()


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
    # The control pool runs a SINGLE worker so that order-sensitive state callbacks are
    # delivered in the order the server produced them. A multi-worker pool distributes
    # these independent tasks across threads with no ordering guarantee, so an update
    # could run before the create that registers the entity, leaving the consumer with a
    # KeyError. Audio stays parallel on its own pool (sized by max_processes).
    CONTROL_WORKERS = 1

    # Bound on outstanding tasks per pool before sheddable ones are dropped. The control
    # bound is generous (these events are comparatively rare); the sound bound is tight
    # because audio is high-rate and dropping a stale frame is preferable to building an
    # ever-growing backlog.
    MAX_PENDING_CONTROL = 1024
    MAX_PENDING_SOUND = 256

    # State-mutation callbacks are never shed: dropping one leaves every consumer with
    # permanently inconsistent state (e.g. an update or remove for an entity whose create
    # was discarded). Unbounded growth under a sustained flood is the lesser evil here.
    _UNSHEDDABLE: frozenset[CallbackLiteral] = frozenset(
        (
            "on_user_created",
            "on_user_updated",
            "on_user_removed",
            "on_channel_created",
            "on_channel_updated",
            "on_channel_removed",
        )
    )

    def __init__(self, client: Mumble):
        self._client = client
        self._logger = client.logger.getChild(self.__class__.__name__)
        self._temp = CallbackDict()
        self._callbacks = CallbackDict()
        # Control-plane callbacks run on their own single-worker pool; high-rate
        # on_sound_received runs on a dedicated parallel pool so audio bursts can't starve
        # connection/state events (e.g. on_disconnect) when they share a worker.
        self._pool = _BoundedPool(self.CONTROL_WORKERS, self.MAX_PENDING_CONTROL, self._logger, "Callback")
        self._sound_pool = _BoundedPool(client.max_processes, self.MAX_PENDING_SOUND, self._logger, "SoundCallback")

    def dispatch(self, _type: CallbackLiteral, *args):
        try:
            callback = self._callbacks[_type]
        except (KeyError, TypeError):
            return
        pool = self._sound_pool if _type == "on_sound_received" else self._pool
        pool.submit(callback, args, sheddable=_type not in self._UNSHEDDABLE)

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
