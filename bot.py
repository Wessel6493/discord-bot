import os
import discord
import json
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask
from threading import Thread
from discord import TextChannel
import asyncio
from datetime import datetime, timezone, timedelta
import mysql.connector
from mysql.connector import Error

# -------------------- DATABASE CONNECTIE --------------------

def create_db_connection():
    try:
        connection = mysql.connector.connect(
            host=os.getenv("DB_HOST", "sql108.infinityfree.com"),
            user=os.getenv("DB_USER", "if0_40050163"),
            password=os.getenv("DB_PASSWORD", "glrNV0WDAjnS60"),
            database=os.getenv("DB_NAME", "if0_40050163_discord_bot")
        )
        if connection.is_connected():
            print("✅ Verbonden met de database!")
            return connection
    except Error as e:
        print(f"❌ Fout bij verbinden met de database: {e}")
        return None

db_connection = create_db_connection()
db_cursor = db_connection.cursor(dictionary=True) if db_connection else None

# -------------------- JSON BACKUP --------------------

ANNOUNCED_EVENTS_FILE = "announced_events.json"

if os.path.exists(ANNOUNCED_EVENTS_FILE):
    with open(ANNOUNCED_EVENTS_FILE, "r") as f:
        already_announced_events = json.load(f)
else:
    already_announced_events = {}

def save_announced_events():
    with open(ANNOUNCED_EVENTS_FILE, "w") as f:
        json.dump(already_announced_events, f)

# -------------------- BOT SETUP --------------------

load_dotenv()
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise ValueError("TOKEN is niet ingesteld in .env")

intents = discord.Intents.all()
intents.members = True
intents.message_content = True
intents.guild_scheduled_events = True

bot = commands.Bot(command_prefix="!", intents=intents)

WELCOME_CHANNEL_ID = 1410221365923024970
EVENT_CHANNEL_ID = 1410240534705995796

# -------------------- REMINDER FUNCTIE --------------------

async def send_reminder(event_name, occurrence_time, loc_text, channel):
    reminder_time = occurrence_time - timedelta(hours=24)
    wait_seconds = (reminder_time - datetime.now(timezone.utc)).total_seconds()
    if wait_seconds > 0:
        await asyncio.sleep(wait_seconds)
    await channel.send(f"⏰ Herinnering! **{event_name}** begint over 24 uur! {loc_text}")

# -------------------- BOT EVENTS --------------------

@bot.event
async def on_ready():
    print(f"{bot.user} is online!")
    bot.loop.create_task(poll_guild_events())

@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if isinstance(channel, TextChannel):
        await channel.send(f"Welkom {member.mention}! 🎉")

# -------------------- GUILD EVENTS POLLING --------------------

async def poll_guild_events():
    await bot.wait_until_ready()
    if not bot.guilds:
        print("Bot zit nog in geen server")
        return

    guild = bot.guilds[0]
    channel = bot.get_channel(EVENT_CHANNEL_ID)

    while not bot.is_closed():
        try:
            events = await guild.fetch_scheduled_events()
            for event in events:
                event_id_str = str(event.id)
                start_time = event.start_time.replace(microsecond=0)  # microseconds verwijderen

                # Check of occurance al in DB staat
                exists = None
                if db_connection and db_cursor:
                    db_cursor.execute(
                        "SELECT * FROM event_occurrences WHERE event_id=%s AND occurrence_time=%s",
                        (event.id, start_time)
                    )
                    exists = db_cursor.fetchone()

                if not exists:
                    location = getattr(event, "location", None) or getattr(getattr(event, "entity_metadata", None), "location", None)
                    location_text = f"📍 Locatie: {location}" if location else "📍 Locatie: Niet opgegeven"

                    if isinstance(channel, TextChannel):
                        msg = await channel.send(
                            f"📢 Nieuw evenement!\n**{event.name}**\n"
                            f"🗓 {start_time.strftime('%d-%m-%Y %H:%M')}\n"
                            f"{location_text}"
                        )

                        # JSON opslaan
                        key = f"{event_id_str}_{start_time.isoformat()}"
                        already_announced_events[key] = {"message_id": msg.id}
                        save_announced_events()

                        # Opslaan in DB
                        if db_connection and db_cursor:
                            try:
                                db_cursor.execute(
                                    "INSERT INTO event_occurrences (event_id, message_id, occurrence_time, deleted) VALUES (%s, %s, %s, %s)",
                                    (event.id, msg.id, start_time, 0)
                                )
                                db_connection.commit()
                            except Error as e:
                                db_connection.rollback()
                                print(f"❌ Fout bij opslaan in DB: {e}")

                        # Reminder plannen
                        asyncio.create_task(send_reminder(event.name, start_time, location_text, channel))

        except Exception as e:
            print(f"Fout bij pollen van events: {e}")

        await asyncio.sleep(60)

# -------------------- KEEP-ALIVE --------------------

app = Flask('')

@app.route('/')
def home():
    return "Buddy Bot is online!"

def run():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

Thread(target=run, daemon=True).start()

# -------------------- BOT START --------------------

bot.run(TOKEN)
    