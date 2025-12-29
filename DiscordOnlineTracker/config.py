"""
config.py - Configuration file for easy updates
"""

# Channel IDs
CHANNELS = {
    "RECRUIT_CONFIRM": 1437568595977834590,
    "ADMIN": 1455138098437689387,
    "REVIEW": 1454802873300025396,
    "TRYOUT_RESULT": 1455205385463009310,
    "ATTENDANCE": 1437768842871832597,
    "INACTIVE_ACCESS": 1369091668724154419,
    "LOGS": None,  # Optional: Add log channel ID if desired
    "ERRORS": None,  # Optional: Add error channel ID if desired
}

# Role IDs
ROLES = {
    "IMPERIUS": 1437570031822176408,          # Impèrius🔥
    "OG": 1437572916005834793,               # OG-Impèrius🐦‍🔥
    "CLAN_MASTER": 1389835747040694332,      # Cᥣᥲᥒ Mᥲstᥱr🌟
    "QUEEN": 1437578521374363769,            # Queen❤️‍🔥
    "CUTE": 1438420490455613540,             # cute ✨
    "INACTIVE": 1454803208995340328,         # Inactive role
}

# Voting Roles (who can vote)
VOTING_ROLES = [
    ROLES["CLAN_MASTER"],
    ROLES["QUEEN"],
    ROLES["CUTE"],
    ROLES["OG"],
]

# Voice Channel ID for inactive members
INACTIVE_VOICE_CHANNEL = 1437575744824934531

# Bot Settings
INTERVIEW_TIMEOUT = 300  # 5 minutes in seconds
GHOST_CHECK_HOURS = 24   # Check ghost users every 24 hours
INACTIVE_CHECK_DAYS = 7  # Check inactive members every 7 days
ONLINE_COOLDOWN = 1800   # 30 minutes in seconds
