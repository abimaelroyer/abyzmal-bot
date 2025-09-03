import asyncio
import json
import logging
import os
import random
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import discord
import pytz
import requests
from discord.ext import commands, tasks
from twitchAPI.twitch import Twitch

from xp import getTopXP, init, getXp, updateXp
  
import os

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(script_dir, "inspire.json"), "r", encoding="utf-8") as f:
    inspire_list = json.load(f)

with open(os.path.join(script_dir, "jokes.json"), "r", encoding="utf-8") as f:
    jokes = json.load(f)
    
PATCH_FILE = Path(os.path.join(script_dir, "patchnotes.json"))
with PATCH_FILE.open("r", encoding="utf-8") as f:
    patchData = json.load(f)
    current_version = patchData.get("current_version")
    last_posted = patchData.get("last_posted_version")
    notes = patchData.get("notes", [])
    if current_version and current_version != last_posted:
        # Find the current version info
        version_info = next(
            (n for n in patchData.get("notes", []) if n.get("version") == current_version),
            None
        )

with open(os.path.join(script_dir, "quote.json"), "r", encoding="utf-8") as f:
    quote_list = json.load(f)
    
ROADMAP_FILE = Path(os.path.join(script_dir, "roadmap.json"))
with ROADMAP_FILE.open("r", encoding="utf-8") as f:
    roadmapData = json.load(f)
roadmap_entries = roadmapData.get("roadmap", [])

with open(os.path.join(script_dir, "serverConfigs.json"), "r") as f:
    settings = json.load(f)

with open(os.path.join(script_dir, "trivia.json"), "r", encoding="utf-8") as f:
    questions = json.load(f)

with open(os.path.join(script_dir, "ToDoList.json"), "r", encoding="utf-8") as f:
    ToDoList = json.load(f)

with open(os.path.join(script_dir, "wisdom.json"), "r", encoding="utf-8") as f:
    wisdom_list = json.load(f)

with open(os.path.join(script_dir, "wordleList.json"), "r", encoding="utf-8") as f:
    wordle_list = set(json.load(f))

with open(os.path.join(script_dir, "wordList.json"), "r", encoding="utf-8") as f:
    words = json.load(f)


# ───────────────────────────────
# Config & Globals
# ───────────────────────────────
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True
intents.message_content = True

handler = logging.FileHandler(filename='discord.log', encoding='utf8', mode='w')

TOKEN = os.environ["DISCORD_TOKEN"]

guild_streamers = {}
guild_stream_channels = {}

xpCooldown = 60  # seconds
user_xp = {}      
user_levels = {}  

XP_PER_MESSAGE = (5, 15)
HouseofGrace = 798914333802496002
StreamerPing = 851287572453130240
Recruit = 798686544739303436

# Twitch API
twitch_client_id = "d69y0rkoovtt1celx22e957pdcrjhu"
twitch_client_secret = "opziv6mhtd372hr67y2tnf2u6ww155"
twitch = Twitch(twitch_client_id, twitch_client_secret)
twitch.authenticate_app
twitchApiEndpoint = "https://api.twitch.tv/helix"

est = pytz.timezone("US/Eastern")

versionUpdate = True
currentVersion = "0.4.5"

AdminPerms = [525885316050190348, 607020728075812875, 716017948078112830, 301485862557057025, 293827979191255053]
devPerm = 525885316050190348

prefixes = {}

for guild_id, guild_config in settings.items():
    guild_streamers[guild_id] = guild_config.get("streamers", [])
    stream_channel_id = guild_config.get("streamAnnouncements")
    if stream_channel_id:
        guild_stream_channels[guild_id] = int(stream_channel_id)

last_status = {guild_id: {user: False for user in streamers} for guild_id, streamers in guild_streamers.items()}

# ───────────────────────────────
# XP Math
# ───────────────────────────────
def xptoNext(level: int) -> int:
    return 5 * (level**2) + 50 * level + 100

def totalLevelXP(level: int) -> int:
    L = level
    return (5 * (L - 1) * L * (2 * L - 1)) // 6 + 25 * L * (L - 1) + 100 * L

def calculate_level(xp: int) -> int:
    lo, hi = 0, 10000
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if totalLevelXP(mid) <= xp:
            lo = mid
        else:
            hi = mid - 1
    return lo

# ───────────────────────────────
# Helper Functions
# ───────────────────────────────

def get_prefix(bot, message):
    if not message.guild:
        return "!!"
    guild_id = str(message.guild.id)
    if guild_id in settings:
        return settings[guild_id].get("prefix", "!!")
    return "!!"
    
bot = commands.Bot(command_prefix=get_prefix, intents=intents, help_command=None)

def progress_bar(current: int, total: int, width: int = 20) -> str:
    if total <= 0:
        return "—" * width
    filled = int((current / total) * width)
    return "█" * max(0, min(filled, width)) + "░" * max(0, width - filled)

def _fmt_list(items):
    return "\n".join(f"• {i}" for i in items) if items else "—"

def _entry_embed(entry, current_version_label: str, bot_user):
    e = createEmbed(
        title=f"A.R.I.A. Patch Notes — v{entry.get('version','')}",
        description=entry.get("announcement", "—"),
        color=discord.Color.teal()
    )
    e.add_field(name="Version", value=f"v{entry.get('version','')}", inline=True)
    e.add_field(name="Date", value=entry.get("date","—"), inline=True)
    e.add_field(name="Status", value=entry.get("status","—"), inline=True)
    e.add_field(name="New & Updated", value=_fmt_list(entry.get("changes", []))[:1024] or "—", inline=False)
    e.add_field(name="Improvements", value=_fmt_list(entry.get("improvements", []))[:1024] or "—", inline=False)
    e.add_field(name="Fixes", value=_fmt_list(entry.get("fixes", []))[:1024] or "—", inline=False)

    avatar_url = getattr(bot_user, "display_avatar", None)
    avatar_url = avatar_url.url if avatar_url else (bot_user.avatar.url if bot_user.avatar else None)
    if avatar_url:
        e.set_author(name=f"{bot_user.name} • current v{current_version_label}", icon_url=avatar_url)
        e.set_thumbnail(url=avatar_url)
    e.set_footer(text="A.R.I.A. © 2025")
    return e

def _find_entry(notes, ver: str):
    for n in notes:
        if n.get("version","").lower() == ver.lower():
            return n
    return None

def createEmbed(title, description, color, footer: str | None = None, fields=None):
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_author(name=bot.user.name, icon_url=bot.user.display_avatar.url)
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.set_footer(text="A.R.I.A. © 2025")
    
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)

    return embed

AccessToken = get_app_access_token(twitch_client_id, twitch_client_secret)

APIHeaders = {
    "Client-ID": "d69y0rkoovtt1celx22e957pdcrjhu",
    "Authorization": f"Bearer {AccessToken}"
}

async def get_app_access_token():
    url = "https://id.twitch.tv/oauth2/token"
    params = {
        "client_id": twitch_client_id,
        "client_secret": twitch_client_secret,
        "grant_type": "client_credentials"
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, params=params) as resp:
            data = await resp.json()
            return data["access_token"]

async def get_user_id(username: str, headers):
    url = "https://api.twitch.tv/helix/users"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params={"login": username}) as resp:
            data = await resp.json()
            if data["data"]:
                return data["data"][0]["id"]
            return None

async def get_stream_data(user_id: str, headers):
    url = "https://api.twitch.tv/helix/streams"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params={"user_id": user_id}) as resp:
            data = await resp.json()
            if data["data"]:
                stream = data["data"][0]
                return {
                    "title": stream["title"],
                    "game": stream["game_name"],
                    "thumbnail": stream["thumbnail_url"].replace("{width}", "320").replace("{height}", "180"),
                }
            return None

async def check_stream(username: str, headers):
    try:
        user_id = await get_user_id(username, headers)
        if not user_id:
            print(f"User {username} not found.")
            return None
        return await get_stream_data(user_id, headers)
    except Exception as e:
        print(f"Error checking {username}: {e}")
        return None

@tasks.loop(seconds=30)
async def check_streams_loop():
    access_token = await get_app_access_token()
    headers = {
        "Client-ID": twitch_client_id,
        "Authorization": f"Bearer {access_token}"
    }

    for guild_id, streamers in guild_streamers.items():
        stream_channel_id = guild_stream_channels.get(guild_id)
        stream_channel = bot.get_channel(stream_channel_id)
        if not stream_channel:
            continue

        streamer_ping_role = stream_channel.guild.get_role(StreamerPing)

        for username in streamers:
            stream = await check_stream(username, headers)
            if stream and not last_status[guild_id][username]:
                embed = discord.Embed(
                    title=f"{username} is LIVE!",
                    description=f"{stream['title']}\n🎮 Playing: {stream['game']}",
                    url=f"https://twitch.tv/{username}",
                    color=discord.Color.purple()
                )
                embed.set_image(url=stream['thumbnail'])
                await stream_channel.send(f"{streamer_ping_role.mention if streamer_ping_role else ''} {username} just went live!", embed=embed)

            last_status[guild_id][username] = bool(stream)


def get_clip(username: str, limit: int = 5, days: int = 30) -> list[dict]:
    """
    Return up to `limit` recent clips for `username` from the last `days` days.
    Each item is a Helix clip dict (has 'url', 'title', 'thumbnail_url', 'view_count', 'created_at', etc).
    """
    broadcaster_id = get_user_id(username)
    if not broadcaster_id:
        return []

    started_at = (datetime.now(est) - timedelta(days=days)).isoformat()

    params = {
        "broadcaster_id": broadcaster_id,
        "first": min(max(limit, 1), 100),
        "started_at": started_at,
    }
    url = f"{twitchApiEndpoint}/clips"
    r = requests.get(url, headers=APIHeaders, params=params, timeout=15)
    if r.status_code == 401:
        raise RuntimeError("Unauthorized (401): refresh your app access token.")
    r.raise_for_status()

    return r.json().get("data", [])
    
def get_random_clip(username: str, days: int = 30) -> dict | None:
    clips = get_clip(username, limit=20, days=days)
    return random.choice(clips) if clips else None

def save_settings():
    with open(os.path.join(script_dir, "serverConfigs.json"), "w") as f:
        json.dump(settings, f, indent=4)


# ───────────────────────────────
# Views (UI)
# ───────────────────────────────
class pageView(discord.ui.View):
    def __init__(self, ctx: commands.Context, pages: list[discord.Embed], start_index: int = 0, timeout: float = 120.0):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.pages = pages
        self.index = max(0, min(start_index, len(pages) - 1))
        self.message: discord.Message | None = None
        if len(self.pages) <= 1:
            for child in self.children:
                if isinstance(child, discord.ui.Button) and child.custom_id in {"first","prev","next","last"}:
                    child.disabled = True

    async def _update(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command invoker can use these controls.", ephemeral=True)
            return
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    async def on_timeout(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

    @discord.ui.button(label="⏮ First", style=discord.ButtonStyle.secondary, custom_id="first")
    async def first(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = 0
        await self._update(interaction)

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary, custom_id="prev")
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.index > 0:
            self.index -= 1
        await self._update(interaction)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, custom_id="next")
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.index < len(self.pages) - 1:
            self.index += 1
        await self._update(interaction)

    @discord.ui.button(label="Last ⏭", style=discord.ButtonStyle.secondary, custom_id="last")
    async def last(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = len(self.pages) - 1
        await self._update(interaction)

    @discord.ui.button(label="✖ Close", style=discord.ButtonStyle.danger, custom_id="close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command invoker can close this.", ephemeral=True)
            return
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        await interaction.response.edit_message(view=self)

# ───────────────────────────────
# Events
# ───────────────────────────────
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return  # Ignore command not found errors
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing required argument: {error.param}")
    else:
        print(f"Command error: {error}")
        await ctx.send(f"❌ An error occurred: {str(error)}")

@bot.event
async def on_ready():
    global headers

    # --- LOCAL TIME & STARTUP MESSAGE ---
    ny_tz = pytz.timezone('America/New_York')
    now = datetime.now(ny_tz)
    t = now.strftime("%I:%M %p").lstrip('0')

    startupMsgs = [
        f"A.R.I.A. online. Local Time is now {t}. Let's get started!",
        f"System check: all green. Time check: {t} Est. A.R.I.A.'s ready to go!",
        f"Good day! It's {t} — A.R.I.A. here, ready to assist!",
    ]
    startUpMsg = random.choice(startupMsgs)
    print(startUpMsg)

    for guild in bot.guilds:
        guild_id = str(guild.id)
        channels = settings.get(guild_id, {}).get("channels", {})

        devRoom = bot.get_channel(channels.get("dev_room"))
        if devRoom:
            await devRoom.send("A.R.I.A. online!")

        patchChannel = bot.get_channel(channels.get("patch_notes"))
        if patchChannel and version_info:
            embed = createEmbed(
                title=f"🚀 A.R.I.A. Bot — Version {version_info.get('version')} Patch Notes",
                description=version_info.get("announcement", ""),
                color=discord.Color.green()
            )
            await patchChannel.send(embed=embed)

    print(f"{bot.user} is online. Checking Twitch streams...")
    check_streams.start()

@bot.event
async def on_member_join(member: discord.Member):
    guild_id = str(member.guild.id)
    channels = settings.get(guild_id, {}).get("channels", {})
    welcome_channel = bot.get_channel(channels.get("welcome"))

    if welcome_channel:
        embed = createEmbed(
            title=f"Welcome {member.name}!",
            description=f"Hello {member.mention}, welcome to the server!\n Make sure to read the rules and have a great time!",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=member.avatar.url if member.avatar else "")
        await welcome_channel.send(embed=embed)

    # Optionally assign a default role
    default_role = discord.utils.get(member.guild.roles, id=798686544739303436)  # replace with role ID
    if default_role:
        await member.add_roles(default_role)

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return  # Ignore messages from bots

    user_id = str(message.author.id)

    # Give random XP per message
    gained_xp = random.randint(XP_PER_MESSAGE[0], XP_PER_MESSAGE[1])
    user_xp[user_id] = user_xp.get(user_id, 0) + gained_xp

    # Check for level-up
    old_level = user_levels.get(user_id, 0)
    new_level = calculate_level(user_xp[user_id])

    if new_level > old_level:
        user_levels[user_id] = new_level
        await message.channel.send(
            f"🎉 Congrats {message.author.mention}, you leveled up to **Level {new_level}**!"
        )

    # Make sure commands still work
    await bot.process_commands(message)
   
# ───────────────────────────────
# Commands — Info/Utility
# ───────────────────────────────

# !!hello
@bot.command(name="hello", aliases=["Hello", "hi", "Hi", "hey", "Hey"])
async def hello(ctx: commands.Context):
    "Say hi to A.R.I.A!"
    await ctx.send(f"Hello! {ctx.author.mention}!")

# !!help
@bot.command(name="help", aliases=["Help"])
async def help_command(ctx: commands.Context):
    """Shows this help message"""
    cmds = sorted(bot.commands, key=lambda c: c.name.lower())
    entries = []

    for command in cmds:
        if command.hidden:
            continue
        try:
            if not await command.can_run(ctx):
                continue
        except Exception:
            continue

        usage = f"!!{command.qualified_name}"
        if command.signature:
            usage += f" {command.signature}"
        desc = command.help or "No description provided."
        entries.append((usage, desc))

    per_page = 5
    pages = []
    for i in range(0, len(entries), per_page):
        chunk = entries[i:i + per_page]

        embed = createEmbed(
            title="📘 A.R.I.A. Commands",
            description="Available commands:",
            color=discord.Color.green()
        )
        for name, desc in chunk:
            embed.add_field(name=name, value=desc, inline=False)
        embed.set_footer(text=f"A.R.I.A. © 2025 | Page {len(pages)+1}")
        pages.append(embed)

    if not pages:
        await ctx.send("No available commands.")
        return

    view = pageView(ctx, pages)
    view.message = await ctx.send(embed=pages[0], view=view)

# !!info
@bot.command(name="info", aliases=["Info"])
async def info(ctx: commands.Context):
    "A.R.I.A. introduces herself!"
    await ctx.send(
        f"💠 **Initialization Complete.**\n\n"
        f"Greetings, {ctx.author.mention} — I am **A.R.I.A.**\n"
        f"(*Another Really Intelligent Assistant*).\n\n"
        f"🗓 **Creation Date:** June 20th, 2025\n"
        f"👤 **Creator:** debbie.downer — DM him for questions and feedback.\n\n"
        f"📖 **Commands:** Type `!!help` to view my full list of capabilities.\n\n"
        f"🛰 **Status:** Semi operational, system shutdowns are frequent. It’s an honor to make your acquaintance."
    )
    
# !!ping
@bot.command(name="ping", aliases=["Ping"])
async def ping_cmd(ctx: commands.Context):
    "Show bot latency."
    await ctx.send(f"Pong! {round(bot.latency*1000)} ms")

# !!avatar
@bot.command(name="avatar", aliases=["Avatar"])
async def avatar(ctx: commands.Context, member: discord.Member | None = None):
    "Shows a user's avatar."
    target = member or ctx.author
    embed = createEmbed(
        title=f"{target.display_name}'s Avatar",
        description = None,
        color=discord.Color(0x493657)
    )
    embed.set_image(url=target.display_avatar.url)
    await ctx.send(embed=embed)

# ───────────────────────────────
# Commands — Fun
# ───────────────────────────────

# !!coinflip
@bot.command(name="coinflip", aliases=["Coinflip"])
async def coinflip(ctx: commands.Context):
    "Heads I win, tails you lose."
    await ctx.send(random.choice(["Heads", "Tails"]))

# !!diceroll
@bot.command(name="diceroll", aliases=["Diceroll", "dr", "roll"])
async def diceroll(ctx: commands.Context, dice: str = "1d6"):
    "Rolls a dice in NdN format. It's optional to specify the dice."
    try:
        n, d = dice.lower().split("d")
        n, d = int(n), int(d)
        n = max(1, min(n, 20))
        d = max(2, min(d, 1000))
        rolls = [random.randint(1, d) for _ in range(n)]
        total = sum(rolls)
        await ctx.send(f"{ctx.author.mention} rolled a **{total}** \n ({dice}: {rolls})")
    except Exception:
        await ctx.send("Format: `!!roll NdM` e.g. `!!roll 2d6`")
   
# !!hangman
HANGMAN_PICS = [
    "```\n +---+\n     |\n     |\n     |\n    ===\n```",
    "```\n +---+\n O   |\n     |\n     |\n    ===\n```",
    "```\n +---+\n O   |\n |   |\n     |\n    ===\n```",
    "```\n +---+\n O   |\n/|   |\n     |\n    ===\n```",
    "```\n +---+\n O   |\n/|\\  |\n     |\n    ===\n```",
    "```\n +---+\n O   |\n/|\\  |\n/    |\n    ===\n```",
    "```\n +---+\n O   |\n/|\\  |\n/ \\  |\n    ===\n```"
]

# !!hangman
@bot.command(name="hangman", aliases=["Hangman"])
async def hangman(ctx: commands.Context):
    "Play a game of hangman"

    word = random.choice(words)
    display_word = ["_" if c.isalpha() else c for c in word]
    guessedLetters = set()
    incorrectGuesses = 0
    Attempts = len(HANGMAN_PICS) - 1

    embed = createEmbed(
        title="🕹 Hangman Game",
        description=(
            f"{HANGMAN_PICS[incorrectGuesses]}\n\n"
            f"Word: {' '.join(display_word)}\n"
            f"Guessed letters: None\n"
            f"Guesses remaining: {Attempts - incorrectGuesses}"
        ),
        color=discord.Color.orange(),
        footer="Type one letter per guess. You have 60 seconds per guess."
    )
    message = await ctx.send(embed=embed)

    while incorrectGuesses < Attempts and "_" in display_word:
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and len(m.content) == 1

        try:
            msg = await bot.wait_for("message", check=check, timeout=60.0)
            guess = msg.content.lower()

            if guess in guessedLetters:
                await ctx.send(f"⚠️ You already guessed `{guess}`!")
                continue

            guessedLetters.add(guess)

            # Reveal matching letters (case-insensitive)
            if guess in word.lower():
                for i, c in enumerate(word):
                    if c.lower() == guess:
                        display_word[i] = c
            else:
                incorrectGuesses += 1

            embed.description = (
                f"{HANGMAN_PICS[incorrectGuesses]}\n\n"
                f"Word: {' '.join(display_word)}\n"
                f"Guessed letters: {', '.join(sorted(guessedLetters))}\n"
                f"Guesses remaining: {Attempts - incorrectGuesses}"
            )
            await message.edit(embed=embed)

        except asyncio.TimeoutError:
            embed.title = "⏰ Time's up!"
            embed.description = (
                (embed.description or "") +
                f"\n\nThe word was **{word}**."
            )
            await message.edit(embed=embed)
            return

    if "_" not in display_word:
        embed.title = "🎉 You Win!"
    else:
        embed.title = "Game Over!"
        display_word = list(word)  # reveal full word

    embed.description = (
        f"{HANGMAN_PICS[incorrectGuesses]}\n\n"
        f"Word: {' '.join(display_word)}\n"
        f"Guessed letters: {', '.join(sorted(guessedLetters))}"
    )
    await message.edit(embed=embed)
    
# !!inspire
@bot.command(name="inspire", aliases=["Inspire"])
async def inspire(ctx: commands.Context):
    "Get some motivation from A.R.I.A!"
    
    motivation = random.choice(inspire_list)
    await ctx.send(f"{motivation}")

# !!joke
@bot.command(name="joke", aliases=["Joke"])
async def joke(ctx: commands.Context):
    "Get a random joke! You better laugh"
    
    joke = random.choice(jokes)
    await ctx.send(f"{joke}")
     
# !!numguess
@bot.command(name="numguess", aliases=["Numguess"])
async def numguess(ctx: commands.Context):
    "Guess a number between 1 and 100."
    num = random.randint(1, 100)
    guessed = False
    currentGuesses = 0
    await ctx.send("I'm thinking of a number between 1 and 100. You have 30 chances to guess it!")

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    while not guessed and currentGuesses < 10:
        try:
            msg = await bot.wait_for("message", check=check, timeout=30.0)

            if not msg.content.isdigit():
                await ctx.send("⚠️ Please enter a valid number.")
                continue

            guess = int(msg.content)

            if not 1 <= guess <= 100:
                await ctx.send("🚫 Only numbers between 1 and 100 are allowed.")
                continue

            currentGuesses += 1

            if guess == num:
                await ctx.send(f"🎉 Correct! The number was {num}. You guessed it in {currentGuesses} tries.")
                guessed = True
            elif guess < num:
                await ctx.send("📉 Too low!")
            else:
                await ctx.send("📈 Too high!")

        except asyncio.TimeoutError:
            await ctx.send("⏰ Time's up! You took too long to guess.")
            break

    if not guessed:
        await ctx.send(f"❌ You didn't guess the number. It was **{num}**.")
   
# !!pp
@bot.command(name="pp")
async def ppsize(ctx: commands.Context):
    "Ayo? Why you asking?"
    pp_size = random.randint(1, 12)
    if 1 < pp_size <= 4:
        await ctx.send(f"Your pp size is {pp_size} inches. Yikes.")
    elif 4 < pp_size <= 7:
        await ctx.send(f"Your pp size is {pp_size} inches. Not bad.")
    elif 7 < pp_size <= 10:
        await ctx.send(f"Your pp size is {pp_size} inches. You kinda packing.")
    else:
        await ctx.send(f"Your pp size is {pp_size} inches. Jesus dude 👀.")

# !!quote
@bot.command(name="quote", aliases=["Quote"])
async def quote(ctx: commands.Context):
    "Get a quote from A.R.I.A!"
        
    quote = random.choice(quote_list)
    await ctx.send(f"{quote}")

# !!trivia
active_trivia_parties = {}
@bot.command(name="trivia", aliases=["Trivia"])
async def trivia(ctx: commands.Context, *, arg=None):
    "Answer some trivia!"
    if arg == "party":
        await trviaMultiplayer(ctx)
        return

    q = random.choice(questions)
    question = q["question"]
    correct = q["correct_answer"]
    options = q["incorrect_answers"] + [correct]
    random.shuffle(options)

    letters = ["A", "B", "C", "D"]
    choice_map = dict(zip(letters, options))
    correct_letter = next(k for k, v in choice_map.items() if v == correct)

    embed = createEmbed(
        title="🧠 Trivia Time!",
        description=question,
        color=discord.Color(0xA9DEF9)
    )
    embed.add_field(
        name="Choices",
        value="\n".join(f"{letter}. {choice_map[letter]}" for letter in letters),
        inline=False
    )
    embed.set_footer(text="A.R.I.A. © 2025 | Type A, B, C, or D to answer. You have 15 seconds.")
    await ctx.send(embed=embed)

    def check(m):
        return (
            m.author == ctx.author and 
            m.channel == ctx.channel and 
            m.content.upper() in letters
        )

    try:
        msg = await bot.wait_for("message", check=check, timeout=15.0)
    except asyncio.TimeoutError:
        await ctx.send(f"⏰ Time's up! You didn't answer in time. The correct answer was **{correct}**.")
        return

    if msg.content.upper() == correct_letter:
        await ctx.send("✅ Correct! You got it right.")
    else:
        await ctx.send(f"❌ Wrong! The correct answer was **{correct}**")
    
# trivia multiplayer
async def trviaMultiplayer(ctx):
    channel_id = ctx.channel.id
    active_trivia_parties[channel_id] = True
    joinEmoji = "🎉"
    joinMsg = await ctx.send(f"React with {joinEmoji} to join the trivia party! You have 10 seconds!")
    await joinMsg.add_reaction(joinEmoji)

    def check(reaction, user):
        return (
            reaction.message.id == joinMsg.id and str(reaction.emoji) == joinEmoji and not user.bot
        )

    players = set()
    try:
        while True:
            reaction, user = await bot.wait_for('reaction_add', timeout=10.0, check=check)
            players.add(user)
    except asyncio.TimeoutError:
        if not players:
            await ctx.send("No one joined, cancelling.")
            return
        player_mentions = ', '.join([player.mention for player in players])
        await ctx.send(f"Trivia Party starting with players: {player_mentions}")

    scores = {player: 0 for player in players}
    letters = ["A", "B", "C", "D"]

    while active_trivia_parties.get(channel_id, False):
        q = random.choice(questions)
        question = q["question"]
        correct = q["correct_answer"]
        options = q["incorrect_answers"] + [correct]
        random.shuffle(options)

        choice_map = dict(zip(letters, options))
        correct_letter = next(k for k, v in choice_map.items() if v == correct)

        embed = createEmbed(
            title="🧠 Trivia Party!",
            description=question,
            color=discord.Color.blue(),
            footer = "A.R.I.A. © 2025 | Type A, B, C, or D to answer. You have 15 seconds.")
        
        embed.add_field(
            name="Choices",
            value="\n".join(f"{letter}. {choice_map[letter]}" for letter in letters),
            inline=False
        )
        await ctx.send(embed=embed)

        correct_answers = []
        answered_players = set()

        def answer_check(m):
            return (
                m.channel == ctx.channel and
                m.author in players and
                m.content.upper() in letters and
                m.author not in answered_players
            )

        correct_answers = []
        answered_players = set()
        responses = {}

        end_time = asyncio.get_event_loop().time() + 15
        while asyncio.get_event_loop().time() < end_time and len(answered_players) < len(players):
            try:
                timeout = end_time - asyncio.get_event_loop().time()
                msg = await bot.wait_for("message", check=answer_check, timeout=timeout)
                answered_players.add(msg.author)
                responses[msg.author] = msg.content.upper()
            except asyncio.TimeoutError:
                break

        for player, response in responses.items():
            if response == correct_letter:
                correct_answers.append(player)

        await ctx.send(f"🕒 Time's up! The correct answer was **{correct}**.")

        if correct_answers:
            correct_mentions = ', '.join([p.mention for p in correct_answers])
            await ctx.send(f"✅ Players who answered correctly: {correct_mentions}")
        else:
            await ctx.send("❌ No one got it right this round.")

        points_map = [10, 5, 3] + [2] * 10
        for i, player in enumerate(correct_answers):
            scores[player] += points_map[i]

        score_msg = "📊 **Current Scores:**\n"
        for player, score in scores.items():
            score_msg += f"**{player.display_name}**: {score}\n"
        await ctx.send(score_msg)

        if not active_trivia_parties.get(channel_id, False):
            await ctx.send("🛑 The Trivia Party has been cancelled.")
            break
            
    for player, score in scores.items():
        if score >= 100:
            await ctx.send(f"🏆 {player.mention} wins the Trivia Party with **{score}** points! Congratulations!")
            active_trivia_parties[channel_id] = False
            break


# !!trivia stop
@bot.command(name="triviastop", aliases=["stoptrivia"])
async def cancel_trivia(ctx: commands.Context):
    "Stops the active trivia party in the channel."
    channel_id = ctx.channel.id
    if active_trivia_parties.get(channel_id, False):
        active_trivia_parties[channel_id] = False
        await ctx.send("🛑 Trivia Party has been cancelled.")
    else:
        await ctx.send("⚠️ No active Trivia Party to cancel in this channel.")

# !!wisdom
@bot.command(name="wisdom", aliases=["Wisdom"])
async def wisdom(ctx: commands.Context):
    "Get some wisdom from A.R.I.A"
        
    wisdom = random.choice(wisdom_list)
    await ctx.send(f"{wisdom}")
        
# !!wordle
activeWordles = {}
def score_guess(guess: str, answer: str) -> list[str]:
            res = ["b"] * 5
            counts = Counter(answer)

            # Greens
            for i, ch in enumerate(guess):
                if ch == answer[i]:
                    res[i] = "g"
                    counts[ch] -= 1

            # Yellows
            for i, ch in enumerate(guess):
                if res[i] == "b" and counts.get(ch, 0) > 0:
                    res[i] = "y"
                    counts[ch] -= 1

            return res

def render_grid(rows: list[str]) -> str:
            return "\n".join(rows) if rows else "No guesses yet."

@bot.command(name="wordle", aliases=["Wordle"])
async def wordle(ctx: commands.Context):
                    "Play the daily Wordle in DMs."
                    EMOJI = {"g": "🟩", "y": "🟨", "b": "⬛"}        
                    user = ctx.author

                    if activeWordles.get(user.id, False):
                        await ctx.send(f"{user.mention}, you already have a Wordle game running in DMs!")
                        return

                    activeWordles[user.id] = True
                    await ctx.send(f"{user.mention}, I've sent you a DM with your Wordle game!")

                    try:
                        # Fetch the daily solution
                        today = datetime.today()
                        formatted_date = today.strftime("%Y-%m-%d")
                        url = f"https://www.nytimes.com/svc/wordle/v2/{formatted_date}.json"
                        response = requests.get(url).json()
                        wordle = response["solution"].lower()

                        guessed = False
                        remainingAttempts = 6
                        rows: list[str] = []

                        embed = createEmbed(
                            title="🟩 Wordle",
                            description=f"Guess the daily Wordle. You have **{remainingAttempts}** guesses left.",
                            color=discord.Color.green(),
                            footer="A.R.I.A. © 2025 | Type your guesses in this DM."
                        )
                        msg = await user.send(embed=embed)

                        def check(m: discord.Message):
                            return (
                                m.author == user
                                and isinstance(m.channel, discord.DMChannel)
                                and len(m.content) == 5
                                and m.content.isalpha()
                            )

                        while remainingAttempts > 0 and not guessed:
                            try:
                                user_msg = await bot.wait_for("message", check=check, timeout=600.0)
                                guess = user_msg.content.lower()

                                if guess not in wordle_list:
                                    await user.send("⚠️ Not a valid word. Try again.")
                                    continue

                                scored = score_guess(guess, wordle)
                                row = "".join(EMOJI[c] for c in scored)
                                rows.append(row)

                                if guess == wordle:
                                    guessed = True
                                    embed.title = "🎉 Wordle — Solved!"
                                    embed.description = (
                                        f"{render_grid(rows)}\n\n"
                                        f"**Solved in {len(rows)}!**\n"
                                        f"Answer: ||{wordle.upper()}||"
                                    )
                                else:
                                    remainingAttempts -= 1
                                    embed.title = "🟩🟨⬛ Wordle"
                                    embed.description = (
                                        f"{render_grid(rows)}\n\n"
                                        f"Attempts remaining: **{remainingAttempts}**"
                                    )

                                await msg.edit(embed=embed)

                            except asyncio.TimeoutError:
                                embed.title = "⏰ Wordle — Timed Out"
                                embed.description = (
                                    f"{render_grid(rows)}\n\n"
                                    f"Time expired. The word was: **||{wordle.upper()}||**."
                                )
                                await msg.edit(embed=embed)
                                return

                        # If player ran out of attempts
                        if not guessed and remainingAttempts == 0:
                            embed.title = "🛑 Wordle — Out of Attempts"
                            embed.description = (
                                f"{render_grid(rows)}\n\n"
                                f"The word was **{wordle.upper()}**."
                            )
                            await msg.edit(embed=embed)

                    finally:
                        activeWordles.pop(user.id, None)

# ───────────────────────────────
# Commands — XP/Leaderboard
# ───────────────────────────────

# !!rank
@bot.command(name="rank", aliases=["Rank"])
async def rank(ctx: commands.Context, member: discord.Member = None):
    "Check your XP or someone else's XP"
    try:
        target = member or ctx.author
        data = await getXp(str(target.id))
        lvl = calculate_level(data["xp"])
        cur_lvl_floor = totalLevelXP(lvl)
        next_lvl_floor = totalLevelXP(lvl + 1)
        into_level = data["xp"] - cur_lvl_floor
        span = next_lvl_floor - cur_lvl_floor
        to_next = max(0, span - into_level)
        pct = 0 if span == 0 else (into_level / span) * 100
        bar = progress_bar(into_level, span, width=24)
        embed = createEmbed(
            title=f"{target.display_name}'s XP",
            description=f"Level **{lvl}**",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Total XP", value=f"{data['xp']:,}", inline=True)
        embed.add_field(name="Next Level", value=f"{to_next:,} XP", inline=True)
        embed.add_field(name="Progress", value=f"{bar}\n{into_level:,}/{span:,} ({pct:.1f}%)", inline=False)
        await ctx.send(embed=embed)
    except Exception as e:
        data = await getXp(str((member or ctx.author).id))
        lvl = calculate_level(data["xp"])
        await ctx.send(f"{(member or ctx.author).mention} — XP: {data['xp']} | Level: {lvl}\n(Error in embed: {e!r})")

# !!leaderboard
@bot.command(name="leaderboard", aliases=["Leaderboard","lb"])
async def leaderboard(ctx: commands.Context, top: int = 10):
    "Shows the top XP leaderboard."
    try:
        top = max(1, min(top, 25))
        leaderboard_data = await getTopXP(top)
        if not leaderboard_data:
            await ctx.send("No XP data found yet.")
            return
        embed = createEmbed(
            title="XP Leaderboard",
            description=f"Top {top} users by XP",
            color=discord.Color.gold()
        )
        for i, (user_id, xp) in enumerate(leaderboard_data, start=1):
            user = ctx.guild.get_member(int(user_id))
            name = user.display_name if user else f"User ID {user_id}"
            level = calculate_level(xp)
            embed.add_field(name=f"#{i} — {name}", value=f"Level {level} — {xp:,} XP", inline=False)
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"Error loading leaderboard: {e!r}")
        
# ───────────────────────────────
# Commands — Server Info
# ───────────────────────────────

# !!perks
@bot.command(name="perks", aliases=["Perks"])
async def perks_cmd(ctx: commands.Context):
    "Shows the level role rewards and perks."
    level_roles = {
        "L1-4":  {"role_name": "Recruit",   "description": "Access to general chat, basic server permissions."},
        "L5-9":  {"role_name": "Private",   "description": "Unlock the ability to use custom emojis in chat."},
        "L10-14":{"role_name": "Corporal",  "description": "WIP lmao"},
        "L15-19":{"role_name": "Sergeant",  "description": "Eligible to participate in **giveaways** and small contests."},
        "L20-24":{"role_name": "Lieutenant","description": "WIP lmao"},
        "L25-29":{"role_name": "Captain",   "description": "WIP lmao"},
        "L30-34":{"role_name": "Major",     "description": "Your name gets a unique **color upgrade** to stand out in chat."},
        "L35-39":{"role_name": "Colonel",   "description": "Access to Streamer VC, early access to **beta server features**."},
        "L40-44":{"role_name": "Brigadier", "description": "Custom **epithet/title** visible to everyone."},
        "L45-49":{"role_name": "General",   "description": "Early access to event announcements & content previews."},
        "L50+":  {"role_name": "Admiral",   "description": "All perks unlocked + access to the **WaffleHut HQ chat**."},
    }
    embed = createEmbed(
        title="Level Role Rewards",
        description="Roles and perks you unlock as you level up.",
        color=discord.Color.pink()
    )
    embed.set_author(name=bot.user.name, icon_url=bot.user.display_avatar.url)
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    for lvl_range, info in level_roles.items():
        embed.add_field(name=f"{lvl_range}: {info['role_name']}", value=info["description"] or "—", inline=False)
    embed.set_footer(text="A.R.I.A. © 2025")
    await ctx.send(embed=embed)

# ───────────────────────────────
# Commands — Patchnotes
# ───────────────────────────────

# !!patchnotes
@bot.command(
    name="patchnotes",
    aliases=["Patchnotes", "patch", "Patch", "version", "Version"]
)
async def patchnotes(ctx: commands.Context, *, ver: str = "latest"):
        """
        Shows patch notes for a specific version or all versions.
        """
        try:
            if not notes:
                await ctx.send("No patch notes found.")
                return

            # Show all versions
            if ver.lower() == "all":
                pages = [_entry_embed(entry, current_version, bot.user) for entry in notes]
                view = pageView(ctx, pages, start_index=0, timeout=120.0)
                msg = await ctx.send(embed=pages[0], view=view)
                view.message = msg
                return

            # Show latest version
            if ver.lower() == "latest":
                entry = notes[0]
            else:
                entry = next((n for n in notes if n.get("version", "").lower() == ver.lower()), None)
                if not entry:
                    await ctx.send(
                        "Version not found. Try `!!patchnotes`, `!!patchnotes latest`, or `!!patchnotes all`."
                    )
                    return

            # Build and send embed
            embed = _entry_embed(entry, current_version, bot.user)
            await ctx.send(embed=embed)

        except Exception as ex:
            await ctx.send(f"❌ Error loading patch notes: {ex!r}")

# ───────────────────────────────
# Commands — Twitch
# ───────────────────────────────

# !!clip
@bot.command(name="clip", aliases=["Clip"])
async def clip_cmd(ctx, username: str):
    clip = get_random_clip(username.lower(), days=30)
    if not clip:
        await ctx.send(f"⚠️ No clips found for user: {username}")
        return

    embed = createEmbed(
        title=f"🎬 {clip['broadcaster_name']}'s Clip",
        description=f"[{clip['title']}]({clip['url']})\n📸 by {clip.get('creator_name','Unknown')}",
        color=discord.Color.purple()
    )
    embed.set_image(url=clip["thumbnail_url"])
    embed.set_footer(text=f"Views: {clip['view_count']} • Created: {clip['created_at'][:10]} • A.R.I.A. © 2025")
    await ctx.send(embed=embed)


# !!twitchInfo
@bot.command(name="twitchInfo", aliases=["TwitchInfo"])
async def twitchInfo(ctx, username: str):
    """Get basic Twitch info about a user"""
    try:
        # Initialize twitch object
        await twitch.authenticate_app([])

        # Get user info
        user_data = None
        async for user in twitch.get_users(logins=[username]):
            user_data = user
            break
        if not user_data:
            await ctx.send(f"⚠️ No Twitch user found with username: {username}")
            return

        # Get live stream status
        stream_data = None
        async for stream in twitch.get_streams(user_login=[username]):
            stream_data = stream
            break

        # Build response embed
        live_status = (
            f"🟢 **LIVE** — {stream_data.title} playing {stream_data.game_name}"
            if stream_data else
            "🔴 Offline"
        )

        embed = createEmbed(
            title=f"Twitch Info: {user_data.display_name}",
            description=f"{user_data.description or 'No description available.'}\n\n{live_status}",
            color=discord.Color.purple()
        )
        embed.set_thumbnail(url=user_data.profile_image_url)
        await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"❌ Error fetching Twitch info: {e}")

@bot.group(name="streamers", invoke_without_command=True)
async def streamers(ctx):
    """Base command for managing streamers."""
    await ctx.send("Available subcommands: add, remove, list")

@streamers.command(name="add")
async def add_streamer(ctx, streamer_name: str):
    guild_id = str(ctx.guild.id)
    if guild_id not in settings:
        settings[guild_id] = {}
    if "streamers" not in settings[guild_id]:
        settings[guild_id]["streamers"] = []

    if streamer_name in settings[guild_id]["streamers"]:
        await ctx.send(f"{streamer_name} is already in the list.")
    else:
        settings[guild_id]["streamers"].append(streamer_name)
        save_settings()
        await ctx.send(f"Added {streamer_name} to the streamers list.")

@streamers.command(name="remove")
async def remove_streamer(ctx, streamer_name: str):
    guild_id = str(ctx.guild.id)
    if guild_id in settings and "streamers" in settings[guild_id]:
        if streamer_name in settings[guild_id]["streamers"]:
            settings[guild_id]["streamers"].remove(streamer_name)
            save_settings()
            await ctx.send(f"Removed {streamer_name} from the streamers list.")
        else:
            await ctx.send(f"{streamer_name} is not in the list.")
    else:
        await ctx.send("No streamers list found for this server.")

@streamers.command(name="list")
async def list_streamers(ctx):
    guild_id = str(ctx.guild.id)
    streamers_list = settings.get(guild_id, {}).get("streamers", [])
    if streamers_list:
        await ctx.send("Current streamers:\n" + "\n".join(streamers_list))
    else:
        await ctx.send("No streamers have been added for this server yet.")

# ───────────────────────────────
# Commands — Admin
# ───────────────────────────────

# !!ban
@bot.command(name="ban", aliases=["Ban"])
@commands.has_permissions(administrator=True)
async def ban(ctx: commands.Context, member: discord.Member, *, reason=None):
    "Bans a member from the server. Specify a reason if needed."
    await member.ban(reason=reason)
    await ctx.send(f"{member.mention} has been banned from the server.")

# !!kick
@bot.command(name="kick", aliases=["Kick"])
@commands.has_permissions(administrator=True)
async def kick(ctx: commands.Context, member: discord.Member, *, reason=None):
    "Kicks a member from the server. Specify a reason if needed."
    await member.kick(reason=reason)
    await ctx.send(f"{member.mention} has been kicked from the server.")

# !!mute
@bot.command(name="mute", aliases=["Mute"])
@commands.has_permissions(manage_roles=True)
async def mute(ctx, member: discord.Member, duration: int, *, reason=None):
    muted_role = discord.utils.get(ctx.guild.roles, name="syBau")
    if not muted_role:
        await ctx.send("⚠️ 'Muted' role does not exist. Please create it first.")
        return

    await member.add_roles(muted_role, reason=reason)
    await ctx.send(f"🔇 {member.mention} has been muted for {duration} seconds. Reason: {reason or 'No reason provided.'}")

    await asyncio.sleep(duration)
    await member.remove_roles(muted_role)
    await ctx.send(f"🔊 {member.mention} has been unmuted.")

    
# !!setxp
@bot.command(name="setxp", aliases=["setXP"])
@commands.has_permissions(administrator=True)
async def setxp_cmd(ctx: commands.Context, member: discord.Member, xp: int):
    "(Admin only) Give a user a certain amount of total XP"
    xp = max(0, xp)
    await updateXp(str(member.id), xp, time.time())
    lvl = calculate_level(xp)
    await ctx.send(f"{member.mention} — XP set to {xp} | Level: {lvl}")

# ───────────────────────────────
# Commands — Server Config
# ───────────────────────────────

# !!setprefix
@bot.command(name="setprefix", aliases=["setPrefix"])
@commands.has_permissions(administrator=True)
async def setprefix(ctx: commands.Context, prefix: str):
    "Sets the bot's prefix for this server."
    await ctx.send("Enter the preferred prefix for bot commands. Default is !!")

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    
    msg = await bot.wait_for("message", check=check, timeout=30.0)
    userPrefix = msg.content
    await ctx.send(f"Prefix set to {userPrefix}")


# !!setChannel
@bot.command(name="setChannel", aliases=["setchannel"])
@commands.has_permissions(administrator=True)
async def setChannel(ctx: commands.Context):
    """Set a server channel for a specific function."""

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    # Step 1: Ask for the function type
    await ctx.send(
        "Enter the number of the function you want to set the channel for:\n"
        "1. Welcome\n"
        "2. General\n"
        "3. Patch Notes\n"
        "4. Stream Announcements"
    )

    try:
        msg = await bot.wait_for("message", check=check, timeout=30.0)
    except asyncio.TimeoutError:
        await ctx.send("You took too long to respond. Command cancelled.")
        return

    function = msg.content

    if function not in ["1", "2", "3", "4"]:
        await ctx.send("Invalid selection. Command cancelled.")
        return

    # Step 2: Ask for the channel
    await ctx.send("Please mention the channel you want to use (or enter the channel ID):")

    try:
        msg = await bot.wait_for("message", check=check, timeout=30.0)
    except asyncio.TimeoutError:
        await ctx.send("You took too long to respond. Command cancelled.")
        return

    # Try to get the channel from mention or ID
    channel = None
    if msg.channel_mentions:
        channel = msg.channel_mentions[0]  # First mentioned channel
    else:
        try:
            channel = await commands.TextChannelConverter().convert(ctx, msg.content)
        except commands.ChannelNotFound:
            await ctx.send("Invalid channel. Command cancelled.")
            return

    # Ensure the guild has a settings entry
    if ctx.guild.id not in settings:
        settings[ctx.guild.id] = {}

    # Map the function number to the JSON key
    key_map = {
        "1": "welcome",
        "2": "general",
        "3": "patchNotes",
        "4": "streamAnnouncements"
    }

    settings[ctx.guild.id][key_map[function]] = str(channel.id)
    await ctx.send(f"{key_map[function].capitalize()} channel set to {channel.mention}")

    # Save settings to JSON
    with open(os.path.join(script_dir, "serverConfigs.json"), "w") as f:
        json.dump(settings, f, indent=4)

# ───────────────────────────────
# Restricted Commands
# ───────────────────────────────

# !!roadmap
@bot.command(name="roadmap", aliases=["Roadmap"])
async def roadmap(ctx: commands.Context, *, ver: str = "latest"):
    if ctx.author.id not in AdminPerms:
        await ctx.send("Access denied.")
        return

    "Shows roadmap details for a specific version or all versions."
    try:
        entries = roadmap_entries
        if not entries:
            await ctx.send("No roadmap entries found.")
            return

        # Show all versions
        if ver.lower() == "all":
            pages = []
            for entry in entries:
                embed = createEmbed(
                    title=f"📌 A.R.I.A. Roadmap — v{entry.get('version','')}",
                    description=f"**{entry.get('focus','')}**",
                    color=discord.Color.teal()
                )
                embed.add_field(
                    name="Planned Features",
                    value="\n".join(f"• {item}" for item in entry.get("items", [])) or "—",
                    inline=False
                )
                embed.set_footer(text=f"Page {entries.index(entry)+1} of {len(entries)} • A.R.I.A. © 2025")
                pages.append(embed)

            view = pageView(ctx, pages, start_index=0, timeout=120.0)
            msg = await ctx.send(embed=pages[0], view=view)
            view.message = msg
            return

        # Show latest version
        if ver.lower() == "latest":
            entry = entries[0]
        else:
            entry = next((e for e in entries if e.get("version","").lower() == ver.lower()), None)
            if not entry:
                await ctx.send("Roadmap version not found. Try `!!roadmap`, `!!roadmap latest`, or `!!roadmap all`.")
                return

        embed = createEmbed(
            title=f"📌 A.R.I.A. Roadmap — v{entry.get('version','')}",
            description=f"**{entry.get('focus','')}**",
            color=discord.Color.teal()
        )
        embed.add_field(
            name="Planned Features",
            value="\n".join(f"• {item}" for item in entry.get("items", [])) or "—",
            inline=False
        )
        embed.set_footer(text="A.R.I.A. © 2025")

        await ctx.send(embed=embed)

    except Exception as ex:
        await ctx.send(f"Error loading roadmap: {ex!r}")

# !!toDo
@bot.command(name="toDo", aliases=["ToDo","todo"])
async def toDo(ctx: commands.Context):
    if ctx.author.id != devPerm:
        await ctx.send("Access denied.")
        return
    "Shows today's to-do list."
    today_tasks = ToDoList[0]["List"]
    description = "\n".join(f"• {task}" for task in today_tasks)
    embed = createEmbed(
        title="To Do List",
        description= f"Here's what needs to be done today: \n{description}",
        color=discord.Color.red(),
    )
    embed.set_footer(text = "A.R.I.A. © 2025 | Directed by God.")
    await ctx.send(embed=embed)

# ───────────────────────────────
# Boot
# ───────────────────────────────
async def main():
    await init()
    
if __name__ == "__main__":
    asyncio.run(main())
    bot.run(TOKEN, log_handler=handler, log_level=logging.DEBUG)