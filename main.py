import asyncio
import json
import sys
import uuid
import datetime
import pytz
import redis
from telethon import events, Button, TelegramClient
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import FloodWaitError, ChatAdminRequiredError, ChannelPrivateError
import telethon
from config import BOT_TOKEN, API_ID, API_HASH, CLIENT_ID, CLIENT_HASH, REDIS_HOST, REDIS_PASS, REDIS_USER, REDIS_PORT
from uuid import uuid4

# -------------------
# Redis
# -------------------
r = redis.Redis(
    host=REDIS_HOST,
    port=int(REDIS_PORT),
    username=REDIS_USER,
    password=REDIS_PASS,
    decode_responses=True,
)

# -------------------
# Clients
# -------------------
bot_client = TelegramClient("bot_session", API_ID, API_HASH)
user_client = TelegramClient("user_session", CLIENT_ID, CLIENT_HASH)

# Temporary mapping: short keys → (ad_id, ch_id)
instant_post_map = {}

# -------------------
# Helpers
# -------------------
def get_channels():
    data = r.get("channels")
    return json.loads(data) if data else []

def set_channels(channels):
    r.set("channels", json.dumps(channels))

def get_state(uid):
    return r.get(f"state:{uid}")

def set_state(uid, state):
    r.set(f"state:{uid}", state)

def clear_state(uid):
    r.delete(f"state:{uid}")

def get_adverts():
    data = r.get("adverts")
    if not data:
        return []
    try:
        return json.loads(data)
    except:
        return []

def save_adverts(adverts):
    r.set("adverts", json.dumps(adverts))

def get_last_posted(ad_id):
    date_str = r.get(f"ad_posted:{ad_id}")
    return datetime.datetime.fromisoformat(date_str) if date_str else None

def set_last_posted(ad_id, dt):
    r.set(f"ad_posted:{ad_id}", dt.isoformat())

def find_ad(ad_id):
    for ad in get_adverts():
        if ad["id"] == ad_id:
            return ad
    return None

# -------------------
# UI
# -------------------
async def show_main_menu(event):
    buttons=[
        [Button.inline("🛰 Channels", data=b"channels")],
        [Button.inline("📝 Manage Adverts", data=b"adverts")],
        [Button.inline("⚡ Run Scheduler", data=b"run_scheduler_once")],
        [Button.inline("🌩️ Instant Post (Ad)", data=b"run_without_scheduler")],
        [Button.inline("⛈️ Instant Post (Ad & Channel)", data=b"instant_post_select_ad")],
    ]

    try:
        await event.edit("📋 Main Menu:", buttons=buttons)
    except Exception:
        await event.respond("📋 Main Menu:", buttons=buttons)

async def show_adverts_menu(event):
    try:
        adverts = get_adverts()
        if not adverts:
            await event.edit(
                "📝 No adverts yet.",
                buttons=[
                    [Button.inline("➕ New Ad", data=b"new_ad")],
                    [Button.inline("⬅️ Back", data=b"back")],
                ],
            )
            return

        buttons = []
        for ad in adverts:
            label = f"{'🟢' if ad['active'] else '🔴'} {ad['content'][:25]}"
            buttons.append([Button.inline(label, data=f"edit_ad:{ad['id']}".encode())])
        buttons.append([Button.inline("➕ New Ad", data=b"new_ad")])
        buttons.append([Button.inline("⬅️ Back", data=b"back")])

        await event.edit("📝 Your adverts:", buttons=buttons)
    except Exception as e:
        await event.answer(f"❌ Failed to load adverts: {e}", alert=True)


# -------------------
# Callbacks
# -------------------
@bot_client.on(events.NewMessage(pattern="/start"))
async def start_handler(event):
    # remove any lingering state
    clear_state(event.sender_id)
    await show_main_menu(event)


@bot_client.on(events.CallbackQuery(data=b"adverts"))
async def adverts_callback(event):
    await show_adverts_menu(event)


@bot_client.on(events.CallbackQuery(data=b"run_scheduler_once"))
async def run_scheduler_once_callback(event):
    await event.respond("⚡ Running scheduler once for debug...")
    await run_scheduler_once()
    await event.respond("✅ Scheduler run completed!")

@bot_client.on(events.CallbackQuery(data=b"run_without_scheduler"))
async def run_without_scheduler(event):
    adverts = get_adverts()
    if not adverts:
        await event.answer("❌ No adverts available.", alert=True)
        return

    buttons = []
    for ad in adverts:
        label = f"{'🟢' if ad['active'] else '🔴'} {ad['content'][:25]}"
        buttons.append([Button.inline(label, data=f"instant_post_ad_all:{ad['id']}".encode())])

    buttons.append([Button.inline("⬅️ Back", data=b"back")])
    await event.edit("📝 Select an ad to post instantly (to all its channels):", buttons=buttons)

@bot_client.on(events.CallbackQuery(data=b"back"))
async def handle_back(event):
    clear_state(event.sender_id)
    await show_main_menu(event)

@bot_client.on(events.CallbackQuery(data=b"instant_post_select_ad"))
async def instant_post_select_ad_callback(event):
    adverts = get_adverts()
    if not adverts:
        await event.answer("❌ No adverts available.", alert=True)
        return

    buttons = []
    for ad in adverts:
        label = f"{'🟢' if ad['active'] else '🔴'} {ad['content'][:25]}"
        buttons.append([Button.inline(label, data=f"instant_post_ad:{ad['id']}".encode())])

    buttons.append([Button.inline("⬅️ Back", data=b"back")])
    await event.edit("📝 Select an ad to instantly post:", buttons=buttons)

@bot_client.on(events.CallbackQuery(data=b"channels"))
async def handle_channels(event):
    channels = get_channels()  # list of channel IDs as strings
    if channels:
        lines = []
        for ch_id in channels:
            try:
                entity = await user_client.get_entity(int(ch_id))
                lines.append(f"{getattr(entity, 'title', ch_id)} ({ch_id})")
            except Exception:
                lines.append(f"❌ Could not fetch {ch_id}")
        text = "📡 Current Channels:\n" + "\n".join(lines)
    else:
        text = "No channels added yet."

    await event.edit(
        f"{text}\n\nSend me a Telegram channel link (t.me/...) to add one.",
        buttons=[[Button.inline("⬅️ Back", data=b"back")]],
    )
    set_state(event.sender_id, "awaiting_channel")


@bot_client.on(events.CallbackQuery(data=b"new_ad"))
async def new_ad_callback(event):
    await event.edit(
        "✍️ Send the content for your new advertisement:",
        buttons=[[Button.inline("⬅️ Cancel", data=b"adverts")]],
    )
    set_state(event.sender_id, "awaiting_ad_content")


@bot_client.on(events.NewMessage)
async def handle_messages(event):
    uid = event.sender_id
    state = get_state(uid)
    if not state:
        # Ignore normal messages unless user is in a flow
        return

    if state == "awaiting_channel":
        text = event.raw_text.strip()
        if "t.me/" not in text:
            clear_state(uid)
            await event.respond("❌ Invalid channel link. Try again.")
            return
        try:
            entity = await user_client.get_entity(text)
            eid = int(getattr(entity, "id"))
            eid_str = str(eid)
            if not eid_str.startswith("-100"):
                full = f"-100{abs(eid)}"
            else:
                full = eid_str

            channels = get_channels()
            if full not in channels:
                channels.append(full)
                set_channels(channels)
                await event.respond(
                    f"✅ Added channel {getattr(entity, 'title', text)} ({full})"
                )
            else:
                await event.respond("⚠️ Channel already added.")
        except Exception as e:
            await event.respond(f"❌ Failed: {e}")
        finally:
            clear_state(uid)
            await show_main_menu(event)
    elif state == "awaiting_ad_content":
        r.set(f"temp_ad_content:{uid}", event.raw_text)
        await event.respond("🕒 Now send schedule for this ad (e.g. `2-10 GMT+3`):")
        set_state(uid, "awaiting_ad_schedule")
    elif state == "awaiting_ad_schedule":
        content = r.get(f"temp_ad_content:{uid}")
        schedule = event.raw_text.strip()
        channels = get_channels()
        if not channels:
            await event.respond("⚠️ No channels available. Add channels first.")
            clear_state(uid)
            return

        # Store temp ad
        r.set(
            f"temp_ad:{uid}",
            json.dumps({"content": content, "schedule": schedule, "channels": []}),
        )
        set_state(uid, "awaiting_ad_channels")

        # Buttons use index instead of full ID to avoid 64-byte limit
        buttons = [
            [Button.inline(ch, data=f"ch:{i}".encode())]
            for i, ch in enumerate(channels)
        ]
        buttons.append([Button.inline("✅ Done", data=b"done_selecting_channels")])
        await event.respond(
            "📡 Select channels for this ad (click multiple, then ✅ Done):",
            buttons=buttons,
        )
    elif state.startswith("editing_text:"):
        ad_id = state.split(":")[1]
        adverts = get_adverts()
        for ad in adverts:
            if ad["id"] == ad_id:
                ad["content"] = event.raw_text
        save_adverts(adverts)
        clear_state(uid)

        await edit_ad_callback(
            type(
                "CallbackWrapper",
                (),
                {
                    "data": f"edit_ad:{ad_id}".encode(),
                    "edit": event.edit,
                    "respond": event.respond,
                    "sender_id": uid,
                },
            )()
        )
    elif state.startswith("editing_schedule:"):
        ad_id = state.split(":")[1]
        new_schedule = event.raw_text.strip()

        if not parse_schedule(new_schedule):
            await event.respond("❌ Invalid format. Use `2-10 GMT+3`")
            return

        adverts = get_adverts()
        for ad in adverts:
            if ad["id"] == ad_id:
                ad["schedule"] = new_schedule
        save_adverts(adverts)
        clear_state(uid)

        await edit_ad_callback(
            type(
                "CallbackWrapper",
                (),
                {
                    "data": f"edit_ad:{ad_id}".encode(),
                    "edit": event.edit,
                    "respond": event.respond,
                    "sender_id": uid,
                },
            )()
        )


# -------------------
# Channel selection callbacks
# -------------------
@bot_client.on(events.CallbackQuery(pattern=b"instant_post_ad:(.*)"))
async def instant_post_ad_callback(event):
    ad_id = event.data.decode().split(":")[1]
    ad = find_ad(ad_id)
    if not ad:
        await event.answer("❌ Ad not found.", alert=True)
        return

    channels = get_channels()
    if not channels:
        await event.answer("⚠️ No channels configured.", alert=True)
        return

    buttons = []
    for ch in channels:
        try:
            entity = await user_client.get_entity(int(ch))
            title = getattr(entity, "title", str(ch))
        except Exception:
            title = f"❌ {ch}"

        # Create a short mapping key
        key = str(uuid4())[:8]
        instant_post_map[key] = (ad_id, ch)

        buttons.append([Button.inline(title, data=f"instant_post_channel:{key}".encode())])

    buttons.append([Button.inline("⬅️ Back", data=b"instant_post_select_ad")])
    await event.edit(
        f"📡 Select channel to post ad:\n\n📝 {ad['content'][:100]}...",
        buttons=buttons,
    )

@bot_client.on(events.CallbackQuery(pattern=b"instant_post_channel:(.*)"))
async def instant_post_channel_callback(event):
    key = event.data.decode().split(":")[1]
    if key not in instant_post_map:
        await event.answer("⚠️ Session expired or invalid key.", alert=True)
        return

    ad_id, ch_id = instant_post_map.pop(key)  # remove after use
    ad = find_ad(ad_id)
    if not ad:
        await event.answer("❌ Ad not found.", alert=True)
        return

    await event.respond(f"🚀 Posting ad '{ad_id}' to channel {ch_id}...")
    try:
        await send_message_to_channel(ch_id, ad)
        await event.respond(f"✅ Successfully posted ad '{ad_id}' to {ch_id}!")
    except Exception as e:
        await event.respond(f"❌ Failed to post: {e}")

@bot_client.on(events.CallbackQuery(pattern=b"ch:(\d+)"))
async def select_channel_callback(event):
    uid = event.sender_id
    idx = int(event.data.decode().split(":")[1])
    state = get_state(uid)

    channels = get_channels()
    if idx >= len(channels):
        await event.answer("Invalid channel index", alert=True)
        return

    ch = channels[idx]

    # CASE 1: user is creating a new ad
    if state == "awaiting_ad_channels":
        temp = json.loads(r.get(f"temp_ad:{uid}"))
        if ch in temp["channels"]:
            temp["channels"].remove(ch)
        else:
            temp["channels"].append(ch)
        r.set(f"temp_ad:{uid}", json.dumps(temp))

        # Refresh buttons (multi-select visual update)
        buttons = []
        for i, ch_id in enumerate(channels):
            try:
                entity = await user_client.get_entity(int(ch_id))
                title = getattr(entity, "title", ch_id)
            except Exception:
                title = f"❌ {ch_id}"
            selected = "✅" if ch_id in temp["channels"] else "⬜"
            buttons.append(
                [Button.inline(f"{selected} {title}", data=f"ch:{i}".encode())]
            )
        buttons.append([Button.inline("✅ Done", data=b"done_selecting_channels")])

        await event.edit(
            "📡 Select channels for this ad (click multiple, then ✅ Done):",
            buttons=buttons,
        )

    # CASE 2: user is editing an ad
    elif state == "editing_channels":
        temp = json.loads(r.get(f"temp_edit_ad:{uid}"))
        if ch in temp["channels"]:
            temp["channels"].remove(ch)
        else:
            temp["channels"].append(ch)
        r.set(f"temp_edit_ad:{uid}", json.dumps(temp))

        # Refresh buttons (multi-select visual update)
        buttons = []
        for i, ch_id in enumerate(channels):
            try:
                entity = await user_client.get_entity(int(ch_id))
                title = getattr(entity, "title", ch_id)
            except Exception:
                title = f"❌ {ch_id}"
            selected = "✅" if ch_id in temp["channels"] else "⬜"
            buttons.append(
                [Button.inline(f"{selected} {title}", data=f"ch:{i}".encode())]
            )
        buttons.append([Button.inline("✅ Done", data=b"done_editing_channels")])

        await event.edit(
            "📡 Select channels for this ad (click multiple, then ✅ Done):",
            buttons=buttons,
        )
    else:
        await event.answer("❌ Not in channel selection mode.", alert=True)

def format_schedule(schedule: str) -> str:
    try:
        parts = schedule.split()
        if len(parts) != 2:
            return schedule  # unexpected structure
        time_range, tz = parts
        start, end = time_range.split("-")
        start_hour = int(start)
        end_hour = int(end)
        return f"{start_hour:02d}:00–{end_hour:02d}:00"
    except Exception:
        return schedule

async def show_ad_menu(event, ad_id):
    ad = find_ad(ad_id)
    if not ad:
        await event.respond("❌ Ad not found.")
        return

    text = (
        f"📝 Ad: {ad['content']}\n"
        f"⏰ Schedule: {format_schedule(ad['schedule'])}\n"
        f"Status: {'✅ Active' if ad['active'] else '⛔ Inactive'}\n"
        f"Channels: {len(ad.get('channels', []))}"
    )

    buttons = [
        [Button.inline("🚀 Toggle Active", data=f"toggle_ad:{ad_id}".encode())],
        [Button.inline("✏️ Edit Content", data=f"edit_content:{ad_id}".encode())],
        [Button.inline("🕒 Edit Schedule", data=f"edit_schedule:{ad_id}".encode())],
        [Button.inline("📡 Edit Channels", data=f"edit_channels:{ad_id}".encode())],
        [Button.inline("🗑 Delete", data=f"delete_ad:{ad_id}".encode())],
        [Button.inline("⬅️ Back", data=b"adverts")],
    ]

    try:
        # Try to edit message (works for callbacks)
        await event.edit(text, buttons=buttons)
    except Exception:
        # Fallback to sending a new message (works for NewMessage)
        await event.respond(text, buttons=buttons)

@bot_client.on(events.CallbackQuery(pattern=b"edit_ad:(.*)"))
async def edit_ad_callback(event):
    ad_id = event.data.decode().split(":")[1]
    await show_ad_menu(event, ad_id)

@bot_client.on(events.CallbackQuery(pattern=b"edit_schedule:(.*)"))
async def edit_schedule_callback(event):
    ad_id = event.data.decode().split(":")[1]
    ad = find_ad(ad_id)
    if not ad:
        await event.respond("❌ Ad not found.")
        return

    await event.edit(
        "🕒 Send the new schedule for the ad (e.g. `2-10 GMT+3`):",
        buttons=[[Button.inline("⬅️ Cancel", data=f"edit_ad:{ad_id}".encode())]],
    )
    set_state(event.sender_id, f"editing_schedule:{ad_id}")


@bot_client.on(events.CallbackQuery(pattern=b"edit_content:(.*)"))
async def edit_content_callback(event):
    ad_id = event.data.decode().split(":")[1]
    ad = find_ad(ad_id)
    if not ad:
        await event.respond("❌ Ad not found.")
        return

    await event.edit(
        "✍️ Send the new advertisement text:",
        buttons=[[Button.inline("⬅️ Cancel", data=f"edit_ad:{ad_id}".encode())]],
    )
    set_state(event.sender_id, f"editing_text:{ad_id}")


@bot_client.on(events.CallbackQuery(pattern=b"edit_channels:(.*)"))
async def edit_channels_callback(event):
    ad_id = event.data.decode().split(":")[1]
    ad = find_ad(ad_id)
    if not ad:
        await event.respond("❌ Ad not found.")
        return

    channels = get_channels()
    if not channels:
        await event.respond("⚠️ No channels available. Add channels first.")
        return

    r.set(
        f"temp_edit_ad:{event.sender_id}",
        json.dumps({"ad_id": ad_id, "channels": ad.get("channels", [])}),
    )
    set_state(event.sender_id, "editing_channels")

    buttons = []
    for i, ch_id in enumerate(channels):
        try:
            entity = await user_client.get_entity(int(ch_id))
            title = getattr(entity, "title", ch_id)
        except Exception:
            title = f"❌ {ch_id}"
        selected = "✅" if ch_id in ad.get("channels", []) else "⬜"
        buttons.append(
            [Button.inline(f"{selected} {title}", data=f"edit_ch:{i}".encode())]
        )

    buttons.append([Button.inline("✅ Done", data=b"done_editing_channels")])
    await event.edit(
        "📡 Select channels for this ad (click multiple, then ✅ Done):",
        buttons=buttons,
    )


@bot_client.on(events.CallbackQuery(pattern=b"edit_ch:(\d+)"))
async def toggle_edit_channel_callback(event):
    idx = int(event.data.decode().split(":")[1])
    uid = event.sender_id
    temp = json.loads(r.get(f"temp_edit_ad:{uid}"))
    ch = get_channels()[idx]

    if ch in temp["channels"]:
        temp["channels"].remove(ch)
    else:
        temp["channels"].append(ch)

    r.set(f"temp_edit_ad:{uid}", json.dumps(temp))
    await event.answer(f"Selected channels: {len(temp['channels'])}")


@bot_client.on(events.CallbackQuery(data=b"done_editing_channels"))
async def done_editing_channels(event):
    uid = event.sender_id
    temp = json.loads(r.get(f"temp_edit_ad:{uid}"))
    ad_id = temp["ad_id"]
    selected_channels = temp["channels"]

    adverts = get_adverts()
    for ad in adverts:
        if ad["id"] == ad_id:
            ad["channels"] = selected_channels
    save_adverts(adverts)

    r.delete(f"temp_edit_ad:{uid}")
    clear_state(uid)
    await event.respond("✅ Channels updated for the ad!")

    # Show ad menu again
    await edit_ad_callback(
        type(
            "CallbackWrapper",
            (),
            {
                "data": f"edit_ad:{ad_id}".encode(),
                "edit": event.edit,
                "respond": event.respond,
                "sender_id": uid,
            },
        )()
    )

@bot_client.on(events.CallbackQuery(pattern=b"instant_post_ad_all:(.*)"))
async def instant_post_ad_all_callback(event):
    ad_id = event.data.decode().split(":")[1]
    ad = find_ad(ad_id)
    if not ad:
        await event.answer("❌ Ad not found.", alert=True)
        return

    channels = ad.get("channels") or get_channels()
    if not channels:
        await event.answer("⚠️ No channels configured for this ad.", alert=True)
        return

    await event.respond(f"🚀 Posting ad '{ad_id}' to {len(channels)} channel(s)...")

    success = 0
    for ch in channels:
        try:
            await send_message_to_channel(ch, ad)
            success += 1
        except Exception as e:
            await event.respond(f"❌ Failed for {ch}: {e}")

    await event.respond(f"✅ Done! Posted to {success}/{len(channels)} channels.")

@bot_client.on(events.CallbackQuery(pattern=b"toggle_ad:(.*)"))
async def toggle_ad_callback(event):
    ad_id = event.data.decode().split(":")[1]
    adverts = get_adverts()
    updated = False
    for ad in adverts:
        if ad["id"] == ad_id:
            ad["active"] = not ad["active"]
            updated = True
    save_adverts(adverts)

    if updated:
        try:
            await edit_ad_callback(event)
        except telethon.errors.rpcerrorlist.MessageNotModifiedError:
            await event.answer("✅ Toggled successfully", alert=True)


@bot_client.on(events.CallbackQuery(pattern=b"delete_ad:(.*)"))
async def delete_ad_callback(event):
    ad_id = event.data.decode().split(":")[1]
    adverts = [ad for ad in get_adverts() if ad["id"] != ad_id]
    save_adverts(adverts)
    await event.edit("🗑 Ad deleted.")
    await show_adverts_menu(event)


@bot_client.on(events.CallbackQuery(data=b"done_selecting_channels"))
async def done_selecting_channels(event):
    uid = event.sender_id
    temp_ad = json.loads(r.get(f"temp_ad:{uid}"))
    ad = {
        "id": str(uuid.uuid4()),
        "content": temp_ad["content"],
        "schedule": temp_ad["schedule"],
        "channels": temp_ad["channels"],
        "active": False,
    }
    adverts = get_adverts()
    adverts.append(ad)
    save_adverts(adverts)
    clear_state(uid)
    r.delete(f"temp_ad:{uid}")
    await event.respond(
        f"✅ Ad created!\nContent: {ad['content']}\nSchedule: {ad['schedule']}\nChannels: {ad['channels']}"
    )
    await show_adverts_menu(event)


def parse_schedule(schedule_str):
    try:
        hours, tz = schedule_str.split()
        start, end = map(int, hours.split("-"))
        offset = int(tz.replace("GMT", ""))
        return start, end, offset
    except Exception:
        return None

async def debug_chat_permissions(ch_id: int):
    try:
        entity = await user_client.get_entity(ch_id)
        print("=== Chat Info ===")
        print(f"Title: {getattr(entity, 'title', None)}")
        print(f"ID: {entity.id}")
        print(f"Type: {type(entity)}")
        print(f"Megagroup: {getattr(entity, 'megagroup', False)}")
        print(f"Broadcast: {getattr(entity, 'broadcast', False)}")
        print(f"Creator: {getattr(entity, 'creator', False)}")
        print(f"Admin rights: {getattr(entity, 'admin_rights', None)}")
        print(f"Default banned rights: {getattr(entity, 'default_banned_rights', None)}")

        # Check if user is joined
        full = await user_client.get_permissions(ch_id, 'me')
        print("=== My Permissions ===")
        print(full)
    except ChannelPrivateError:
        print("❌ Channel is private or you are not a member.")
    except Exception as e:
        print(f"❌ Failed to inspect chat: {e}")

async def send_message_to_channel(ch_id, ad):
    try:
        try:
            permissions = await user_client.get_permissions(int(ch_id), 'me')
            print("=== Permissions ===")
            print(permissions)
        except:
            await user_client(JoinChannelRequest(ch_id))
            print(f"Not in channel {ch_id}. Joining.")

        # await debug_chat_permissions(int(ch_id))
        entity = await user_client.get_entity(int(ch_id))
        await user_client.send_message(entity, ad["content"])
        print(f"[{datetime.datetime.now()}] ✅ Posted ad '{ad['id']}' to {ch_id}")
        await asyncio.sleep(1)
    except FloodWaitError as e:
        print(f"⚠️ Flood wait {e.seconds}s — sleeping...")
        await asyncio.sleep(e.seconds + 5)
    except ChannelPrivateError:
        print(f"❌ Channel {ch_id} is private or you are not a member.")
    except ChatAdminRequiredError:
        try:
            await bot_client.send_message(int(ch_id), "content")
        except Exception as e:
            print(f"❌ Failed via bot to {ch_id}: {e}")
    except Exception as e:
        print(f"Failed to send ad {ad['id']} to {ch_id}: {e}")

async def try_post_ad(ad):
    if not ad["active"]:
        return

    parsed = parse_schedule(ad["schedule"])
    if not parsed:
        print(f"❌ Invalid schedule for ad {ad['id']}")
        return

    start, end, offset = parsed
    tzinfo = pytz.timezone("Europe/Vilnius")
    now_utc = datetime.datetime.now(tzinfo)

    # Check if we already posted this ad today
    last_posted = get_last_posted(ad["id"])
    if last_posted:
        # If last posted today in this hour slot, skip
        if last_posted.date() == now_utc.date() and start <= last_posted.hour < end:
            print(f"⏰ Already posted today for ad {ad['id']}")
            return

    # Only post if current hour in schedule
    if start <= now_utc.hour < end:
        target_channels = ad.get("channels") or get_channels()
        for ch in target_channels:
            await send_message_to_channel(ch, ad)
        # Mark as posted
        set_last_posted(ad["id"], now_utc)
    else:
        print(f"⏰ Time not in range: {now_utc} (schedule {start}-{end} GMT+3)")

async def run_scheduler_once():
    adverts = get_adverts()
    for ad in adverts:
        await try_post_ad(ad)

async def scheduler_loop():
    while True:
        await run_scheduler_once()
        await asyncio.sleep(3600)

# -------------------
# Bootstrap
# -------------------
async def main():
    async with bot_client:
        await bot_client.start(bot_token=BOT_TOKEN)
        async with user_client:
            await user_client.start()
            print("✅ Bot and user sessions started.")
            await asyncio.gather(
                bot_client.run_until_disconnected(),
                user_client.run_until_disconnected(),
                scheduler_loop(),
            )


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
