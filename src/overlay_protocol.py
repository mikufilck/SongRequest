"""Bounded EOF-delimited local socket command (the sender closes after sendall)."""
import json
import time

MAX_COMMAND_BYTES = 1024 * 1024


def receive_command(connection, timeout=1.0, limit=MAX_COMMAND_BYTES):
    deadline = time.monotonic() + timeout
    chunks = []
    size = 0
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("overlay command timed out")
        connection.settimeout(remaining)
        chunk = connection.recv(min(16384, limit + 1 - size))
        if not chunk:
            break
        size += len(chunk)
        if size > limit:
            raise ValueError("overlay command too large")
        chunks.append(chunk)
    command = json.loads(b"".join(chunks).decode("utf-8"))
    if not isinstance(command, dict):
        raise ValueError("overlay command must be an object")
    return command
