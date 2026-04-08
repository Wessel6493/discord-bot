import os
import discord
import asyncio
import sys
from datetime import datetime, timezone, timedelta
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask
from threading import Thread
from discord import TextChannel

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Database functies
from database.database import create_db_connection, get_event, insert_event, update_reminder

load_dotenv()

# -------------------- DATABASE --------------------
db_connection = create_db_connection()

# -------------------- BOT SETUP --------------------
TOKEN = os.getenv("TOKEN")
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

poll_started = False
tickets = {}

# Channel IDs
WELCOME_CHANNEL_ID = 1410221365923024970
EVENT_CHANNEL_ID = 1410240534705995796
SUPPORT_CHANNEL_ID = 1410241224547504208

# -------------------- REMINDER --------------------
async def send_reminder(event_name, start_time, location_text, channel, event_id):
    """
    Stuurt reminder 24 uur voor event.
    Markeert reminder als verzonden in database.
    """
    now = datetime.now(timezone.utc)

    if start_time < now:
        return

    reminder_time = start_time - timedelta(hours=24)
    wait = (reminder_time - now).total_seconds()
    if wait > 0:
        await asyncio.sleep(wait)

    await channel.send(f"⏰ Herinnering! **{event_name}** begint over 24 uur! {location_text}")

    # Markeer reminder als verzonden
    try:
        update_reminder(db_connection, event_id)
        print(f"⏰ Reminder gemarkeerd als verzonden: {event_name}")
    except Exception as e:
        print(f"❌ Update error: {e}")

# -------------------- READY --------------------
@bot.event
async def on_ready():
    global poll_started
    print(f"{bot.user} online")
    if not poll_started:
        bot.loop.create_task(poll_guild_events())
        poll_started = True

# -------------------- WELCOME --------------------
@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if isinstance(channel, TextChannel):
        await channel.send(
            f"Welkom {member.mention}! 🎉\n\n"
            "📜 **Regels:**\n1. Respect\n2. Geen spam\n3. Volg staff"
        )

# -------------------- EVENT POLLING --------------------
async def poll_guild_events():
    """
    Poll Discord events op een rate-limit vriendelijke manier.
    - Checkt alleen events die nog niet in de database staan.
    - Plant reminders alleen als ze nog niet verstuurd zijn.
    - Vermijdt spam en dubbele inserts.
    """
    await bot.wait_until_ready()
    guild = bot.guilds[0]
    channel = bot.get_channel(EVENT_CHANNEL_ID)

    while not bot.is_closed():
        try:
            events = await guild.fetch_scheduled_events()
            print(f"🔎 Gevonden {len(events)} events in Discord")

            for event in events:
                start_time = event.start_time.astimezone(timezone.utc).replace(microsecond=0)
                now = datetime.now(timezone.utc)

                if start_time < now:
                    print(f"⏳ Event {event.name} ({event.id}) is al voorbij, skip")
                    continue

                # Haal event op uit DB
                db_event = get_event(db_connection, event.id)

                # Locatie ophalen
                location = getattr(event, "location", None) or getattr(
                    getattr(event, "entity_metadata", None), "location", None
                )
                location_text = f"📍 {location}" if location else "📍 Geen locatie"

                # -------------------- NIEUW EVENT --------------------
                if not db_event:
                    print(f"📢 Nieuw event gevonden: {event.name}")
                    msg = await channel.send(
                        f"📢 Nieuw evenement!\n"
                        f"**{event.name}**\n"
                        f"🗓 {start_time.strftime('%d-%m-%Y %H:%M')}\n"
                        f"{location_text}"
                    )

                    success = insert_event(
                        db_connection,
                        event_id=event.id,
                        message_id=msg.id,
                        event_name=event.name,
                        location=location_text,
                        occurance_time=start_time
                    )
                    if success:
                        print(f"✅ Event '{event.name}' opgeslagen in database")
                    else:
                        print(f"❌ Kon event '{event.name} {event.id} {db_event}' niet opslaan in database")

                # -------------------- REMINDER --------------------
                db_event = get_event(db_connection, event.id)
                if db_event and not db_event.get("reminder_sent"):
                    print(f"⏰ Reminder nog niet verzonden voor {event.name}, plannen")
                    asyncio.create_task(
                        send_reminder(event.name, start_time, location_text, channel, event.id)
                    )

        except discord.errors.HTTPException as e:
            print(f"⚠️ Discord HTTP error: {e}, wachten tot volgende poll")
        except Exception as e:
            print(f"❌ Polling error: {e}")

        # Poll interval rate-limit vriendelijk
        await asyncio.sleep(600)  # check elke 10 minuten

# -------------------- TICKET --------------------
@bot.command()
async def ticket(ctx, *, bericht=None):
    if not bericht:
        return await ctx.reply("Gebruik: !ticket <bericht>")
    if ctx.author.id in tickets:
        return await ctx.reply("⚠️ Je hebt al een ticket")

    support_channel = bot.get_channel(SUPPORT_CHANNEL_ID)
    embed = discord.Embed(
        title="🎟 Nieuw Ticket",
        description=f"{ctx.author.mention}\n\n{bericht}",
        color=discord.Color.green()
    )
    msg = await support_channel.send(embed=embed)
    tickets[ctx.author.id] = msg.id

    try:
        await ctx.author.send("✅ Ticket ontvangen")
        await ctx.message.delete()
    except:
        pass

# -------------------- CLOSE TICKET --------------------
@bot.command()
async def close(ctx):
    if ctx.author.id not in tickets:
        return await ctx.reply("⚠️ Je hebt geen open ticket")

    support_channel = bot.get_channel(SUPPORT_CHANNEL_ID)
    msg_id = tickets[ctx.author.id]

    try:
        msg = await support_channel.fetch_message(msg_id)
        embed = msg.embeds[0]
        embed.color = discord.Color.red()
        embed.set_footer(text=f"Gesloten door {ctx.author} op {datetime.now().strftime('%d-%m-%Y %H:%M')}")
        await msg.edit(embed=embed)
    except:
        pass

    del tickets[ctx.author.id]

    try:
        await ctx.author.send("🔒 Je ticket is gesloten")
        await ctx.message.delete()
    except:
        pass

    await ctx.send(f"✅ Ticket van {ctx.author.mention} gesloten", delete_after=5)

# -------------------- KEEP ALIVE --------------------
app = Flask('')
@app.route('/')
def home():
    return "Bot online"

Thread(target=lambda: app.run(host='0.0.0.0', port=5000), daemon=True).start()

# -------------------- START --------------------
bot.run(TOKEN)