from contextlib import asynccontextmanager
from fastapi import FastAPI
from dotenv import load_dotenv

from core.database import init_valkey, close_valkey
from routes.counters import router as counters_router

# Load environment variables from .env file if it exists
load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize the Valkey connection
    await init_valkey()
    yield
    # Shutdown: Close the Valkey connection gracefully
    await close_valkey()

app = FastAPI(
    title="Suanpan",
    description="A highly scalable and stateless counting API using FastAPI and Valkey.",
    lifespan=lifespan,
)

app.include_router(counters_router)

@app.get("/", tags=["meta"])
async def root():
    return {"message": "Welcome to Suanpan API. Visit /docs for interactive documentation."}

@app.get("/health", tags=["meta"])
async def health():
    from core.database import client
    if client:
        try:
            await client.ping()
            return {"status": "healthy", "valkey": "connected"}
        except Exception as e:
            return {"status": "unhealthy", "valkey": str(e)}
    return {"status": "unhealthy", "valkey": "not initialized"}
