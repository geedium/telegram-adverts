import os
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

CLIENT_ID = int(os.getenv("CLIENT_API_ID"))
CLIENT_HASH = os.getenv("CLIENT_API_HASH")

BOT_TOKEN = os.getenv("BOT_TOKEN")

REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT")
REDIS_USER = os.getenv("REDIS_USER")
REDIS_PASS = os.getenv("REDIS_PASS")

CHANNEL_RULES = {
    "-1001810503890": {
        "type": "barcelona",
        "start": 10,
        "end": 22,
        "max_posts_per_day": 2,
        "max_length": 110,
    },
    "-1001954585999": {
        "type": "ltgrupe",
        "max_posts_per_week": 1,
        "daytime_start": 8,
        "daytime_end": 20,
    },
    "-1001231843953": {
        "type": "hourly",
        "by_hours": 10,
    },
    "-1001376932863": {
        "type": "hourly",
        "by_hours": 10,
    },
}
