from telethon import TelegramClient
from telethon.sessions import StringSession
from teleads.config import API_ID, API_HASH

SESSION_FILE = 'sessions/bot_session.session' 

# Load existing session
client = TelegramClient(SESSION_FILE, API_ID, API_HASH)

async def main():
    # Start the client
    await client.start()

    # Convert to StringSession
    string_sess = StringSession.save(client.session)
    print("Your Bot StringSession (save to .env file):\n")
    print(string_sess)

with client:
    client.loop.run_until_complete(main())
