import re
import secrets
from fastapi import HTTPException
from core.constants import MIN_LENGTH, MAX_LENGTH

# Alphanumeric plus _  -  .
_VALID_PATTERN = re.compile(r"^[A-Za-z0-9_\-.]{3,64}$")

# ── Key-format helpers ────────────────────────────────────────────────────────
# Counter keys  →  K:<namespace>:<key>
# Admin keys    →  A:<namespace>:<key>

def _validate_segment(value: str, label: str) -> None:
    """Raise HTTP 400 if *value* is not a valid namespace or key segment."""
    if len(value) < MIN_LENGTH or len(value) > MAX_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {label}: length must be between {MIN_LENGTH} and {MAX_LENGTH} characters inclusive",
        )
    if not _VALID_PATTERN.match(value):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {label}: must match pattern ^[A-Za-z0-9_\\-.]{{{MIN_LENGTH},{MAX_LENGTH}}}$",
        )


def build_db_key(namespace: str, key: str, skip_validation: bool = False) -> str:
    """Return the canonical Valkey counter key ``K:<namespace>:<key>``."""
    if not skip_validation:
        _validate_segment(namespace, "namespace")
        _validate_segment(key, "key")
    return f"K:{namespace}:{key}"


def build_admin_key(db_key: str) -> str:
    """
    Derive the admin-key from a counter db_key.
    ``K:ns:k`` → ``A:ns:k``
    """
    return "A:" + db_key.removeprefix("K:")


# ── Request helpers ───────────────────────────────────────────────────────────

def parse_namespace_key(namespace: str, key: str) -> tuple[str, str]:
    """
    FastAPI path parameters arrive already decoded; just strip stray slashes.
    Returns ``(namespace, key)`` or raises HTTP 400.
    """
    namespace = namespace.strip("/")
    key = key.strip("/")

    if not namespace or not key:
        raise HTTPException(status_code=400, detail="Namespace and key are required")
    if "/" in key:
        raise HTTPException(
            status_code=404,
            detail="Route not found. Use /<namespace>/<key> path format.",
        )

    return namespace, key


# ── Random-string helper ──────────────────────────────────────────────────────

_CHARSET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"

def generate_random_string(length: int = 16) -> str:
    """Return a URL-safe random string of *length* characters."""
    return "".join(secrets.choice(_CHARSET) for _ in range(length))
