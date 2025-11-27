import json
from .redis import redis

def get_channels():
    data = redis.get("teleads:channels")
    return json.loads(data) if data else []

def set_channels(channels):
    redis.set("teleads:channels", json.dumps(channels))
