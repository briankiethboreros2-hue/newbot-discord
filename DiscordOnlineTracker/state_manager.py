"""
state_manager.py - Simple state management for bot
"""
import json
import threading
import asyncio
from datetime import datetime, timedelta
import os
import logging

logger = logging.getLogger(__name__)

class StateManager:
    def __init__(self, persistence_file="bot_state.json"):
        self.persistence_file = persistence_file
        self.lock = threading.Lock()
        
        # Initialize all state dictionaries
        self.active_interviews = {}
        self.interview_timeouts = {}
        self.checked_users = set()
        self.last_online = {}
        self.recent_joins = {}
        self.demoted_users = {}
        self.completed_interviews = set()
        self.failed_interviews = set()
        
        # Load existing state
        self.load_state()
        
        # Start auto-save
        self.auto_save_task = None
    
    def start_auto_save(self):
        """Start auto-saving state periodically"""
        async def auto_save():
            while True:
                await asyncio.sleep(300)  # Save every 5 minutes
                self.save_state()
                logger.debug("💾 Auto-saved state")
        
        self.auto_save_task = asyncio.create_task(auto_save())
        logger.info("✅ Started state auto-save")
    
    def stop_auto_save(self):
        """Stop auto-saving"""
        if self.auto_save_task:
            self.auto_save_task.cancel()
        self.save_state()  # Final save
        logger.info("🛑 Stopped state auto-save")
    
    def load_state(self):
        """Load state from JSON file"""
        try:
            if os.path.exists(self.persistence_file):
                with open(self.persistence_file, 'r') as f:
                    data = json.load(f)
                
                # Load all state data
                self.active_interviews = {int(k): v for k, v in data.get('active_interviews', {}).items()}
                self.interview_timeouts = {int(k): v for k, v in data.get('interview_timeouts', {}).items()}
                self.checked_users = set(data.get('checked_users', []))
                self.completed_interviews = set(data.get('completed_interviews', []))
                self.failed_interviews = set(data.get('failed_interviews', []))
                
                # Load timestamp dictionaries
                self.last_online = self._load_timestamps(data.get('last_online', {}))
                self.recent_joins = self._load_timestamps(data.get('recent_joins', {}))
                self.demoted_users = self._load_timestamps(data.get('demoted_users', {}))
                
                logger.info(f"✅ Loaded state from {self.persistence_file}")
                
        except Exception as e:
            logger.error(f"❌ Error loading state: {e}")
    
    def _load_timestamps(self, data_dict):
        """Convert ISO timestamp strings back to datetime objects"""
        result = {}
        for key, value in data_dict.items():
            try:
                result[int(key)] = datetime.fromisoformat(value)
            except:
                result[int(key)] = value
        return result
    
    def _save_timestamps(self, data_dict):
        """Convert datetime objects to ISO timestamp strings"""
        result = {}
        for key, value in data_dict.items():
            if isinstance(value, datetime):
                result[str(key)] = value.isoformat()
            else:
                result[str(key)] = value
        return result
    
    def save_state(self):
        """Save state to JSON file"""
        try:
            with self.lock:
                data = {
                    'active_interviews': self.active_interviews,
                    'interview_timeouts': self.interview_timeouts,
                    'checked_users': list(self.checked_users),
                    'completed_interviews': list(self.completed_interviews),
                    'failed_interviews': list(self.failed_interviews),
                    'last_online': self._save_timestamps(self.last_online),
                    'recent_joins': self._save_timestamps(self.recent_joins),
                    'demoted_users': self._save_timestamps(self.demoted_users),
                    'saved_at': datetime.now().isoformat()
                }
                
                with open(self.persistence_file, 'w') as f:
                    json.dump(data, f, indent=2, default=str)
                
                logger.debug(f"💾 State saved to {self.persistence_file}")
                
        except Exception as e:
            logger.error(f"❌ Error saving state: {e}")
    
    def cleanup_stale_data(self):
        """Clean up old data to prevent memory leaks"""
        with self.lock:
            now = datetime.now()
            cleaned_count = 0
            
            # Clean active_interviews older than 1 hour
            stale_keys = []
            for key, interview in self.active_interviews.items():
                if 'start_time' in interview:
                    start_time = interview['start_time']
                    if isinstance(start_time, str):
                        try:
                            start_time = datetime.fromisoformat(start_time)
                        except:
                            stale_keys.append(key)
                            continue
                    
                    if (now - start_time) > timedelta(hours=1):
                        stale_keys.append(key)
            
            for key in stale_keys:
                del self.active_interviews[key]
                cleaned_count += 1
            
            # Clean recent_joins older than 2 hours
            stale_joins = []
            for user_id, join_time in self.recent_joins.items():
                if (now - join_time) > timedelta(hours=2):
                    stale_joins.append(user_id)
            
            for user_id in stale_joins:
                del self.recent_joins[user_id]
                cleaned_count += 1
            
            # Clean last_online older than 7 days
            stale_online = []
            for user_id, last_time in self.last_online.items():
                if (now - last_time) > timedelta(days=7):
                    stale_online.append(user_id)
            
            for user_id in stale_online:
                del self.last_online[user_id]
                cleaned_count += 1
            
            if cleaned_count > 0:
                logger.info(f"🧹 Cleaned {cleaned_count} stale entries")
                self.save_state()
    
    # Thread-safe getters and setters
    def get_active_interview(self, user_id):
        with self.lock:
            return self.active_interviews.get(user_id)
    
    def set_active_interview(self, user_id, data):
        with self.lock:
            self.active_interviews[user_id] = data
    
    def remove_active_interview(self, user_id):
        with self.lock:
            if user_id in self.active_interviews:
                del self.active_interviews[user_id]
    
    def add_checked_user(self, user_id):
        with self.lock:
            self.checked_users.add(user_id)
    
    def is_user_checked(self, user_id):
        with self.lock:
            return user_id in self.checked_users
    
    def get_recent_join(self, user_id):
        with self.lock:
            return self.recent_joins.get(user_id)
    
    def add_recent_join(self, user_id, join_time):
        with self.lock:
            self.recent_joins[user_id] = join_time
    
    def remove_recent_join(self, user_id):
        with self.lock:
            if user_id in self.recent_joins:
                del self.recent_joins[user_id]
    
    def add_completed_interview(self, user_id):
        with self.lock:
            self.completed_interviews.add(user_id)
    
    def is_interview_completed(self, user_id):
        with self.lock:
            return user_id in self.completed_interviews
    
    def add_failed_interview(self, user_id):
        with self.lock:
            self.failed_interviews.add(user_id)
    
    def is_interview_failed(self, user_id):
        with self.lock:
            return user_id in self.failed_interviews
