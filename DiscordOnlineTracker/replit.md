# Discord Presence Bot

## Overview
A Python Discord bot that monitors when specific members come online and announces their presence in a designated channel. The bot includes a Flask keep-alive server to maintain uptime on Replit.

## Project Structure
- `main.py` - Main Discord bot logic with presence monitoring
- `keep_alive.py` - Flask web server running on port 8080 to keep Replit awake
- `pyproject.toml` - Python dependencies configuration
- `.gitignore` - Git ignore patterns for Python projects

## Features
- **Presence Monitoring**: Detects when members go online
- **Role-Based Announcements**: Custom messages based on member roles:
  - 👑 Queen (for "Queen" or "Queen👑" roles)
  - 🌟 Clan Master (for "Cᥣᥲᥒ Mᥲstᥱr🌟" role)
  - 🔫 OG-Impedance (for "OG-Impedance🔫" role)
  - ⭐ Impedance (for "Impedance⭐" role)
  - 🙂 Regular member (default)
- **Keep-Alive Server**: Flask server prevents Replit from sleeping

## Setup Instructions

### 1. Add Discord Bot Token
1. Go to Replit's Secrets tab (lock icon in left sidebar)
2. Add a new secret:
   - **Key**: `DISCORD_TOKEN`
   - **Value**: Your Discord bot token from the [Discord Developer Portal](https://discord.com/developers/applications)

### 2. Update Channel ID
In `main.py`, replace the placeholder channel ID:
```python
channel = client.get_channel(123456789012345678)  # Replace with your actual channel ID
```

### 3. Discord Bot Setup
Your bot needs these permissions in the Discord Developer Portal:
- **Privileged Gateway Intents**:
  - ✅ Presence Intent
  - ✅ Server Members Intent
- **Bot Permissions**:
  - Send Messages
  - Read Message History
  - View Channels

### 4. Run the Bot
Click the "Run" button in Replit, and the bot will start automatically.

## Technical Details
- **Language**: Python 3.11
- **Dependencies**: discord.py 2.6.4, Flask 3.1.2
- **Intents**: Members and Presences enabled
- **Port**: Flask runs on 8080 (background thread)

## Recent Changes
- November 11, 2025: Initial project creation with presence monitoring and keep-alive functionality
