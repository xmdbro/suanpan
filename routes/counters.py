"""
routes/counters.py — Core CRUD endpoints for Suanpan counters.

URL scheme (mirrors Abacus):
  POST /create/{namespace}/{key}   — create a new counter
  POST /create                     — create a counter with a random namespace+key
  GET  /{namespace}/{key}/hit      — increment by 1
  GET  /{namespace}/{key}/get      — read current value
  GET  /{namespace}/{key}/update   — increment/decrement by ?value=N
  GET  /{namespace}/{key}/set      — overwrite with ?value=N  (requires admin_key)
  GET  /{namespace}/{key}/reset    — set back to 0           (requires admin_key)
  DELETE /{namespace}/{key}        — delete counter          (requires admin_key)
  GET  /{namespace}/{key}/info     — metadata (value, TTL, is_genuine)
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

import core.database as db
from core.constants import BASE_TTL_SECONDS, MAX_INT
from utils.keys import (
    build_admin_key,
    build_db_key,
    generate_random_string,
    parse_namespace_key,
)

router = APIRouter()

# ── Lua scripts (atomic, single RTT) ─────────────────────────────────────────

# Atomically create counter + admin key only if counter does NOT exist yet.
# Returns 1 on success, 0 if counter already existed.
_LUA_CREATE = """
if redis.call("SET", KEYS[1], ARGV[1], "NX", "EX", ARGV[2]) == false then
  return 0
end
redis.call("SET", KEYS[2], ARGV[3])
return 1
"""

# Atomically increment only if key exists; returns new value or nil.
_LUA_INCRBY_IF_EXISTS = """
if redis.call("EXISTS", KEYS[1]) == 0 then
  return nil
end
return redis.call("INCRBY", KEYS[1], ARGV[1])
"""


# ── Helper ────────────────────────────────────────────────────────────────────

def _check_admin(stored: str | None, provided: str | None) -> None:
    """Raise 403 if the provided admin key doesn't match the stored one."""
    if not stored or stored != provided:
        raise HTTPException(status_code=403, detail="Invalid or missing admin_key")


# ── /create ───────────────────────────────────────────────────────────────────

@router.post("/create/{namespace}/{key}", status_code=201, tags=["counters"])
async def create(
    namespace: str,
    key: str,
    initializer: int = Query(0, description="Initial counter value"),
    admin_key: str | None = Query(None, description="Custom admin key (optional — one is generated if omitted)"),
):
    """Create a new counter. Returns the admin key needed for privileged operations."""
    namespace, key = parse_namespace_key(namespace, key)
    db_key = build_db_key(namespace, key)
    adm_key = build_admin_key(db_key)

    chosen_admin = admin_key or str(uuid.uuid4())

    result = await db.client.eval(
        _LUA_CREATE,
        2,  # numkeys
        db_key, adm_key,
        initializer, BASE_TTL_SECONDS, chosen_admin,
    )

    if result == 0:
        raise HTTPException(status_code=409, detail="Key already exists, please use a different key.")

    return {"namespace": namespace, "key": key, "value": initializer, "admin_key": chosen_admin}


@router.post("/create", status_code=201, tags=["counters"])
async def create_random():
    """Create a counter with a randomly generated namespace and key."""
    namespace = generate_random_string(16)
    key = generate_random_string(16)

    db_key = build_db_key(namespace, key, skip_validation=True)
    adm_key = build_admin_key(db_key)
    chosen_admin = str(uuid.uuid4())

    await db.client.eval(
        _LUA_CREATE,
        2,
        db_key, adm_key,
        0, BASE_TTL_SECONDS, chosen_admin,
    )

    return {"namespace": namespace, "key": key, "value": 0, "admin_key": chosen_admin}


# ── /get ──────────────────────────────────────────────────────────────────────

@router.get("/{namespace}/{key}/get", tags=["counters"])
async def get(namespace: str, key: str):
    """Return the current value of a counter."""
    namespace, key = parse_namespace_key(namespace, key)
    db_key = build_db_key(namespace, key)

    val = await db.client.get(db_key)
    if val is None:
        raise HTTPException(status_code=404, detail="Key not found")

    return {"value": int(val)}


# ── /hit ──────────────────────────────────────────────────────────────────────

@router.get("/{namespace}/{key}/hit", tags=["counters"])
async def hit(namespace: str, key: str):
    """Increment the counter by 1 and return the new value."""
    namespace, key = parse_namespace_key(namespace, key)
    db_key = build_db_key(namespace, key)

    val = await db.client.incr(db_key)

    if val > MAX_INT:
        # Roll back and refuse
        await db.client.decr(db_key)
        raise HTTPException(
            status_code=400,
            detail=f"Value is too large. Max value is {MAX_INT}",
        )

    # Lazily set/refresh TTL — the key may have been auto-created by INCR
    await db.client.expire(db_key, BASE_TTL_SECONDS)

    return {"value": val}


# ── /update ───────────────────────────────────────────────────────────────────

@router.get("/{namespace}/{key}/update", tags=["counters"])
async def update(
    namespace: str,
    key: str,
    value: int = Query(..., description="Amount to increment (negative = decrement)"),
):
    """Increment (or decrement) the counter by an arbitrary integer."""
    if value == 0:
        raise HTTPException(
            status_code=400,
            detail="Changing value by 0 does nothing — provide a non-zero value.",
        )

    namespace, key = parse_namespace_key(namespace, key)
    db_key = build_db_key(namespace, key)

    new_val = await db.client.eval(_LUA_INCRBY_IF_EXISTS, 1, db_key, value)

    if new_val is None:
        raise HTTPException(
            status_code=409,
            detail="Key does not exist. Create it first using /create.",
        )

    return {"value": int(new_val)}


# ── /set ──────────────────────────────────────────────────────────────────────

@router.get("/{namespace}/{key}/set", tags=["counters"])
async def set_value(
    namespace: str,
    key: str,
    value: int = Query(..., description="New value to set the counter to"),
    admin_key: str | None = Query(None),
):
    """Overwrite the counter with a specific value. Requires the admin key."""
    namespace, key = parse_namespace_key(namespace, key)
    db_key = build_db_key(namespace, key)
    adm_key = build_admin_key(db_key)

    stored_admin = await db.client.get(adm_key)
    _check_admin(stored_admin, admin_key)

    # SET XX — only update if key already exists
    updated = await db.client.set(db_key, value, xx=True, ex=BASE_TTL_SECONDS)
    if not updated:
        raise HTTPException(status_code=409, detail="Key does not exist, please use a different key.")

    return {"value": value}


# ── /reset ────────────────────────────────────────────────────────────────────

@router.get("/{namespace}/{key}/reset", tags=["counters"])
async def reset(
    namespace: str,
    key: str,
    admin_key: str | None = Query(None),
):
    """Reset the counter back to 0. Requires the admin key."""
    namespace, key = parse_namespace_key(namespace, key)
    db_key = build_db_key(namespace, key)
    adm_key = build_admin_key(db_key)

    stored_admin = await db.client.get(adm_key)
    _check_admin(stored_admin, admin_key)

    updated = await db.client.set(db_key, 0, xx=True, ex=BASE_TTL_SECONDS)
    if not updated:
        raise HTTPException(status_code=409, detail="Key does not exist, please use a different key.")

    return {"value": 0}


# ── /delete ───────────────────────────────────────────────────────────────────

@router.delete("/{namespace}/{key}", tags=["counters"])
async def delete(
    namespace: str,
    key: str,
    admin_key: str | None = Query(None),
):
    """Permanently delete a counter and its admin key. Requires the admin key."""
    namespace, key = parse_namespace_key(namespace, key)
    db_key = build_db_key(namespace, key)
    adm_key = build_admin_key(db_key)

    stored_admin = await db.client.get(adm_key)
    _check_admin(stored_admin, admin_key)

    await db.client.delete(db_key, adm_key)
    return {"status": "ok", "message": f"Deleted key: {db_key}"}


# ── /info ─────────────────────────────────────────────────────────────────────

@router.get("/{namespace}/{key}/info", tags=["counters"])
async def info(namespace: str, key: str):
    """Return metadata: current value, TTL, and whether an admin key exists."""
    namespace, key = parse_namespace_key(namespace, key)
    db_key = build_db_key(namespace, key)
    adm_key = build_admin_key(db_key)

    # Pipeline: GET + EXISTS + TTL — one round trip
    async with db.client.pipeline(transaction=False) as pipe:
        pipe.get(db_key)
        pipe.exists(adm_key)
        pipe.ttl(db_key)
        val_raw, admin_exists, ttl = await pipe.execute()

    exists = ttl != -2  # -2 means key does not exist in Valkey
    value = int(val_raw) if val_raw is not None else -1
    is_genuine = admin_exists == 0  # genuine = created via /create (has admin key)

    return {
        "value": value,
        "full_key": db_key,
        "is_genuine": is_genuine,
        "expires_in": ttl,
        "exists": exists,
    }
