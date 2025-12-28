# utils/error_handler.py - Comprehensive error handling
import traceback
import asyncio
from discord import HTTPException, Forbidden
from utils.logger import logger

class ErrorHandler:
    def __init__(self, bot):
        self.bot = bot
        self.error_counts = {}
        self.MAX_ERRORS_BEFORE_ALERT = 10
    
    async def handle_error(self, error, context="", notify_admins=True):
        """Handle errors gracefully"""
        error_type = type(error).__name__
        
        # Track error frequency
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
        
        # Log error
        logger.log_error(error, context)
        
        # Check if we should alert admins
        if (self.error_counts[error_type] >= self.MAX_ERRORS_BEFORE_ALERT and 
            notify_admins):
            await self.alert_admins(error_type, context)
        
        # Handle specific error types
        if isinstance(error, HTTPException):
            return await self.handle_http_error(error, context)
        elif isinstance(error, Forbidden):
            return await self.handle_permission_error(error, context)
        elif isinstance(error, asyncio.TimeoutError):
            return await self.handle_timeout_error(error, context)
        
        # Generic error response
        return f"❌ An error occurred: {error_type}"
    
    async def handle_http_error(self, error, context):
        """Handle Discord HTTP errors"""
        logger.warning(f"HTTP Error ({error.status}): {error.text}")
        
        if error.status == 429:  # Rate limited
            retry_after = error.response.headers.get('Retry-After', 5)
            logger.info(f"Rate limited, retrying after {retry_after} seconds")
            await asyncio.sleep(float(retry_after))
            return "🔄 Rate limited, please try again in a moment"
        
        return "⚠️ Discord API error, please try again later"
    
    async def handle_permission_error(self, error, context):
        """Handle permission errors"""
        logger.warning(f"Permission error: {error}")
        
        # Try to fix permissions if possible
        missing_perms = []
        if "Manage Roles" in str(error):
            missing_perms.append("Manage Roles")
        
        if missing_perms:
            return f"🔒 Bot needs permissions: {', '.join(missing_perms)}"
        
        return "🔒 Permission denied"
    
    async def handle_timeout_error(self, error, context):
        """Handle timeout errors"""
        logger.warning(f"Timeout in {context}")
        return "⏰ Operation timed out, please try again"
    
    async def alert_admins(self, error_type, context):
        """Alert admins about frequent errors"""
        try:
            admin_channel = self.bot.get_channel(Config.ADMIN_CHANNEL_ID)
            if admin_channel:
                await admin_channel.send(
                    f"🚨 **BOT ERROR ALERT**\n"
                    f"Error type: `{error_type}`\n"
                    f"Context: {context}\n"
                    f"Count: {self.error_counts[error_type]}\n"
                    f"Please check bot logs."
                )
        except Exception as e:
            logger.error(f"Failed to alert admins: {e}")
    
    def reset_error_count(self, error_type=None):
        """Reset error counters"""
        if error_type:
            self.error_counts[error_type] = 0
        else:
            self.error_counts.clear()

# Decorator for error handling
def with_error_handling(func):
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            handler = ErrorHandler(args[0].bot if hasattr(args[0], 'bot') else None)
            return await handler.handle_error(e, f"Function: {func.__name__}")
    return wrapper
