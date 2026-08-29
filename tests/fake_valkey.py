"""Small async Valkey double used by the API tests.

The fake intentionally implements only the commands Suanpan uses. Keeping it
local makes the test suite fast and independent from a running Valkey server.
"""

from collections.abc import Callable
from typing import Any


class FakePipeline:
    def __init__(self, client: "FakeValkey") -> None:
        self.client = client
        self.operations: list[Callable[[], Any]] = []

    async def __aenter__(self) -> "FakePipeline":
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    def get(self, key: str) -> "FakePipeline":
        self.operations.append(lambda: self.client.values.get(key))
        return self

    def exists(self, key: str) -> "FakePipeline":
        self.operations.append(lambda: int(key in self.client.values))
        return self

    def ttl(self, key: str) -> "FakePipeline":
        self.operations.append(
            lambda: -2
            if key not in self.client.values
            else self.client.expirations.get(key, -1)
        )
        return self

    def dbsize(self) -> "FakePipeline":
        self.operations.append(lambda: len(self.client.values))
        return self

    def info(self, section: str) -> "FakePipeline":
        responses = {
            "server": {"redis_version": "test"},
            "stats": {"expired_keys": 0, "total_commands_processed": 0},
        }
        self.operations.append(lambda: responses[section])
        return self

    async def execute(self) -> list[Any]:
        return [operation() for operation in self.operations]


class FakeValkey:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}

    async def ping(self) -> bool:
        return True

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def incr(self, key: str) -> int:
        value = int(self.values.get(key, "0")) + 1
        self.values[key] = str(value)
        return value

    async def decr(self, key: str) -> int:
        value = int(self.values.get(key, "0")) - 1
        self.values[key] = str(value)
        return value

    async def expire(self, key: str, seconds: int) -> bool:
        if key not in self.values:
            return False
        self.expirations[key] = seconds
        return True

    async def set(
        self,
        key: str,
        value: int | str,
        *,
        nx: bool = False,
        xx: bool = False,
        ex: int | None = None,
    ) -> bool | None:
        if nx and key in self.values:
            return None
        if xx and key not in self.values:
            return None
        self.values[key] = str(value)
        if ex is not None:
            self.expirations[key] = ex
        return True

    async def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if key in self.values:
                deleted += 1
                del self.values[key]
                self.expirations.pop(key, None)
        return deleted

    async def eval(self, script: str, numkeys: int, *args: Any) -> int | None:
        del numkeys
        if 'redis.call("SET", KEYS[1]' in script:
            db_key, admin_key, initial, ttl, token = args
            if db_key in self.values:
                return 0
            self.values[db_key] = str(initial)
            self.values[admin_key] = str(token)
            self.expirations[db_key] = int(ttl)
            return 1

        if 'redis.call("INCRBY", KEYS[1]' in script:
            db_key, amount = args
            if db_key not in self.values:
                return None
            value = int(self.values[db_key]) + int(amount)
            self.values[db_key] = str(value)
            return value

        raise NotImplementedError("The test fake does not recognize this Lua script")

    def pipeline(self, transaction: bool = True) -> FakePipeline:
        del transaction
        return FakePipeline(self)
