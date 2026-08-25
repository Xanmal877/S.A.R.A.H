import hashlib
import hmac
import json
import time

MAX_CLOCK_SKEW = 60  # seconds - blunts simple replay of captured messages


class ProtocolError(Exception):
    pass


def _sign(secret: bytes, payload: bytes) -> str:
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def encode_message(secret: bytes, msg_type: str, data: dict = None) -> bytes:
    envelope = {"type": msg_type, "data": data or {}, "ts": time.time()}
    payload = json.dumps(envelope, sort_keys=True).encode("utf-8")
    sig = _sign(secret, payload)
    return (json.dumps({"payload": envelope, "sig": sig}) + "\n").encode("utf-8")


def decode_message(secret: bytes, raw: bytes) -> dict:
    """Verifies the HMAC signature and clock skew, then returns the envelope
    (dict with "type"/"data"/"ts"). Raises ProtocolError on any failure -
    callers must treat that as a hard rejection, not a retry-able error."""
    try:
        frame = json.loads(raw.decode("utf-8"))
        envelope = frame["payload"]
        sig = frame["sig"]
    except (json.JSONDecodeError, KeyError, UnicodeDecodeError) as e:
        raise ProtocolError(f"Malformed message: {e}")

    payload = json.dumps(envelope, sort_keys=True).encode("utf-8")
    expected_sig = _sign(secret, payload)
    if not hmac.compare_digest(sig, expected_sig):
        raise ProtocolError("Invalid signature")

    if abs(time.time() - envelope.get("ts", 0)) > MAX_CLOCK_SKEW:
        raise ProtocolError("Message timestamp outside allowed clock skew")

    return envelope
