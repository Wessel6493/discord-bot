import os
import discord
import json
import asyncio
from datetime import datetime, timezone, timedelta
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask
from threading import Thread
from discord import TextChannel
import mysql.connector
from mysql.connector import Error

load_dotenv()

tickets = {}
poll_started = False


# -------------------- DATABASE --------------------

def create_db_connection():
    try:
        connection = mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            database=os.getenv("DB_NAME")
        )
        if connection.is_connected():
            print("✅ Verbonden met database")
            return connection
    except Error as e:
        print("DB error:", e)
        return None


db_connection = create_db_connection()
db_cursor = db_connection.cursor(dictionary=True) if db_connection else None


# -------------------- BOT SETUP --------------------

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

def is_admin():
    async def predicate(ctx):
        if ctx.author.guild_permissions.administrator:
            return True

        role_ids = [role.id for role in ctx.author.roles]
        if ADMIN_ROLE_ID in role_ids:
            return True

        await ctx.send("🚫 Alleen admins mogen dit commando gebruiken.")
        return False

    return commands.check(predicate)

WELCOME_CHANNEL_ID = 1410221365923024970
EVENT_CHANNEL_ID = 1410240534705995796
SUPPORT_CHANNEL_ID = 1410241224547504208
ADMIN_ROLE_ID = 1410222510393397389 



# -------------------- REMINDER --------------------

async def send_reminder(event_name, start_time, location_text, channel):

    now = datetime.now(timezone.utc)

    if start_time < now:
        return

    reminder_time = start_time - timedelta(hours=24)
    wait = (reminder_time - now).total_seconds()

    if wait > 0:
        await asyncio.sleep(wait)

    await channel.send(f"⏰ Herinnering! **{event_name}** begint over 24 uur! {location_text}")


# -------------------- READY --------------------

@bot.event
async def on_ready():
    global poll_started
    print(bot.user, "online")

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

    await bot.wait_until_ready()

    guild = bot.guilds[0]
    channel = bot.get_channel(EVENT_CHANNEL_ID)

    while not bot.is_closed():

        try:

            events = await guild.fetch_scheduled_events()

            for event in events:

                start_time = event.start_time.astimezone(timezone.utc).replace(microsecond=0)
                now = datetime.now(timezone.utc)

                if start_time < now:
                    continue

                exists = None

                if db_cursor:
                    try:
                        db_cursor.execute(
                            "SELECT 1 FROM announced_events WHERE event_id=%s AND occurance_time=%s LIMIT 1",
                            (event.id, start_time)
                        )
                        exists = db_cursor.fetchone()
                    except:
                        exists = True

                if exists:
                    continue

                location = getattr(event, "location", None) or getattr(
                    getattr(event, "entity_metadata", None), "location", None)

                location_text = f"📍 {location}" if location else "📍 Geen locatie"

                msg = await channel.send(
                    f"📢 Nieuw evenement!\n"
                    f"**{event.name}**\n"
                    f"🗓 {start_time.strftime('%d-%m-%Y %H:%M')}\n"
                    f"{location_text}"
                )

                if db_cursor:
                    try:
                        # INSERT inclusief event_name, zodat 1364 fout verdwijnt
                        db_cursor.execute(
                         "INSERT INTO announced_events (event_id, message_id, occurance_time, deleted, event_name, reminder_sent) VALUES (%s, %s, %s, %s, %s, %s)",
                         (event.id, msg.id, start_time, 0, event.name, 0)
                        )
                        db_connection.commit()
                        print(f"✅ Event opgeslagen: {event.name} ({start_time})")
                    except Error as e:
                        print(f"❌ Insert error voor event {event.name}: {e}")

                asyncio.create_task(
                    send_reminder(event.name, start_time, location_text, channel)   
                )

        except Exception as e:
            print("Polling error:", e)

        await asyncio.sleep(300)


# -------------------- TICKET --------------------

@bot.command()
async def ticket(ctx, *, bericht=None):

    if not bericht:
        return await ctx.reply("Gebruik: !ticket <bericht>")

    if ctx.author.id in tickets:
        return await ctx.reply("⚠️ Je hebt al ticket")

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
    except:
        pass

    if ctx.guild:
        try:
            await ctx.message.delete()
        except Exception:
            pass


# -------------------- CLOSE --------------------

@bot.command()
@commands.has_permissions(manage_messages=True)
async def close(ctx, user: discord.Member):

    if user.id not in tickets:
        return await ctx.send("Geen ticket")

    tickets.pop(user.id)

# -------------------- ERROR HANDLING --------------------

@bot.event
async def on_command_error(ctx, error):

    # Command bestaat niet
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ Dit commando bestaat niet. Gebruik `!help` voor alle commando's.")

    
    # Verplichte argumenten ontbreken
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"⚠️ Je mist een argument: `{error.param.name}`")

    # Geen permissie
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("🚫 Jij hebt geen rechten om dit commando te gebruiken.")

    # Bot mist permissies
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send("⚠️ Ik heb niet genoeg rechten om dit uit te voeren.")

    # Fout bij !close zonder manage_messages
    elif isinstance(error, commands.CheckFailure):
        await ctx.send("🚫 Je hebt geen toestemming om dit commando te gebruiken.")

    # Onbekende fouten
    else:
        print(f"Onbekende fout: {error}")
        await ctx.send(f"⚠️ Er is iets misgegaan bij het uitvoeren van dit commando. {error}")

# -------------------- KEEP-ALIVE --------------------

app = Flask('')

@app.route('/')
def home():
    return "Bot online"

def run():
    app.run(host='0.0.0.0', port=5000)

Thread(target=run, daemon=True).start()


# -------------------- START --------------------

bot.run(TOKEN)
    
