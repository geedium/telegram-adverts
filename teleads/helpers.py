import json
from .prisma import db

CACHE_KEY_CHANNELS = "teleads:channels"


async def get_adverts():
    record = await db.cache.find_unique(where={"key": "teleads:adverts"})
    if not record or not record.value:
        return []

    try:
        return json.loads(record.value)
    except json.JSONDecodeError:
        return []


async def set_adverts(adverts):
    value = json.dumps(adverts)
    await db.cache.upsert(
        where={"key": "teleads:adverts"},
        data={
            "update": {"value": value},
            "create": {"key": "teleads:adverts", "value": value},
        },
    )


async def get_channels():
    record = await db.cache.find_unique(where={"key": CACHE_KEY_CHANNELS})
    if not record or not record.value:
        return []

    try:
        return json.loads(record.value)
    except json.JSONDecodeError:
        return []


async def set_channels(channels: list):
    value = json.dumps(channels)
    await db.cache.upsert(
        where={"key": CACHE_KEY_CHANNELS},
        data={
            "update": {"value": value},
            "create": {"key": CACHE_KEY_CHANNELS, "value": value},
        },
    )
