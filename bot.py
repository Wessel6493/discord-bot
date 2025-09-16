import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

# Laad token uit .env
load_dotenv()
TOKEN = os.getenv("TOKEN")

# Stel intents in (nodig om join-events te ontvangen)
intents = discord.Intents.all()
intents.members = True
intents.message_content = True
# Maak de bot
bot = commands.Bot(command_prefix="!", intents=intents)

# Wanneer de bot opstart
@bot.event
async def on_ready():
    print(f"{bot.user} is nu online en klaar om welkom te heten!")

# Wanneer een nieuw lid joint
@bot.event
async def on_member_join(member):
    print(f"Nieuw lid: {member}")  # log in terminal

    # Pak direct het kanaal met ID
    channel = bot.get_channel(1410221365923024970)

    if channel:
        await channel.send(
            f"Welkom {member.mention}! 🎉 Fijn dat je er bent bij Stichting YALC!\n\n"
            "📜 **Regels:**\n"
            "1. Wees respectvol\n"
            "2. Geen spam\n"
            "3. Volg de richtlijnen van de server"
        )
    else:
        print("Kanaal niet gevonden!")

@bot.command()
async def test_welcome(ctx):
    print("Command ontvangen!")  # check of het commando afgaat
    channel = bot.get_channel(1410221365923024970)  # vervang door jouw kanaal-ID
    print(channel)  # check of het kanaal gevonden wordt

    if channel:
        await channel.send("Dit is een testbericht!")
    else:
        await ctx.send("Kanaal niet gevonden!")



# Keep-alive webserver (voor Replit/Glitch)
app = Flask('')

@app.route('/')
def home():
    return "Buddy Bot is online!"

def run():
    port = int(os.environ.get("PORT", 3000))
    app.run(host='0.0.0.0', port=port)

# Start webserver in aparte thread
def keep_alive():
    t = Thread(target=run)
    t.start()

keep_alive()

# Start de bot
bot.run(TOKEN)