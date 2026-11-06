import unittest
from unittest.mock import MagicMock

from pymumble_typed.blobs import BlobDB


class TestBlobDB(unittest.TestCase):
    def setUp(self):
        self.db = BlobDB(MagicMock(), ":memory:")

    def test_get_user_texture_with_null_column_returns_empty_bytes(self):
        # Writing only the comment leaves the texture column NULL; reading it must not
        # crash on b64decode(None) but return the empty default.
        self.db.update_user_comment("user", "commenthash", "a comment")

        self.assertEqual(self.db.get_user_texture("user"), b"")

    def test_get_user_comment_with_null_column_returns_empty_string(self):
        self.db.update_user_texture("user", "texturehash", b"data")

        self.assertEqual(self.db.get_user_comment("user"), "")

    def test_get_channel_description_missing_returns_empty_string(self):
        self.assertEqual(self.db.get_channel_description(123), "")

    def test_round_trip_still_works(self):
        self.db.update_user_texture("user", "texturehash", b"avatar-bytes")
        self.db.update_user_comment("user", "commenthash", "a comment")
        self.db.update_channel_description(1, "deschash", "a description")

        self.assertEqual(self.db.get_user_texture("user"), b"avatar-bytes")
        self.assertEqual(self.db.get_user_comment("user"), "a comment")
        self.assertEqual(self.db.get_channel_description(1), "a description")


if __name__ == "__main__":
    unittest.main()
