"""
routes/counters.py — Core CRUD endpoints for Suanpan counters.

URL scheme (verb-first, matching the reference API):
  POST /create/{namespace}/{key}   — create a new counter
  POST /create                     — create a counter with a random namespace+key
  GET  /get/{namespace}/{key}      — read current value
  GET  /get/{namespace}/{key}/shield — read current value as SVG
  GET  /hit/{namespace}/{key}      — increment by 1
  GET  /hit/{namespace}/{key}/shield — increment by 1 and return SVG
  POST /update/{namespace}/{key}   — increment/decrement by ?value=N  (requires token)
  POST /set/{namespace}/{key}      — overwrite with ?value=N          (requires token)
  POST /reset/{namespace}/{key}    — set back to 0                    (requires token)
  POST /delete/{namespace}/{key}   — delete counter                   (requires token)
  GET  /info/{namespace}/{key}     — metadata (value, TTL, is_genuine)
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Header, Query, Response

import core.database as db
from core.constants import BASE_TTL_SECONDS, MAX_INT
from utils.badges import BadgeOptions, generate_badge
from utils.keys import (
    build_admin_key,
    build_db_key,
    generate_random_string,
    parse_namespace_key,
)

router = APIRouter()

# ── Lua scripts (atomic, single RTT) ─────────────────────────────────────────

# Atomically create counter + admin key only if the counter does NOT exist yet.
# Returns 1 on success, 0 if the counter already existed.
_LUA_CREATE = """
if redis.call("SET", KEYS[1], ARGV[1], "NX", "EX", ARGV[2]) == false then
  return 0
end
redis.call("SET", KEYS[2], ARGV[3])
return 1
"""

# Atomically increment only if the key exists; returns the new value or nil.
_LUA_INCRBY_IF_EXISTS = """
if redis.call("EXISTS", KEYS[1]) == 0 then
  return nil
end
return redis.call("INCRBY", KEYS[1], ARGV[1])
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _check_admin(stored: str | None, provided: str | None) -> None:
    """
    Validate that *provided* matches the stored admin token.

    Raises:
        HTTP 400 — counter is genuine (auto-created via /hit, no admin token).
        HTTP 401 — token mismatch.
    """
    if stored is None:
        raise HTTPException(
            status_code=400,
            detail="This counter is genuine and does not have an admin key.",
        )
    if stored != provided:
        raise HTTPException(status_code=401, detail="Token is invalid.")


async def get_token(
    token: Annotated[str | None, Query()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> str | None:
    """Extract the admin token from ``?token=`` or an ``Authorization: Bearer`` header."""
    if token:
        return token
    if authorization and authorization.startswith("Bearer "):
        return authorization.split(" ", 1)[1]
    return None


def get_badge_options(
    bgcolor: str = Query("007ec6", description="Badge background hex color"),
    textcolor: str = Query("fff", description="Badge text hex color"),
    text: str = Query("counter", description="Badge label"),
    style: str = Query(
        "flat",
        description=(
            "flat, flat-square, plastic, flat-simple, "
            "flat-square-simple, or plastic-simple"
        ),
    ),
    fontsize: str = Query("11", description="Font size; values <= 3 use 11"),
    font: str = Query("verdana", description="Supported font family name"),
) -> BadgeOptions:
    """Collect Abacus-compatible shield query parameters."""
    return BadgeOptions(bgcolor, textcolor, text, style, fontsize, font)


def _shield_response(value: int, options: BadgeOptions, *, no_cache: bool) -> Response:
    try:
        svg = generate_badge(value, options)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    headers = {}
    if no_cache:
        headers["Cache-Control"] = "max-age=0, no-cache, no-store, must-revalidate"
    return Response(content=svg, media_type="image/svg+xml", headers=headers)


async def _get_counter_value(namespace: str, key: str) -> int:
    namespace, key = parse_namespace_key(namespace, key)
    db_key = build_db_key(namespace, key)

    val = await db.client.get(db_key)
    if val is None:
        raise HTTPException(status_code=404, detail="Key not found")
    return int(val)


async def _hit_counter_value(namespace: str, key: str) -> int:
    namespace, key = parse_namespace_key(namespace, key)
    db_key = build_db_key(namespace, key)

    val = await db.client.incr(db_key)
    if val > MAX_INT:
        await db.client.decr(db_key)
        raise HTTPException(
            status_code=400,
            detail=f"Value is too large. Max value is {MAX_INT}",
        )

    await db.client.expire(db_key, BASE_TTL_SECONDS)
    return val


# ── /create ───────────────────────────────────────────────────────────────────

@router.post("/create/{namespace}/{key}", status_code=201, tags=["counters"])
async def create(
    namespace: str,
    key: str,
    initializer: int = Query(0, description="Initial counter value"),
    admin_token: str | None = Query(None, description="Custom admin token (optional — one is generated if omitted)"),
):
    """Create a new counter. Returns the admin token needed for privileged operations."""
    namespace, key = parse_namespace_key(namespace, key)
    db_key = build_db_key(namespace, key)
    adm_key = build_admin_key(db_key)

    chosen_token = admin_token or str(uuid.uuid4())

    result = await db.client.eval(
        _LUA_CREATE,
        2,  # numkeys
        db_key, adm_key,
        initializer, BASE_TTL_SECONDS, chosen_token,
    )

    if result == 0:
        raise HTTPException(status_code=409, detail="Key already exists, please use a different key.")

    return {"namespace": namespace, "key": key, "value": initializer, "admin_key": chosen_token}


@router.post("/create", status_code=201, tags=["counters"])
async def create_random():
    """Create a counter with a randomly generated namespace and key."""
    namespace = generate_random_string(16)
    key = generate_random_string(16)

    db_key = build_db_key(namespace, key, skip_validation=True)
    adm_key = build_admin_key(db_key)
    chosen_token = str(uuid.uuid4())

    await db.client.eval(
        _LUA_CREATE,
        2,
        db_key, adm_key,
        0, BASE_TTL_SECONDS, chosen_token,
    )

    return {"namespace": namespace, "key": key, "value": 0, "admin_key": chosen_token}


# ── /get ──────────────────────────────────────────────────────────────────────

@router.get("/get/{namespace}/{key}", tags=["counters"])
async def get(namespace: str, key: str):
    """Return the current value of a counter."""
    return {"value": await _get_counter_value(namespace, key)}


@router.get("/get/{namespace}/{key}/shield", tags=["counters"])
async def get_shield(
    namespace: str,
    key: str,
    options: BadgeOptions = Depends(get_badge_options),
):
    """Return the current counter value as an SVG shield."""
    value = await _get_counter_value(namespace, key)
    return _shield_response(value, options, no_cache=False)


# ── /hit ──────────────────────────────────────────────────────────────────────

@router.get("/hit/{namespace}/{key}", tags=["counters"])
async def hit(namespace: str, key: str):
    """Increment the counter by 1 and return the new value."""
    return {"value": await _hit_counter_value(namespace, key)}


@router.get("/hit/{namespace}/{key}/shield", tags=["counters"])
async def hit_shield(
    namespace: str,
    key: str,
    options: BadgeOptions = Depends(get_badge_options),
):
    """Increment the counter and return its new value as an SVG shield."""
    value = await _hit_counter_value(namespace, key)
    return _shield_response(value, options, no_cache=True)


# ── /update ───────────────────────────────────────────────────────────────────

@router.post("/update/{namespace}/{key}", tags=["counters"])
async def update(
    namespace: str,
    key: str,
    value: int = Query(..., description="Amount to increment (negative = decrement)"),
    token: str | None = Depends(get_token),
):
    """Increment (or decrement) the counter by an arbitrary integer. Requires the admin token."""
    if value == 0:
        raise HTTPException(
            status_code=400,
            detail="Changing value by 0 does nothing — provide a non-zero value.",
        )

    namespace, key = parse_namespace_key(namespace, key)
    db_key = build_db_key(namespace, key)
    adm_key = build_admin_key(db_key)

    stored_token = await db.client.get(adm_key)
    _check_admin(stored_token, token)

    new_val = await db.client.eval(_LUA_INCRBY_IF_EXISTS, 1, db_key, value)

    if new_val is None:
        raise HTTPException(
            status_code=409,
            detail="Key does not exist. Create it first using /create.",
        )

    return {"value": int(new_val)}


# ── /set ──────────────────────────────────────────────────────────────────────

@router.post("/set/{namespace}/{key}", tags=["counters"])
async def set_value(
    namespace: str,
    key: str,
    value: int = Query(..., description="New value to set the counter to"),
    token: str | None = Depends(get_token),
):
    """Overwrite the counter with a specific value. Requires the admin token."""
    namespace, key = parse_namespace_key(namespace, key)
    db_key = build_db_key(namespace, key)
    adm_key = build_admin_key(db_key)

    stored_token = await db.client.get(adm_key)
    _check_admin(stored_token, token)

    # SET XX — only update if the counter key already exists.
    updated = await db.client.set(db_key, value, xx=True, ex=BASE_TTL_SECONDS)
    if not updated:
        raise HTTPException(status_code=409, detail="Key does not exist, please use a different key.")

    return {"value": value}


# ── /reset ────────────────────────────────────────────────────────────────────

@router.post("/reset/{namespace}/{key}", tags=["counters"])
async def reset(
    namespace: str,
    key: str,
    token: str | None = Depends(get_token),
):
    """Reset the counter back to 0. Requires the admin token."""
    namespace, key = parse_namespace_key(namespace, key)
    db_key = build_db_key(namespace, key)
    adm_key = build_admin_key(db_key)

    stored_token = await db.client.get(adm_key)
    _check_admin(stored_token, token)

    updated = await db.client.set(db_key, 0, xx=True, ex=BASE_TTL_SECONDS)
    if not updated:
        raise HTTPException(status_code=409, detail="Key does not exist, please use a different key.")

    return {"value": 0}


# ── /delete ───────────────────────────────────────────────────────────────────

@router.post("/delete/{namespace}/{key}", tags=["counters"])
async def delete(
    namespace: str,
    key: str,
    token: str | None = Depends(get_token),
):
    """Permanently delete a counter and its admin token. Requires the admin token."""
    namespace, key = parse_namespace_key(namespace, key)
    db_key = build_db_key(namespace, key)
    adm_key = build_admin_key(db_key)

    stored_token = await db.client.get(adm_key)
    _check_admin(stored_token, token)

    await db.client.delete(db_key, adm_key)
    return {"status": "ok", "message": f"Deleted {db_key}"}


# ── /info ─────────────────────────────────────────────────────────────────────

@router.get("/info/{namespace}/{key}", tags=["counters"])
async def info(namespace: str, key: str):
    """Return metadata: current value, TTL, and whether the counter is genuine."""
    namespace, key = parse_namespace_key(namespace, key)
    db_key = build_db_key(namespace, key)
    adm_key = build_admin_key(db_key)

    # Pipeline: GET + EXISTS(admin) + TTL — one round trip.
    async with db.client.pipeline(transaction=False) as pipe:
        pipe.get(db_key)
        pipe.exists(adm_key)
        pipe.ttl(db_key)
        val_raw, admin_exists, ttl = await pipe.execute()

    exists = ttl != -2  # -2 means the key does not exist in Valkey
    value = int(val_raw) if val_raw is not None else -1

    # A "genuine" counter has NO admin key — it was auto-created (e.g. via /hit)
    # rather than explicitly managed via /create.
    is_genuine = admin_exists == 0

    return {
        "value": value,
        "full_key": db_key,
        "is_genuine": is_genuine,
        "expires_in": ttl,
        "exists": exists,
    }
