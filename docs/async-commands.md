# Design: Awaitable commands (Future-based confirmation)

## Problem

`pymumble-typed` sends control-channel commands fire-and-forget: a caller builds a
`Command` (Move, ModUserState, CreateChannel, ...) and `Mumble.execute_command()`
enqueues it on the `ControlStack`. The caller gets no feedback about whether the server
accepted the change.

The server's reaction is asynchronous and takes one of three shapes:

- a **state-change broadcast** (`ChannelState`, `UserState`, `ChannelRemove`,
  `UserRemove`) reflecting the applied change;
- a **`PermissionDenied`** message, meaning the command was rejected;
- **nothing at all** for some commands (notably `TextMessage`, which the server does
  not echo back to the sender).

We want every command that has an observable effect to return a
`concurrent.futures.Future` that resolves with the resulting state object (the *same*
instance stored in `Users`/`Channels`) on success, or fails with a
`PermissionDeniedError` on rejection.

## Why correlation is hard

The Mumble control protocol has **no request/response correlation IDs**. A `ChannelState`
reply that creates a channel carries the new `channel_id` but nothing tying it to the
originating request. So matching a server message back to the command that caused it is
necessarily heuristic. Three properties make it tractable:

1. **TCP in-order processing.** The control channel is TCP and the server processes
   commands sequentially, emitting the resulting state-change or `PermissionDenied`
   *before* moving on to the next message. Replies therefore arrive in the same order as
   the commands that produced them.
2. **Content matching.** `session` + changed field (user ops) or `name` + `parent` /
   `channel_id` (channel ops) narrow a reply down to a specific in-flight command.
3. **The `actor` field.** `UserState` and `UserRemove` carry `actor` — the session of
   the user who triggered the change — but **only when the change was made by *another*
   user** (e.g. an admin moves/mutes us). A user's *own* changes (our `move_in()`,
   self-mute, ...) come back with `actor` **unset**. So a change was caused by us when
   `actor == myself.session` *or* `actor` is absent and the affected session is ours.
   (`ChannelState` has **no** `actor`, so channel ops rely on content + ordering only.)

## Two kinds of command

`execute_command` splits commands into two groups by their message type
(`Mumble._CONFIRMED_TYPES`):

**Confirmed commands** are those the server echoes back as a state change. They are
appended to an ordered pending list (the `Command` carries its own `future` — no wrapper)
and their future is resolved later, when the matching state echo arrives, with the
resulting state object — or rejected when a `PermissionDenied` identifies them.

| Operation | Command | Server reply that resolves the future |
|-----------|---------|----------------------------------------|
| move / mute / deaf / suppress / comment / texture / listening / ... | `Move`, `ModUserState` (`UserState`) | `UserState` echo → the `User` |
| create / rename / move / position / max users / description / link / unlink | `CreateChannel`, `UpdateChannel`, `LinkChannel`, `UnlinkChannel` (`ChannelState`) | `ChannelState` echo → the `Channel` |
| remove channel | `RemoveChannel` (`ChannelRemove`) | `ChannelRemove` echo → `True` |
| kick / ban | `RemoveUser` (`UserRemove`) | `UserRemove` echo → `True` |

**Fire-and-forget commands** are those the server sends **no confirmation** for. There is
nothing to wait for, so they are sent and their future is resolved **immediately** with
`True`; they are never tracked. These are:

| Operation | Command | Why no confirmation |
|-----------|---------|---------------------|
| send channel / private text message | `TextMessage`, `TextPrivateMessage` (`TextMessage`) | the server does not echo a sender's own message back |
| set / clear whisper target | `VoiceTarget` | the server sends no reply; whisper permission is checked when speaking |
| query / update ACL | `QueryACL`, `UpdateACL` (`ACL`) | the ACL reply is delivered via the `on_acl_received` callback, not as a per-command echo |
| fetch comments / textures / descriptions | `RequestBlobCmd` (`RequestBlob`) | internal prefetch; the blob arrives in later state messages |

> **Consequence:** because a fire-and-forget future is already resolved, a later
> `PermissionDenied` for such a command (e.g. *TextTooLong*, or no permission to post in a
> channel) cannot reject it; it is still delivered through the `on_permission_denied`
> callback. (Oversized text is additionally caught client-side, before sending, by
> `TextMessage`/`TextPrivateMessage`.)

This keeps the `Ping` message used only for what it is meant for — keepalive and latency —
instead of as a per-command acknowledgement.

## Resolution paths

State echoes are handled *after* the existing state mutation in
`_dispatch_control_message`, so the future resolves with the object already stored in
state:

| Server message    | Handler                          | Match key                                   | Result               |
|-------------------|----------------------------------|---------------------------------------------|----------------------|
| `UserState`       | `_handle_user_state_success`     | caused by us (`actor == myself`, or `actor` unset and `session == myself`) and `session` | `users.get(session)` |
| `ChannelState`    | `_handle_channel_state_success`  | `channel_id`, or `name`+`parent` (create)   | `channels.get(id)`   |
| `ChannelRemove`   | `_handle_channel_remove_success` | `channel_id`                                | `True`               |
| `UserRemove`      | `_handle_user_remove_success`    | `actor == myself` and `session`             | `True`               |
| `PermissionDenied`| `_handle_permission_denied`      | `session`; `channel_id` (create → parent); channel-creation deny type | raises `PermissionDeniedError` |

All handlers scan the pending list **in insertion order** and act on the first match
(FIFO). A `PermissionDenied` both rejects the matching future *and* still fires the global
`on_permission_denied` callback.

Only confirmed (tracked) commands are matched — fire-and-forget commands have already
resolved and are not in the pending list. The handler computes, per command, the
**sessions** and **channels** a denial could reference, and matches the incoming
`PermissionDenied` against them:

- user ops (`UserState` mute/move/..., `UserRemove` kick/ban) → their `session` (and a
  move's destination `channel_id`);
- channel ops (`ChannelState` update, `ChannelRemove`) → their `channel_id`; a
  `CreateChannel` carries no `channel_id`, so it is matched by its `parent`;
- channel-creation deny types that carry no id (`ChannelName`, `NestingLimit`, ...) → the
  command *kind* (`ChannelState`).

A denial that matches no tracked command rejects nothing and is simply delivered through
the `on_permission_denied` callback.

## Lifecycle and safety

- **Threading.** The pending list is guarded by a lock. Handlers collect the future to
  resolve *under* the lock and call `set_result`/`set_exception` *outside* it, so a
  user `add_done_callback` that re-enters `execute_command` cannot deadlock.
- **Disconnect.** `_cleanup_pending_commands` fails every outstanding future with
  `ConnectionLostError` (a `RuntimeError` subclass) so awaiting callers never hang across
  a drop/reconnect. It is wired into the control stack's disconnect action.
- **No leaks.** A tracked command is removed by its state echo, by a denial, or by
  disconnect cleanup; fire-and-forget commands are never tracked. Futures that nobody
  awaits are simply garbage-collected (`concurrent.futures.Future` neither logs nor raises
  on an unconsumed result, unlike `asyncio`).

## Blob requests (comments, descriptions, avatars)

User comments/avatars and channel descriptions can be large, so the server sends only
their **hash** in `UserState`/`ChannelState`. To get the data the client sends a
`RequestBlob` naming the session/channel; the server replies with a `UserState`/
`ChannelState` carrying the actual `comment`/`texture`/`description` field, which the state
layer stores in `BlobDB` (keyed by hash, so unchanged blobs are not refetched).

The same Future model applies, via dedicated `get_` methods (the existing `request_`
methods are left untouched). Mumble's field names are aliased for clarity:

| Method | Mumble field | Returns |
|--------|--------------|---------|
| `User.get_avatar()` | `texture` | `Future[bytes]` |
| `User.get_description()` | `comment` | `Future[str]` |
| `Channel.get_description()` | `description` | `Future[str]` |

Each method requests **one** blob for **one** user/channel. If the data for the current
hash is already in `BlobDB` (or the blob is unset), the Future is resolved **immediately**;
otherwise a `RequestBlob` is sent and a future is registered in `_pending_blobs`, keyed by
`(kind, target_id)` — `kind` ∈ `{"texture", "comment", "description"}`, `target_id` the
session or channel id. When the matching `UserState`/`ChannelState` arrives,
`_handle_user_blob`/`_handle_channel_blob` resolves the waiting futures with the new value.
Pending blob futures are failed by the same disconnect cleanup as commands.

> The legacy `blob_greedy_update` prefetch and the `request_*` methods are untouched and
> will be deprecated in favour of these `get_` methods.

## Public API

`execute_command(cmd, blocking=True)` now returns a `Future`. Every high-level method in
`User`/`Channel`/`Channels`/`Mumble` that wraps it (`move_in`, `mute`, `rename`,
`new_channel`, `send_text_message`, ...) propagates that `Future`. This is additive:
existing callers that ignore the return value keep working unchanged. The result type is
`Future[Channel]`, `Future[User]`, or `Future[None]`/`Future[bool]` depending on the
command. Blob fetches (`get_avatar`/`get_description`) return `Future[bytes]`/`Future[str]`
as above.

## Trade-offs and limits

- **No confirmation for fire-and-forget commands.** Their future resolves to `True`
  immediately, so a later server rejection cannot fail it (it reaches the
  `on_permission_denied` callback instead). See the table above for the exact list.
- **No-op moves are short-circuited.** A move to the channel the user is already in is not
  echoed by the server (there is nothing to change). `move_in` detects this from local
  state and resolves the future immediately with the user, rather than tracking a command
  that would never be confirmed. This matters in practice because Mumble auto-places a
  registered user into its last channel on reconnect, so a "join your default channel" on
  connect is frequently already satisfied.
- **Dropped echoes hang.** A confirmed command that the server, in some other edge case,
  neither echoes nor denies (e.g. a `ModUserState` that sets a flag already in effect)
  leaves its future pending until disconnect cleanup. There is no wall-clock timeout; this
  trades a rare hang for not polling the server.
- **Create races.** Two clients creating a channel with the same `name`+`parent` at the
  same instant are indistinguishable for `ChannelState` (no `actor`). This is inherent to
  the protocol and is accepted/documented rather than solved.
- **Coarse multi-field resolution.** A command that changes several fields at once
  resolves on the first matching state echo, with the updated state object as the result,
  rather than waiting for every field to be reflected.
