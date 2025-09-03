# abyzmal-bot
Official script files for the all purpose abyzmal bot

# features
Welcome Messages: Sends a greeting in a designated channel when a new user joins.
Role Pings: Notifies specific roles to welcome newcomers.
Fun Commands:
Twitch Integration:

# prerequisites
Python 3.10+ installed
A Discord application with a bot token
python-dotenv, discord.py, logging, and random modules

# installation
Clone the repository:
git clone [repository-url]

# install dependencies
pip install -U discord.py python-dotenv

# configuration
Create a .env file in the project root:

DISCORD_TOKEN=your_discord_bot_token
(Optional) Add role/channel IDs as environment variables or hard-code them in bot.py:

Enable Intents in the Discord Developer Portal under your bot’s settings:
Enable Server Members Intent to receive member join events.
