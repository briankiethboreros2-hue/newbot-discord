# Discord Bot - Modular Cleanup System

A sophisticated Discord bot for managing user inactivity, cleanup, and poll-based voting systems.

## 🎯 Features

### Core Systems:
- **Activity Tracking** - Real-time user activity monitoring
- **Poll-Based Voting** - Formal voting system replacing reactions
- **Inactivity Management** - Auto-detection and demotion of inactive users
- **Cleanup System** - Ghost user detection and management
- **Role Management** - Safe role changes with hierarchy protection
- **Audit Logging** - Comprehensive action tracking

### Key Functionalities:
- 15-day inactivity auto-demotion (with 12-day warning)
- Ghost user detection (no roles)
- Returning user notification system
- Poll-based admin decisions
- Protected admin roles (no auto-demotion)
- Channel permission management for inactive users

## 🛠️ Setup Instructions

### 1. Prerequisites
- Python 3.8+
- Discord Bot Token with required permissions
- Discord Server with proper role hierarchy

### 2. Installation
```bash
# Clone or create project structure
mkdir discord-bot
cd discord-bot

# Install dependencies
pip install -r requirements.txt

# Create .env file
echo "DISCORD_BOT_TOKEN=your_bot_token_here" > .env

# Update config.py with your server IDs
# Edit: CHANNEL_IDS, ROLE_IDS, etc.
