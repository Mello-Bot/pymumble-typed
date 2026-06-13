import unittest
from concurrent.futures import Future
from unittest.mock import MagicMock, patch

from pymumble_typed import MessageType, PermissionDeniedError
from pymumble_typed.commands import Command, CreateChannel, ModUserState, Move, QueryACL, RequestBlobCmd, TextMessage
from pymumble_typed.mumble import Mumble
from pymumble_typed.protobuf import Mumble_pb2


class TestAsyncCommands(unittest.TestCase):
    @patch("pymumble_typed.mumble.ControlStack")
    @patch("pymumble_typed.mumble.VoiceStack")
    @patch("pymumble_typed.mumble.BlobDB")
    def setUp(self, mock_blob, mock_voice, mock_control):
        self.mumble = Mumble(
            host="localhost",
            user="TestUser",
            password="password",
            port=64738,
            cert_file="./bot.cert",
            key_file="./bot.key",
            logger=MagicMock(),
        )
        # Mock some internal variables
        self.mumble.users = MagicMock()
        self.mumble.channels = MagicMock()
        self.mumble._control = mock_control
        self.mumble._voice = mock_voice

    def _user_state_command(self, session):
        cmd = Command()
        cmd.type = MessageType.UserState
        cmd.packet = Mumble_pb2.UserState()
        cmd.packet.session = session
        return cmd

    def _user_state_echo(self, session, actor=None):
        packet = Mumble_pb2.UserState()
        packet.session = session
        if actor is not None:
            packet.actor = actor
        return packet

    # --- confirmed commands: tracked until the server echoes or rejects them ---

    def test_confirmed_command_is_tracked_and_returns_pending_future(self):
        cmd = self._user_state_command(123)

        future = self.mumble.execute_command(cmd, blocking=False)

        self.assertIsInstance(future, Future)
        self.assertFalse(future.done())  # waits for the server state echo
        self.assertEqual(len(self.mumble._pending_commands), 1)
        # Only the command itself is sent — no extra ping.
        self.assertEqual(self.mumble._control.send_command.call_count, 1)
        self.assertIs(self.mumble._control.send_command.call_args[0][0], cmd)

    def test_user_state_success_resolves_future(self):
        cmd = self._user_state_command(42)
        myself = MagicMock()
        myself.session = 99
        self.mumble.users.myself = myself
        mock_user = MagicMock()
        self.mumble.users.get.return_value = mock_user

        future = self.mumble.execute_command(cmd, blocking=False)
        # Simulate an incoming UserState update we initiated on another user (actor = 99)
        self.mumble._handle_user_state_success(self._user_state_echo(42, actor=99))

        self.assertTrue(future.done())
        self.assertEqual(future.result(), mock_user)
        self.assertEqual(len(self.mumble._pending_commands), 0)

    def test_self_move_with_absent_actor_resolves_future(self):
        # move_in() on ourselves: the server echoes a UserState for our own session with
        # the actor field unset (a user's own changes carry no actor). It must still
        # resolve, otherwise the future hangs until disconnect cleanup.
        myself = MagicMock()
        myself.session = 99
        self.mumble.users.myself = myself
        mock_user = MagicMock()
        self.mumble.users.get.return_value = mock_user

        future = self.mumble.execute_command(self._user_state_command(99), blocking=False)
        self.mumble._handle_user_state_success(self._user_state_echo(99))  # no actor

        self.assertTrue(future.done())
        self.assertEqual(future.result(), mock_user)
        self.assertEqual(len(self.mumble._pending_commands), 0)

    def test_other_user_self_change_does_not_resolve_our_command(self):
        # Another user changing their own state echoes with no actor and their own
        # session; it must not resolve a command we issued against that same session.
        myself = MagicMock()
        myself.session = 99
        self.mumble.users.myself = myself

        future = self.mumble.execute_command(self._user_state_command(42), blocking=False)
        self.mumble._handle_user_state_success(self._user_state_echo(42))  # actor unset

        self.assertFalse(future.done())
        self.assertEqual(len(self.mumble._pending_commands), 1)

    def test_user_state_from_other_actor_does_not_resolve_future(self):
        cmd = self._user_state_command(42)
        myself = MagicMock()
        myself.session = 99
        self.mumble.users.myself = myself

        future = self.mumble.execute_command(cmd, blocking=False)
        # Another user updated it (actor = 100)
        self.mumble._handle_user_state_success(self._user_state_echo(42, actor=100))

        self.assertFalse(future.done())
        self.assertEqual(len(self.mumble._pending_commands), 1)

    def test_permission_denied_rejects_future(self):
        cmd = self._user_state_command(42)
        future = self.mumble.execute_command(cmd, blocking=False)

        packet = Mumble_pb2.PermissionDenied()
        packet.type = 1  # Permission
        packet.reason = "Not allowed to move user"
        packet.session = 42
        self.mumble._handle_permission_denied(packet)

        self.assertTrue(future.done())
        with self.assertRaises(PermissionDeniedError) as context:
            future.result()
        self.assertEqual(context.exception.deny_type, 1)
        self.assertEqual(context.exception.reason, "Not allowed to move user")
        self.assertEqual(context.exception.session, 42)
        self.assertEqual(len(self.mumble._pending_commands), 0)

    # --- fire-and-forget commands: no server confirmation, resolved immediately ---

    def test_fire_and_forget_text_message_resolves_immediately(self):
        cmd = TextMessage(self.mumble, session=99, channel_id=10, message="hi")

        future = self.mumble.execute_command(cmd, blocking=False)

        self.assertTrue(future.done())
        self.assertTrue(future.result())
        self.assertEqual(len(self.mumble._pending_commands), 0)  # never tracked
        self.assertEqual(self.mumble._control.send_command.call_count, 1)

    def test_fire_and_forget_acl_resolves_immediately(self):
        future = self.mumble.execute_command(QueryACL(3), blocking=False)

        self.assertTrue(future.done())
        self.assertTrue(future.result())
        self.assertEqual(len(self.mumble._pending_commands), 0)

    def test_unmatched_denied_leaves_pending_commands_untouched(self):
        # A denial that identifies no tracked command must not reject an unrelated one; it
        # only fires the on_permission_denied callback (dispatched separately).
        future = self.mumble.execute_command(self._user_state_command(42), blocking=False)

        packet = Mumble_pb2.PermissionDenied()
        packet.type = 1  # Permission
        packet.channel_id = 7  # matches neither the session nor a channel of the command
        self.mumble._handle_permission_denied(packet)

        self.assertFalse(future.done())
        self.assertEqual(len(self.mumble._pending_commands), 1)

    # --- channel create resolution ---

    def test_channel_create_resolves_with_channel_object(self):
        # new_channel() must resolve with the new Channel state object, not a bool.
        mock_channel = MagicMock()
        self.mumble.channels.get.return_value = mock_channel

        future = self.mumble.execute_command(CreateChannel(1, "Test", False), blocking=False)

        packet = Mumble_pb2.ChannelState()
        packet.channel_id = 42
        packet.name = "Test"
        packet.parent = 1
        self.mumble._handle_channel_state_success(packet)

        self.assertTrue(future.done())
        self.assertIs(future.result(), mock_channel)
        self.assertEqual(self.mumble.channels.get.call_args[0][0], 42)
        self.assertEqual(len(self.mumble._pending_commands), 0)

    def test_channel_create_resolves_when_echo_omits_parent(self):
        # The server omits parent for some channels; the create must still match on name.
        mock_channel = MagicMock()
        self.mumble.channels.get.return_value = mock_channel

        future = self.mumble.execute_command(CreateChannel(1, "Test", False), blocking=False)

        packet = Mumble_pb2.ChannelState()
        packet.channel_id = 42
        packet.name = "Test"  # no parent field set
        self.mumble._handle_channel_state_success(packet)

        self.assertTrue(future.done())
        self.assertIs(future.result(), mock_channel)
        self.assertEqual(len(self.mumble._pending_commands), 0)

    def test_channel_create_denied_rejects_future(self):
        # The CreateChannel command has no channel_id (only parent); the denial references
        # the parent channel and must still reject the future.
        future = self.mumble.execute_command(CreateChannel(1, "Test", False), blocking=False)

        packet = Mumble_pb2.PermissionDenied()
        packet.type = 1  # Permission
        packet.reason = "Not allowed to create channel"
        packet.channel_id = 1  # the parent where creation was denied
        self.mumble._handle_permission_denied(packet)

        self.assertTrue(future.done())
        with self.assertRaises(PermissionDeniedError) as context:
            future.result()
        self.assertEqual(context.exception.channel_id, 1)
        self.assertEqual(len(self.mumble._pending_commands), 0)

    def test_channel_create_denied_by_name_rejects_future(self):
        # ChannelName denials carry no channel_id; they must still reject the create.
        future = self.mumble.execute_command(CreateChannel(1, "Bad/Name", False), blocking=False)

        packet = Mumble_pb2.PermissionDenied()
        packet.type = Mumble_pb2.PermissionDenied.ChannelName
        packet.reason = "Invalid channel name"
        self.mumble._handle_permission_denied(packet)

        self.assertTrue(future.done())
        with self.assertRaises(PermissionDeniedError) as context:
            future.result()
        self.assertEqual(context.exception.deny_type, Mumble_pb2.PermissionDenied.ChannelName)
        self.assertEqual(len(self.mumble._pending_commands), 0)

    def test_move_denied_by_destination_channel(self):
        # A move denial may carry only the destination channel_id (no session); the Move
        # command stores that channel in its UserState packet, so it must match.
        future = self.mumble.execute_command(Move(5, 10), blocking=False)

        packet = Mumble_pb2.PermissionDenied()
        packet.type = 1  # Permission
        packet.channel_id = 10  # destination, no session field
        self.mumble._handle_permission_denied(packet)

        self.assertTrue(future.done())
        with self.assertRaises(PermissionDeniedError):
            future.result()
        self.assertEqual(len(self.mumble._pending_commands), 0)

    def test_permission_denied_matches_by_content(self):
        # With several commands in flight, a denial rejects the one it identifies by
        # content, leaving unrelated commands pending.
        mute_future = self.mumble.execute_command(ModUserState(5, mute=True), blocking=False)
        create_future = self.mumble.execute_command(CreateChannel(1, "Test", False), blocking=False)

        packet = Mumble_pb2.PermissionDenied()
        packet.type = 1  # Permission
        packet.channel_id = 1  # identifies the create (parent), not the mute
        self.mumble._handle_permission_denied(packet)

        self.assertTrue(create_future.done())
        self.assertIsInstance(create_future.exception(), PermissionDeniedError)
        self.assertFalse(mute_future.done())
        self.assertEqual(len(self.mumble._pending_commands), 1)

    # --- blob requests: heavy comment/texture/description fetched on demand ---

    def test_blob_request_sends_request_blob_and_stays_pending(self):
        future = self.mumble._await_blob("texture", 5, RequestBlobCmd(user_texture_hashes=[5]))

        self.assertFalse(future.done())
        sent = self.mumble._control.send_command.call_args[0][0]
        self.assertEqual(sent.type, MessageType.RequestBlob)
        self.assertEqual(list(sent.packet.session_texture), [5])

    def test_blob_request_resolves_with_user_texture(self):
        future = self.mumble._await_blob("texture", 5, RequestBlobCmd(user_texture_hashes=[5]))
        user = MagicMock()
        user.texture = b"avatar-bytes"
        self.mumble.users.get.return_value = user

        packet = Mumble_pb2.UserState()
        packet.session = 5
        packet.texture = b"avatar-bytes"
        self.mumble._handle_user_blob(packet)

        self.assertTrue(future.done())
        self.assertEqual(future.result(), b"avatar-bytes")
        self.assertEqual(self.mumble._pending_blobs, {})

    def test_blob_request_resolves_with_channel_description(self):
        future = self.mumble._await_blob("description", 3, RequestBlobCmd(channel_comment_hashes=[3]))
        channel = MagicMock()
        channel.description = "the description"
        self.mumble.channels.get.return_value = channel

        packet = Mumble_pb2.ChannelState()
        packet.channel_id = 3
        packet.description = "the description"
        self.mumble._handle_channel_blob(packet)

        self.assertEqual(future.result(), "the description")

    def test_blob_request_only_resolves_matching_kind(self):
        # A texture request must not be resolved by a comment delivery for the same user.
        texture_future = self.mumble._await_blob("texture", 5, RequestBlobCmd(user_texture_hashes=[5]))
        user = MagicMock()
        user.comment = "a comment"
        self.mumble.users.get.return_value = user

        packet = Mumble_pb2.UserState()
        packet.session = 5
        packet.comment = "a comment"  # comment only, not texture
        self.mumble._handle_user_blob(packet)

        self.assertFalse(texture_future.done())

    def test_resolved_future_is_immediate(self):
        future = self.mumble._resolved_future(b"cached")

        self.assertTrue(future.done())
        self.assertEqual(future.result(), b"cached")

    def test_blob_request_fails_on_disconnect(self):
        future = self.mumble._await_blob("comment", 7, RequestBlobCmd(user_comment_hashes=[7]))

        self.mumble._cleanup_pending_commands()

        self.assertTrue(future.done())
        with self.assertRaises(RuntimeError):
            future.result()
        self.assertEqual(self.mumble._pending_blobs, {})

    def test_get_avatar_end_to_end(self):
        # Real BlobDB and User: first call requests and waits, second call (now cached)
        # resolves immediately.
        with patch("pymumble_typed.mumble.ControlStack"), patch("pymumble_typed.mumble.VoiceStack"):
            mumble = Mumble(host="h", user="u", logger=MagicMock())

        create = Mumble_pb2.UserState()
        create.session = 5
        create.hash = "userhash"
        create.texture_hash = b"\x01\x02"  # has an avatar, but its data is not cached yet
        mumble._dispatch_control_message(MessageType.UserState, create.SerializeToString())
        user = mumble.users[5]

        pending = user.get_avatar()
        self.assertFalse(pending.done())

        deliver = Mumble_pb2.UserState()
        deliver.session = 5
        deliver.texture = b"PNGDATA"
        mumble._dispatch_control_message(MessageType.UserState, deliver.SerializeToString())

        self.assertTrue(pending.done())
        self.assertEqual(pending.result(), b"PNGDATA")

        # Now cached: a second request resolves immediately without waiting.
        cached = user.get_avatar()
        self.assertTrue(cached.done())
        self.assertEqual(cached.result(), b"PNGDATA")

    def _connected_mumble_with_self_in(self, channel_id):
        # Build a real Mumble whose "myself" user sits in `channel_id`, plus that channel.
        with patch("pymumble_typed.mumble.ControlStack"), patch("pymumble_typed.mumble.VoiceStack"):
            mumble = Mumble(host="h", user="u", logger=MagicMock())
        me = Mumble_pb2.UserState()
        me.session = 1
        me.hash = "selfhash"
        me.channel_id = channel_id
        mumble._dispatch_control_message(MessageType.UserState, me.SerializeToString())
        mumble.users.set_myself(1)
        for cid in {channel_id, channel_id + 1}:
            cs = Mumble_pb2.ChannelState()
            cs.channel_id = cid
            cs.name = f"Channel{cid}"
            mumble._dispatch_control_message(MessageType.ChannelState, cs.SerializeToString())
        return mumble

    def test_move_in_to_current_channel_resolves_immediately(self):
        # A no-op move (the bot is already in the target channel) is never echoed by the
        # server, so it must resolve immediately and not be left pending.
        mumble = self._connected_mumble_with_self_in(10)
        mumble._control.send_command.reset_mock()

        future = mumble.users.myself.move_in(mumble.channels[10])

        self.assertTrue(future.done())
        self.assertIs(future.result(), mumble.users.myself)
        self.assertEqual(len(mumble._pending_commands), 0)
        mumble._control.send_command.assert_not_called()

    def test_channel_move_in_to_current_channel_resolves_immediately(self):
        # Same no-op short-circuit when moving via Channel.move_in().
        mumble = self._connected_mumble_with_self_in(10)
        mumble._control.send_command.reset_mock()

        future = mumble.channels[10].move_in()

        self.assertTrue(future.done())
        self.assertIs(future.result(), mumble.users.myself)
        self.assertEqual(len(mumble._pending_commands), 0)
        mumble._control.send_command.assert_not_called()

    def test_move_in_to_other_channel_is_tracked(self):
        # A real move (different channel) is still sent and tracked until the echo arrives.
        mumble = self._connected_mumble_with_self_in(10)
        mumble._control.send_command.reset_mock()

        future = mumble.users.myself.move_in(mumble.channels[11])

        self.assertFalse(future.done())
        self.assertEqual(len(mumble._pending_commands), 1)
        mumble._control.send_command.assert_called_once()

    def test_cleanup_rejects_futures_on_disconnect(self):
        future = self.mumble.execute_command(self._user_state_command(42), blocking=False)
        self.assertEqual(len(self.mumble._pending_commands), 1)

        self.mumble._cleanup_pending_commands()

        self.assertTrue(future.done())
        with self.assertRaises(RuntimeError):
            future.result()
        self.assertEqual(len(self.mumble._pending_commands), 0)


if __name__ == "__main__":
    unittest.main()
