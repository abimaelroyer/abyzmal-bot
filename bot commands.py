import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
import random

load_dotenv()
token = os.getenv('DISCORD_TOKEN')

level1 = "Random [ Level 1 ]"
level2 = "Freshie [ Level 10 ]"

handler = logging.FileHandler(filename='discord.log', encoding='utf8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!! ', intents=intents)

@bot.event
async def on_ready():
    print(f"Tapped in, {bot.user.name}!")

#User join event
@bot.event
async def on_member_join(member):
    #channel 
    welcome = bot.get_channel(1386767674096488508)
    lounge = bot.get_channel(1385449370476085322)
    waffleLounge = bot.get_channel(798695601608589313)
    modLogs = bot.get_channel(798695601608589313)

    #role ids
    NewMember = member.guild.get_role(1387541601269841942)
    levelRole1 = discord.utils.get(member.guild.roles, names = level1)


    #print(f"[DEBUG] on_member_join fired for: {member} ({member.id})")
    if welcome:
        await welcome.send(f"Welcome to the server {member.mention}")
    
        if lounge:
            if NewMember:
                await lounge.send(
                    f"{NewMember.mention} — please welcome {member.mention} to the server!"
                    )
    #if levelRole1:
        #try:
            #await member.add_roles(levelRole1)
        
# hello
@bot.command()
async def hello(ctx):
    await ctx.send(f"What's good {ctx.author.mention}!")

#pp size
@bot.command()
async def ppSize(ctx):
    await ctx.send(f"Your pp size is {random.randrange(12)} inches long")
bot.run(token, log_handler=handler, log_level=logging.DEBUG)