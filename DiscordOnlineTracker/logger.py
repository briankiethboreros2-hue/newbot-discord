# utils/logger.py - Advanced logging system
import logging
import colorlog
import sys
from datetime import datetime
import os

class BotLogger:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._setup_logger()
        return cls._instance
    
    def _setup_logger(self):
        # Create logs directory if it doesn't exist
        os.makedirs("data", exist_ok=True)
        
        # Create formatters
        console_formatter = colorlog.ColoredFormatter(
            '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            }
        )
        
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Configure root logger
        self.logger = logging.getLogger('DiscordBot')
        self.logger.setLevel(logging.DEBUG)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(console_formatter)
        console_handler.setLevel(logging.INFO)
        
        # File handler
        file_handler = logging.FileHandler('data/bot.log', encoding='utf-8')
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(logging.DEBUG)
        
        # Add handlers
        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)
    
    def get_logger(self, module_name=""):
        """Get logger for specific module"""
        if module_name:
            return self.logger.getChild(module_name)
        return self.logger
    
    def log_command(self, ctx, command_name):
        """Log command usage"""
        self.logger.info(f"Command '{command_name}' used by {ctx.author} in {ctx.channel}")
    
    def log_error(self, error, context=""):
        """Log errors with context"""
        self.logger.error(f"{context}: {error}", exc_info=True)
        
        # Also log to error file
        error_logger = logging.getLogger('DiscordBot.Errors')
        error_handler = logging.FileHandler('data/errors.log', encoding='utf-8')
        error_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
        error_logger.addHandler(error_handler)
        error_logger.error(f"{context}: {error}", exc_info=True)

# Singleton instance
logger = BotLogger().get_logger()
