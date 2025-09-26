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

# Bestand waarin aangekondigde events worden opgeslagen
ANNOUNCED_EVENTS_FILE = "announced_events.json"

# Laad eerder aangekondigde events of maak een lege dict
if os.path.exists(ANNOUNCED_EVENTS_FILE):
    with open(ANNOUNCED_EVENTS_FILE, "r") as f:
        already_announced_events = json.load(f)
else:
    already_announced_events = {}  # dict: {event_id: {"message_id": ...}}

# Functie om opgeslagen events bij te werken
def save_announced_events():
    with open(ANNOUNCED_EVENTS_FILE, "w") as f:
        json.dump(already_announced_events, f)


# Laad token uit .env
load_dotenv()
TOKEN = os.getenv("TOKEN")
if TOKEN is None:
    raise ValueError("TOKEN is niet ingesteld in .env")

# Stel intents in
intents = discord.Intents.all()
intents.members = True
intents.message_content = True
intents.guild_scheduled_events = True

# Maak de bot
bot = commands.Bot(command_prefix="!", intents=intents)

# Kanaal-ID
WELCOME_CHANNEL_ID = 1410221365923024970
EVENT_CHANNEL_ID = 1410240534705995796

# -------------------- BOT EVENTS --------------------

@bot.event
async def on_ready():
    print(f"{bot.user} is nu online en klaar!")
    bot.loop.create_task(poll_guild_events())

@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if isinstance(channel, TextChannel):
        await channel.send(
            f"Welkom {member.mention}! 🎉 Fijn dat je er bent bij Stichting YALC!\n\n"
            "📜 **Regels:**\n1. Wees respectvol\n2. Geen spam\n3. Volg de richtlijnen van de server"
        )
    else:
        print("Welkom-kanaal niet gevonden of geen TextChannel")


# -------------------- GUILD EVENTS POLLING --------------------

async def poll_guild_events():
    await bot.wait_until_ready()
    if not bot.guilds:
        print("Bot zit nog in geen enkele server")
        return
    guild = bot.guilds[0]
    channel = bot.get_channel(EVENT_CHANNEL_ID)

    while not bot.is_closed():
        try:
            events = await guild.fetch_scheduled_events()
            for event in events:
                event_id_str = str(event.id)
                if event_id_str not in already_announced_events:
                    # Bepaal locatie
                    location = getattr(event, "location", None)
                    entity_metadata = getattr(event, "entity_metadata", None)
                    if not location and entity_metadata:
                        location = getattr(entity_metadata, "location", None)
                    location_text = f"📍 Locatie: {location}" if location else "📍 Locatie: Niet opgegeven"

                    if isinstance(channel, TextChannel):
                        msg = await channel.send(
                            f"📢 Nieuw evenement gepland!\n"
                            f"**{event.name}**\n"
                            f"🗓 Datum en tijd: {event.start_time.strftime('%d-%m-%Y %H:%M')}\n"
                            f"{location_text}\nZorg dat je erbij bent! 🎉"
                        )

                        # Sla event en bericht id op
                        already_announced_events[event_id_str] = {"message_id": msg.id}
                        save_announced_events()

                        # Verwijder bericht na 6 uur (21600 seconden)
                        async def delete_message_later(message, delay_seconds=10):
                            await asyncio.sleep(delay_seconds)
                            try:
                                await message.delete()
                            except Exception as e:
                                print(f"Kon bericht niet verwijderen: {e}")

                        asyncio.create_task(delete_message_later(msg))

                        # Plan reminder 24 uur van tevoren
                        async def send_reminder(e, location_text):
                            reminder_time = e.start_time - timedelta(hours=24)
                            now = datetime.now(timezone.utc)
                            wait_seconds = (reminder_time - now).total_seconds()
                            if wait_seconds > 0:
                                await asyncio.sleep(wait_seconds)
                            await channel.send(
                                f"⏰ Herinnering! **{e.name}** begint over 24 uur! {location_text}"
                            )

                        asyncio.create_task(send_reminder(event, location_text))

        except Exception as e:
            print(f"Fout bij pollen van events: {e}")

        await asyncio.sleep(60)  # poll elke minuut


# -------------------- COMMANDS --------------------

@bot.command()
async def test_welcome(ctx):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if isinstance(channel, TextChannel):
        await channel.send("Dit is een testbericht!")
    else:
        await ctx.send("Welkom-kanaal niet gevonden of geen TextChannel")

@bot.command()
async def test_event(ctx):
    channel = bot.get_channel(EVENT_CHANNEL_ID)
    if isinstance(channel, TextChannel):
        await channel.send(
            "📢 Test van een evenement!\n**Test Event**\n🗓 01-01-2025 12:00\n📍 Testlocatie\nZorg dat je erbij bent! 🎉"
        )
        await ctx.send("Testbericht naar het evenementen-kanaal gestuurd ✅")
    else:
        await ctx.send("Evenementenkanaal niet gevonden of geen TextChannel ❌")

@bot.command()
async def test_reminder(ctx):
    channel = bot.get_channel(EVENT_CHANNEL_ID)
    if not isinstance(channel, TextChannel):
        await ctx.send("Evenementenkanaal niet gevonden!")
        return

    class DummyEvent:
        name = "Test Reminder Event"
        start_time = datetime.now(timezone.utc) + timedelta(minutes=2)
        location = "Testlocatie"

    event = DummyEvent()

    async def send_reminder(event):
        reminder_time = event.start_time - timedelta(minutes=1)
        now = datetime.now(timezone.utc)
        wait_seconds = (reminder_time - now).total_seconds()
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)
        await channel.send(
            f"⏰ Herinnering! **{event.name}** begint over 1 minuut! 📍 {event.location}"
        )

    asyncio.create_task(send_reminder(event))
    await ctx.send("Test reminder event gepland ✅")


# -------------------- KEEP-ALIVE --------------------

app = Flask('')

@app.route('/')
def home():
    return "Buddy Bot is online!"

def run():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

keep_alive()

# -------------------- BOT START --------------------

bot.run(TOKEN)
