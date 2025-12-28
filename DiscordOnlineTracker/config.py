# config.py - FINAL VERSION FOR RENDER
import os
from dotenv import load_dotenv

# Load environment variables
# Try to load from .env file (for local development)
# But on Render, we use environment variables directly
if os.path.exists('.env'):
    load_dotenv()
    print("📁 Loaded .env file for local development")

class Config:
    # Bot Token - FROM RENDER ENVIRONMENT VARIABLE
    BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
    
    # Channel IDs - VERIFY THESE ARE CORRECT
    CLEANUP_CHANNEL_ID = 1454802873300025396
    ADMIN_CHANNEL_ID = 1437586858417852438
    MAIN_CHANNEL_ID = 1369091668724154419
    CALL_CHANNEL_ID = 1437575744824934531
    
    # Role IDs - VERIFY THESE ARE CORRECT
    IMPERIUS_ROLE_ID = 1437570031822176408
    OG_IMPERIUS_ROLE_ID = 1437572916005834793
    INACTIVE_ROLE_ID = 1454803208995340328
    
    # Protected admin roles
    PROTECTED_ROLE_IDS = [
        1437572916005834793,  # OG-Impèrius🐦‍🔥
        1389835747040694332,  # Admin role 2
        1437578521374363769   # Admin role 3
    ]
    
    # Inactivity settings
    INACTIVITY_WARNING_DAYS = 12
    INACTIVITY_DEMOTION_DAYS = 15
    CHECK_INTERVAL_HOURS = 24
    CHECK_TIME_HOUR = 2
    
    # Poll settings
    POLL_DURATION_HOURS = 24
    URGENT_POLL_HOURS = 2
    
    # Database settings - FOR RENDER
    if os.getenv('RENDER'):
        # Running on Render with persistent disk
        DATABASE_PATH = "/var/data/bot_database.db"
        # Create directory if it doesn't exist
        os.makedirs("/var/data", exist_ok=True)
        print("💾 Using Render persistent disk for database")
    else:
        # Local development
        DATABASE_PATH = "data/bot_database.db"
        os.makedirs("data", exist_ok=True)
        print("💻 Using local data directory for database")
    
    # Logging
    LOG_LEVEL = "INFO"
    
    @classmethod
    def validate(cls):
        """Validate configuration - MODIFIED FOR RENDER"""
        if not cls.BOT_TOKEN:
            # On Render, check environment variable directly
            token = os.getenv('DISCORD_BOT_TOKEN')
            if token:
                cls.BOT_TOKEN = token
                print("✅ Found token in environment variables")
            else:
                print("❌ WARNING: DISCORD_BOT_TOKEN not found")
                print("   On Render: Add DISCORD_BOT_TOKEN as environment variable")
                print("   Locally: Create .env file with DISCORD_BOT_TOKEN=your_token")
                # Don't exit - let the bot try to start anyway
        
        # Check essential IDs (but don't fail if missing)
        essential_ids = {
            'CLEANUP_CHANNEL_ID': cls.CLEANUP_CHANNEL_ID,
            'ADMIN_CHANNEL_ID': cls.ADMIN_CHANNEL_ID,
            'MAIN_CHANNEL_ID': cls.MAIN_CHANNEL_ID,
            'CALL_CHANNEL_ID': cls.CALL_CHANNEL_ID,
            'IMPERIUS_ROLE_ID': cls.IMPERIUS_ROLE_ID,
            'INACTIVE_ROLE_ID': cls.INACTIVE_ROLE_ID,
        }
        
        warnings = []
        for name, value in essential_ids.items():
            if not value:
                warnings.append(f"⚠️ {name} is not set in config.py")
            elif value == 0:
                warnings.append(f"⚠️ {name} is 0, make sure this is correct")
        
        if warnings:
            print("\n".join(warnings))
        else:
            print("✅ Configuration validated")
        
        return True

# Validate on import (but don't crash)
try:
    Config.validate()
except Exception as e:
    print(f"⚠️ Config validation warning: {e}")
