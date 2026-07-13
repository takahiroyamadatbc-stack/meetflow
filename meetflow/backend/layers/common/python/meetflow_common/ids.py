import secrets
import uuid


def generate_id() -> str:
    """Opaque unique id for entities referenced only internally/by API path
    (communityId, eventId, candidateId, placeId, etc.) -- doesn't need to be
    unguessable, just unique.
    """
    return uuid.uuid4().hex


def generate_invite_token() -> str:
    """Unguessable token for invite URLs (INVITE#{token}, F-102).

    Unlike `generate_id`, this ends up in a URL anyone with the link can use
    to join a community, so it needs to be drawn from a CSPRNG rather than a
    plain UUID4 (which is fine for opacity but not designed as a security
    token).
    """
    return secrets.token_urlsafe(24)
