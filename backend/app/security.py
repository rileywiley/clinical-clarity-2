"""Password hashing (Argon2id) and signed cookie session helpers.

Cookie sessions are deliberately chosen over a server-side session table — the auth
module is described as "designed for future SSO" in PRD §4.2, and a signed cookie
keeps the abstraction thin so swapping in SAML/OIDC later is a focused change.
"""

from __future__ import annotations

from typing import TypedDict
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner

from app.config import get_settings

_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(stored_hash: str, plain: str) -> bool:
    try:
        _hasher.verify(stored_hash, plain)
        return True
    except VerifyMismatchError:
        return False


class SessionPayload(TypedDict):
    user_id: str
    org_id: str


def _signer() -> TimestampSigner:
    return TimestampSigner(get_settings().session_secret, salt="vfp.session.v1")


def serialize_session(user_id: UUID, org_id: UUID) -> str:
    raw = f"{user_id}:{org_id}".encode()
    return _signer().sign(raw).decode()


def deserialize_session(token: str) -> SessionPayload | None:
    try:
        raw = _signer().unsign(token, max_age=get_settings().session_max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None
    try:
        user_id_str, org_id_str = raw.decode().split(":", 1)
        # Validate UUID shape — anything malformed = unauthenticated.
        UUID(user_id_str)
        UUID(org_id_str)
    except (ValueError, AttributeError):
        return None
    return {"user_id": user_id_str, "org_id": org_id_str}
