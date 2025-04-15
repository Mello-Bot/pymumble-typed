from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from logging import Logger

import sqlite3
from base64 import b64encode, b64decode
from threading import Lock


class BlobDB:
    def __init__(self, logger: Logger, path: str = ":memory:"):
        self._logger = logger.getChild(self.__class__.__name__)
        self._path = path
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._lock = Lock()
        self._cursor = self._db.cursor()
        self._cursor.execute(
            "CREATE TABLE IF NOT EXISTS users ("
            "user_hash TEXT PRIMARY KEY,"
            "comment_hash TEXT,"
            "comment TEXT,"
            "texture_hash TEXT,"
            "texture TEXT)"
        )
        self._cursor.execute(
            "CREATE TABLE IF NOT EXISTS channels ("
            "channel_id INTEGER PRIMARY KEY,"
            "description_hash TEXT,"
            "description TEXT)"
        )
        self._db.commit()
        self._logger.debug("BlobDB initialized")

    def update_user_comment(self, user_hash: str, comment_hash: str, comment: str):
        self._logger.debug(f"updating user {user_hash} comment: {comment_hash}")
        self._lock.acquire()
        try:
            self._cursor.execute(
                "INSERT INTO users(user_hash, comment_hash, comment) "
                "VALUES(:user_hash,:comment_hash,:comment) "
                "ON CONFLICT(user_hash) "
                "DO UPDATE SET comment_hash=:comment_hash, comment=:comment;",
                {"user_hash": user_hash, "comment_hash": comment_hash, "comment": comment}
            )
            self._db.commit()
            self._logger.debug(f"updated user {user_hash} comment: {comment_hash}")
        except:
            self._logger.error("Failed to update user comment", exc_info=True)
        self._lock.release()

    def get_user_comment(self, user_hash: str) -> str:
        self._lock.acquire()
        result = None
        try:
            result = self._cursor.execute("SELECT comment "
                                          "FROM users "
                                          "WHERE user_hash=:user_hash",
                                          {"user_hash": user_hash}).fetchone()

        except:
            self._logger.error("Failed to get user comment", exc_info=True)
        self._lock.release()
        if not result:
            return ""
        return result[0]

    def is_user_comment_updated(self, user_hash: str, comment_hash: str) -> bool:
        self._lock.acquire()
        try:
            result = self._cursor.execute(
                "SELECT comment_hash "
                "FROM users "
                "WHERE user_hash=:user_hash AND comment_hash=:comment_hash",
                {"user_hash": user_hash, "comment_hash": comment_hash}).fetchone()
        except:
            self._logger.error("Failed to update user comment", exc_info=True)
            result = False
        self._lock.release()
        return not not result

    def update_user_texture(self, user_hash: str, texture_hash: str, texture: bytes):
        self._logger.debug(f"updating user {user_hash} texture: {texture_hash}")
        self._lock.acquire()
        try:
            self._cursor.execute(
                "INSERT INTO users(user_hash, texture_hash, texture) "
                "VALUES(:user_hash,:texture_hash,:texture) "
                "ON CONFLICT(user_hash) "
                "DO UPDATE SET texture_hash=:texture_hash, texture=:texture;",
                {"user_hash": user_hash, "texture_hash": texture_hash, "texture": b64encode(texture)}
            )
            self._db.commit()
            self._logger.debug(f"updated user {user_hash} texture: {texture_hash}")
        except:
            self._logger.error("Failed to update user texture", exc_info=True)
        self._lock.release()

    def get_user_texture(self, user_hash: str) -> bytes:
        self._lock.acquire()
        result = None
        try:
            result = self._cursor.execute("SELECT texture "
                                          "FROM users "
                                          "WHERE user_hash=:user_hash",
                                          {"user_hash": user_hash}).fetchone()
        except:
            self._logger.error("Failed to get user texture", exc_info=True)
        self._lock.release()
        if not result:
            return bytes()
        return b64decode(result[0])

    def is_user_texture_updated(self, user_hash: str, texture_hash: str) -> bool:

        self._lock.acquire()
        try:
            result = self._cursor.execute(
                "SELECT texture_hash "
                "FROM users "
                "WHERE user_hash=:user_hash AND texture_hash=:texture_hash",
                {"user_hash": user_hash, "texture_hash": texture_hash}).fetchone()
        except:
            self._logger.error("Failed to check user comment", exc_info=True)
            result = False
        self._lock.release()
        return not not result

    def update_channel_description(self, channel_id: int, description_hash: str, description: str):
        self._logger.debug(f"updating channel {channel_id} description: {description_hash}")
        self._lock.acquire()
        try:
            self._cursor.execute(
                "INSERT INTO channels(channel_id, description_hash, description) "
                "VALUES(:channel_id,:description_hash,:description) "
                "ON CONFLICT(channel_id) "
                "DO UPDATE SET description_hash=:description_hash, description=:description;",
                {"channel_id": channel_id, "description_hash": description_hash, "description": description}
            )
            self._db.commit()
            self._logger.debug(f"Updated channel {channel_id} description: {description_hash}")
        except:
            self._logger.error("Failed to update channel description", exc_info=True)
        self._lock.release()

    def get_channel_description(self, channel_id: int) -> str:
        self._lock.acquire()
        result = None
        try:
            result = self._cursor.execute("SELECT description "
                                          "FROM channels "
                                          "WHERE channel_id=:channel_id",
                                          {"channel_id": channel_id}).fetchone()

        except:
            self._logger.error("Failed to update get channel description", exc_info=True)
        self._lock.release()
        if not result:
            return ""
        return result[0]

    def is_channel_description_updated(self, channel_id: int, description_hash: str) -> bool:
        self._lock.acquire()
        try:
            result = self._cursor.execute(
                "SELECT description_hash "
                "FROM channels "
                "WHERE channel_id=:channel_id AND description_hash=:description_hash",
                {"channel_id": channel_id, "description_hash": description_hash}).fetchone()
        except:
            self._logger.error("Failed to check channel description", exc_info=True)
            result = False
        self._lock.release()
        return not not result
