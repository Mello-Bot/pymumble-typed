class PermissionDeniedError(Exception):
    def __init__(self, deny_type: int, reason: str, channel_id: int | None = None, session: int | None = None):
        self.deny_type = deny_type
        self.reason = reason
        self.channel_id = channel_id
        self.session = session
        super().__init__(f"Permission denied (type={deny_type}, reason={reason})")


class ConnectionLostError(RuntimeError):
    """
    Raised on a pending command's future when the connection is lost before the
    server confirmed (or rejected) the command."""
