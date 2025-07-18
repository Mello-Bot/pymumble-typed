LOOP_RATE = 0.01
READ_BUFFER_SIZE = 4096


class ConnectionRejectedError(Exception):
    """Thrown when server rejects the connection"""

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


