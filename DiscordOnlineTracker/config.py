# config.py - Centralized configuration
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Bot Token (from .env file)
    BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
    
    # Channel IDs
    CLEANUP_CHANNEL_ID = 1454802873300025396
    ADMIN_CHANNEL_ID = 1437586858417852438
    MAIN_CHANNEL_ID = 1369091668724154419
    CALL_CHANNEL_ID = 1437575744824934531
    
    # Role IDs
    IMPERIUS_ROLE_ID = 1437570031822176408        # Regular member role
    OG_IMPERIUS_ROLE_ID = 1437572916005834793     # OG/Admin role (protected)
    INACTIVE_ROLE_ID = 1454803208995340328        # Inactive role
    
    # Protected admin roles (won't be auto-demoted)
    PROTECTED_ROLE_IDS = [
        1437572916005834793,  # OG-Impèrius🐦‍🔥
        1389835747040694332,  # Admin role 2
        1437578521374363769   # Admin role 3
    ]
    
    # Inactivity settings
    INACTIVITY_WARNING_DAYS = 12   # Warning at 12 days
    INACTIVITY_DEMOTION_DAYS = 15  # Demotion at 15 days
    CHECK_INTERVAL_HOURS = 24      # Daily checks at 2:00 AM
    CHECK_TIME_HOUR = 2            # 2 AM
    
    # Poll settings
    POLL_DURATION_HOURS = 24       # Regular poll duration
    URGENT_POLL_HOURS = 2          # Urgent poll duration
    
    # Database settings
    DATABASE_PATH = "data/bot_database.db"
    BACKUP_PATH = "data/backups/"
    
    # Logging
    LOG_LEVEL = "INFO"
    LOG_FILE = "data/bot.log"
    
    # Safety settings
    MAX_RETRIES = 3
    RETRY_DELAY = 5  # seconds
    
    @classmethod
    def validate(cls):
        """Validate configuration"""
        if not cls.BOT_TOKEN:
            raise ValueError("BOT_TOKEN not set in .env file")
        
        required_ids = [
            cls.CLEANUP_CHANNEL_ID, cls.ADMIN_CHANNEL_ID,
            cls.MAIN_CHANNEL_ID, cls.CALL_CHANNEL_ID,
            cls.IMPERIUS_ROLE_ID, cls.OG_IMPERIUS_ROLE_ID,
            cls.INACTIVE_ROLE_ID
        ]
        
        for id_value in required_ids:
            if not id_value:
                raise ValueError(f"Missing required ID in config: {id_value}")
        
        print("✅ Configuration validated successfully")
        return True

# Validate on import
Config.validate()
