from __future__ import annotations

import struct

# X's /onboarding/web (jf.x.com) endpoints don't answer JSON, they answer JetFuel: a binary
# stream of length-prefixed frames carrying varint-length key/value pairs. There's no schema
# in the response, so instead of decoding the whole thing we scan for the few keys we need
# (session_token, errors, the next action path) and read the value that follows each one.


def _read_varint(buf: bytes, pos: int):
    val = 0
    shift = 0
    while pos < len(buf):
        byte = buf[pos]
        pos += 1
        val |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return val, pos
        shift += 7
        if shift > 63:
            return None, pos
    return None, pos


def split_frames(data: bytes):
    frames = []
    pos = 0
    while pos + 4 <= len(data):
        (length,) = struct.unpack_from("<I", data, pos)
        pos += 4
        if pos + length > len(data):
            break
        frames.append(data[pos:pos + length])
        pos += length
    return frames


def _extract_value_after_key(buf: bytes, key: str):
    key_bytes = key.encode("utf-8")
    # Keys are shorter than 128 bytes, so their length prefix is a single-byte varint.
    anchor = bytes([len(key_bytes)]) + key_bytes
    start = 0
    while True:
        idx = buf.find(anchor, start)
        if idx == -1:
            return None
        after = idx + len(anchor)
        length, npos = _read_varint(buf, after)
        if length is not None and 0 <= length <= len(buf) - npos:
            try:
                return buf[npos:npos + length].decode("utf-8")
            except UnicodeDecodeError:
                pass
        start = idx + 1


def _has_alnum(value: str) -> bool:
    return any(char.isalnum() for char in value)


def _find_next_action(buf: bytes):
    needle = b"/onboarding/web/actions/"
    found = []
    start = 0
    while True:
        idx = buf.find(needle, start)
        if idx == -1:
            break
        end = idx
        while end < len(buf) and 0x20 <= buf[end] < 0x7F and buf[end] not in b'"\\':
            end += 1
        try:
            found.append(buf[idx:end].decode("utf-8"))
        except UnicodeDecodeError:
            pass
        start = idx + 1
    # begin_login points at whatever subtask comes next, prefer the password one when it's there.
    for action in found:
        if action.endswith("login_enter_password"):
            return action
    return found[0] if found else None


def parse_response(body):
    if isinstance(body, str):
        body = body.encode("latin-1", errors="ignore")

    result = {"session_token": None, "next_action": None, "error_message": None}

    session = _extract_value_after_key(body, "session_token")
    if session:
        result["session_token"] = session

    errors = _extract_value_after_key(body, "errors")
    message = _extract_value_after_key(body, "message")
    missing = _extract_value_after_key(body, "missing_account")
    # A missing account isn't returned as an error string, it's a separate key, so surface it
    # as one instead of letting begin_login look like it silently gave nothing back.
    if missing and _has_alnum(missing):
        result["error_message"] = "user_not_found:" + missing
    elif errors and _has_alnum(errors):
        result["error_message"] = errors
    elif message and _has_alnum(message):
        result["error_message"] = message

    result["next_action"] = _find_next_action(body)
    return result
