from redis import Redis
from src.config import REDIS_HOST, REDIS_PASS, REDIS_PORT, REDIS_USER

redis = Redis(
    host=REDIS_HOST,
    port=int(REDIS_PORT),
    username=REDIS_USER,
    password=REDIS_PASS,
    decode_responses=True,
)
