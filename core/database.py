import os
from valkey.asyncio import Valkey

# Global Valkey client
client: Valkey | None = None

async def init_valkey():
    global client
    # The default URL scheme for valkey is normally valkey:// or redis://
    # We want to get str back instead of bytes so we use decode_responses=True
    valkey_url = os.getenv("VALKEY_URL", "valkey://localhost:6379")
    client = Valkey.from_url(valkey_url, decode_responses=True)

async def close_valkey():
    global client
    if client is not None:
        await client.aclose()
