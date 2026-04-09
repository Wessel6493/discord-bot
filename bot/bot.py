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
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

poll_started = False
tickets = {}
scheduled_reminders = set()

# Channel IDs
WELCOME_CHANNEL_ID = 1410221365923024970
EVENT_CHANNEL_ID = 1410240534705995796
SUPPORT_CHANNEL_ID = 1410241224547504208

# -------------------- REMINDER --------------------
async def send_reminder(event_name, start_time, location_text, channel, event_id, announcement_msg_id):
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

    # Stuur reminder, verwijder na 24 uur (als event voorbij is)
    await channel.send(
        f"⏰ Herinnering! **{event_name}** begint over 24 uur! {location_text}",
        delete_after=86400  # 24 uur in seconden
    )

    # Markeer reminder als verzonden
    try:
        update_reminder(db_connection, event_id)
        print(f"⏰ Reminder gemarkeerd als verzonden: {event_name}")
    except Exception as e:
        print(f"❌ Update error: {e}")

    # Wacht tot het event begint en verwijder dan het aankondigingsbericht
    wait_until_event = (start_time - datetime.now(timezone.utc)).total_seconds()
    if wait_until_event > 0:
        await asyncio.sleep(wait_until_event)

    try:
        announcement_msg = await channel.fetch_message(announcement_msg_id)
        await announcement_msg.delete()
        print(f"🗑 Aankondigingsbericht verwijderd voor: {event_name}")
    except Exception as e:
        print(f"❌ Kon aankondigingsbericht niet verwijderen: {e}")

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
                if db_event and not db_event.get("reminder_sent") and event.id not in scheduled_reminders:
                    scheduled_reminders.add(event.id)
                    print(f"⏰ Reminder nog niet verzonden voor {event.name}, plannen")
                    asyncio.create_task(
                        send_reminder(event.name, start_time, location_text, channel, event.id, db_event["message_id"])
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
    tickets[msg.id] = {
    "user_id": ctx.author.id
    }

    try:
        await ctx.author.send("✅ Ticket ontvangen")
        await ctx.message.delete()
    except:
        pass

# -------------------- CLOSE TICKET --------------------
@bot.command()
async def close(ctx, *, oplossing=None):
    if not oplossing:
        return await ctx.reply("Gebruik: reply op ticket + !close <oplossing>")

    if not ctx.message.reference:
        return await ctx.reply("❌ Reply op het ticket bericht dat je wilt sluiten")

    try:
        message_id = ctx.message.reference.message_id
    except:
        return await ctx.reply("❌ Kon bericht niet vinden")

    if message_id not in tickets:
        return await ctx.reply("❌ Dit is geen geldig ticket")

    support_channel = bot.get_channel(SUPPORT_CHANNEL_ID)
    ticket_data = tickets[message_id]
    user_id = ticket_data["user_id"]

    try:
        msg = await support_channel.fetch_message(message_id)

        if not msg.embeds:
            return await ctx.send("❌ Geen embed gevonden")

        embed = msg.embeds[0]
        embed.color = discord.Color.red()

        embed.add_field(
            name="🛠 Oplossing",
            value=oplossing,
            inline=False
        )

        embed.set_footer(
            text=f"Gesloten door {ctx.author} op {datetime.now().strftime('%d-%m-%Y %H:%M')}"
        )

        await msg.edit(embed=embed)

    except Exception as e:
        print(f"Error: {e}")
        return await ctx.send("❌ Kon ticket niet aanpassen")

    # ✅ DM NAAR USER
    try:
        user = await bot.fetch_user(user_id)
        await user.send(
            f"🔒 Je ticket is gesloten!\n\n"
            f"🛠 **Oplossing:**\n{oplossing}"
        )
    except Exception as e:
        print(f"DM error: {e}")

    del tickets[message_id]

    await ctx.send("✅ Ticket gesloten", delete_after=5)

# -------------------- HELP COMMAND --------------------
@bot.command()
async def help(ctx):
    embed = discord.Embed(
        title="📖 Help Menu",
        description="Hier zijn alle beschikbare commando's:",
        color=discord.Color.blue()
    )

    embed.add_field(
        name="🎫 Tickets",
        value=(
            "`!ticket <bericht>` - Maak een ticket aan\n"
            "`!help` - Toon dit help menu\n"
            "**Voor staff:**\n"
            "`!close <oplossing>` - Sluit een ticket (reply op bericht)"
        ),
        inline=False
    )

    embed.add_field(
        name="📅 Events",
        value=(
            "Automatisch:\n"
            "• Nieuwe events worden gepost\n"
            "• Herinnering 24 uur van tevoren"
        ),
        inline=False
    )

    embed.set_footer(text="Gebruik de commands correct 😉")

    await ctx.send(embed=embed)

# -------------------- KEEP ALIVE --------------------

app = Flask('')
@app.route('/')
def home():
    return "Bot online"

Thread(target=lambda: app.run(host='0.0.0.0', port=5000), daemon=True).start()

# -------------------- START --------------------
bot.run(TOKEN)
