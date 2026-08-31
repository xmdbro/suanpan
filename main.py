from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from dotenv import load_dotenv

from core.database import init_valkey, close_valkey
from routes.counters import router as counters_router

DOCS_DIR = Path(__file__).parent / "docs"

# Load environment variables from .env file if it exists.
load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize the Valkey connection.
    await init_valkey()
    yield
    # Shutdown: close the Valkey connection gracefully.
    await close_valkey()


app = FastAPI(
    title="Suanpan",
    description="A highly scalable and stateless counting API.",
    lifespan=lifespan,
)


@app.middleware("http")
async def add_site_headers(request: Request, call_next):
    """Preserve the security and static-asset headers from the former host."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=()",
    )
    if request.url.path.endswith((".css", ".js", ".svg", ".png")):
        response.headers.setdefault(
            "Cache-Control",
            "public, max-age=3600, stale-while-revalidate=86400",
        )
    return response


app.include_router(counters_router)


# ── Meta routes ───────────────────────────────────────────────────────────────


@app.get("/healthcheck", tags=["meta"])
@app.get("/health", tags=["meta"])
async def healthcheck():
    """Ping the Valkey backend and report overall service health."""
    from core.database import client
    if client:
        try:
            await client.ping()
            return {"status": "healthy", "valkey": "connected"}
        except Exception as e:
            return {"status": "unhealthy", "valkey": str(e)}
    return {"status": "unhealthy", "valkey": "not initialized"}


@app.get("/stats", tags=["meta"])
async def stats():
    """
    Return basic service statistics from Valkey.

    Reports the number of keys tracked and selected Valkey server info.
    A richer stats system (per-operation counters, uptime, shard name) will
    be added in a later phase.
    """
    from core.database import client
    if not client:
        return {"error": "Valkey not initialized"}

    try:
        async with client.pipeline(transaction=False) as pipe:
            pipe.dbsize()
            pipe.info("server")
            pipe.info("stats")
            total_keys, server_info, stats_info = await pipe.execute()

        return {
            "total_keys": total_keys,
            "valkey_version": server_info.get("redis_version"),
            "expired_keys": stats_info.get("expired_keys"),
            "total_commands_processed": stats_info.get("total_commands_processed"),
        }
    except Exception as e:
        return {"error": str(e)}


# Serve the documentation site as the frontend fallback. FastAPI path
# operations (including Swagger at /docs) take priority over frontend files.
app.frontend("/", directory=DOCS_DIR)
