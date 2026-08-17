from contextlib import asynccontextmanager
from fastapi import FastAPI
from dotenv import load_dotenv

from core.database import init_valkey, close_valkey

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_valkey()
    yield
    await close_valkey()

app = FastAPI(
    title="Suanpan (Abacus in Python)",
    description="A highly scalable and stateless counting API using FastAPI and Valkey.",
    lifespan=lifespan
)

@app.get("/")
async def root():
    return {"message": "Welcome to Suanpan API"}

@app.get("/health")
async def health():
    from core.database import client
    if client:
        try:
            await client.ping()
            return {"status": "healthy", "valkey": "connected"}
        except Exception as e:
            return {"status": "unhealthy", "valkey": str(e)}
    return {"status": "unhealthy", "valkey": "not initialized"}
