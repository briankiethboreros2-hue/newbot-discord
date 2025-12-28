# config.py - UPDATED WITH PERMISSION FIX
import os
from dotenv import load_dotenv

# Load environment variables
if os.path.exists('.env'):
    load_dotenv()

class Config:
    # Bot Token
    BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
    
    # Channel IDs - VERIFY THESE!
    CLEANUP_CHANNEL_ID = 1454802873300025396
    ADMIN_CHANNEL_ID = 1437586858417852438
    MAIN_CHANNEL_ID = 1369091668724154419
    CALL_CHANNEL_ID = 1437575744824934531
    
    # Role IDs - VERIFY THESE!
    IMPERIUS_ROLE_ID = 1437570031822176408
    OG_IMPERIUS_ROLE_ID = 1437572916005834793
    INACTIVE_ROLE_ID = 1454803208995340328
    
    # Protected admin roles
    PROTECTED_ROLE_IDS = [
        1437572916005834793,
        1389835747040694332,
        1437578521374363769
    ]
    
    # Inactivity settings
    INACTIVITY_WARNING_DAYS = 12
    INACTIVITY_DEMOTION_DAYS = 15
    CHECK_INTERVAL_HOURS = 24
    CHECK_TIME_HOUR = 2
    
    # Poll settings
    POLL_DURATION_HOURS = 24
    URGENT_POLL_HOURS = 2
    
    # Database settings - FIXED FOR RENDER
    if os.getenv('RENDER'):
        # On Render, use /opt/render/.render for persistent storage
        # OR use current directory if that fails
        try:
            RENDER_DATA_PATH = "/opt/render/.render"
            os.makedirs(RENDER_DATA_PATH, exist_ok=True)
            DATABASE_PATH = os.path.join(RENDER_DATA_PATH, "bot_database.db")
            print(f"💾 Using Render storage: {DATABASE_PATH}")
        except PermissionError:
            # Fallback to current directory
            DATABASE_PATH = "bot_database.db"
            print("💾 Using current directory for database (fallback)")
    else:
        # Local development
        DATABASE_PATH = "data/bot_database.db"
        os.makedirs("data", exist_ok=True)
        print("💻 Using local data directory")
    
    # Logging
    LOG_LEVEL = "INFO"
    
    @classmethod
    def validate(cls):
        """Validate configuration"""
        if not cls.BOT_TOKEN:
            # Try to get from environment
            token = os.getenv('DISCORD_BOT_TOKEN')
            if token:
                cls.BOT_TOKEN = token
                print("✅ Found token in environment variables")
            else:
                print("⚠️ WARNING: DISCORD_BOT_TOKEN not found")
        
        print(f"✅ Database path: {cls.DATABASE_PATH}")
        return True

# Validate config
try:
    Config.validate()
except Exception as e:
    print(f"⚠️ Config warning: {e}")
