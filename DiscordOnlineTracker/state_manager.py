"""
state_manager.py - Thread-safe state management with file persistence
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
        
        # State dictionaries
        self.active_interviews = {}
        self.interview_timeouts = {}
        self.completed_interviews = set()
        self.checked_users = set()
        self.demoted_users = {}
        self.last_online = {}
        self.recent_joins = {}
        
        # Load persisted state
        self.load_state()
        
        # Start auto-save task
        self.auto_save_task = None
    
    def start_auto_save(self):
        """Start auto-save task"""
        async def auto_save():
            while True:
                await asyncio.sleep(300)  # Save every 5 minutes
                self.save_state()
        
        self.auto_save_task = asyncio.create_task(auto_save())
    
    def stop_auto_save(self):
        """Stop auto-save task"""
        if self.auto_save_task:
            self.auto_save_task.cancel()
    
    def load_state(self):
        """Load state from file"""
        try:
            if os.path.exists(self.persistence_file):
                with open(self.persistence_file, 'r') as f:
                    data = json.load(f)
                    
                # Convert string keys back to integers
                self.active_interviews = {int(k): v for k, v in data.get('active_interviews', {}).items()}
                self.interview_timeouts = {int(k): v for k, v in data.get('interview_timeouts', {}).items()}
                self.completed_interviews = set(data.get('completed_interviews', []))
                self.checked_users = set(data.get('checked_users', []))
                
                # Convert timestamps back to datetime
                self.demoted_users = {int(k): datetime.fromisoformat(v) 
                                    for k, v in data.get('demoted_users', {}).items()}
                self.last_online = {int(k): datetime.fromisoformat(v) 
                                  for k, v in data.get('last_online', {}).items()}
                self.recent_joins = {int(k): datetime.fromisoformat(v) 
                                   for k, v in data.get('recent_joins', {}).items()}
                
                logger.info(f"✅ Loaded state from {self.persistence_file}")
                
        except Exception as e:
            logger.error(f"❌ Error loading state: {e}")
    
    def save_state(self):
        """Save state to file"""
        try:
            with self.lock:
                # Convert datetime to ISO format strings
                data = {
                    'active_interviews': self.active_interviews,
                    'interview_timeouts': self.interview_timeouts,
                    'completed_interviews': list(self.completed_interviews),
                    'checked_users': list(self.checked_users),
                    'demoted_users': {k: v.isoformat() for k, v in self.demoted_users.items()},
                    'last_online': {k: v.isoformat() for k, v in self.last_online.items()},
                    'recent_joins': {k: v.isoformat() for k, v in self.recent_joins.items()},
                    'saved_at': datetime.now().isoformat()
                }
                
                with open(self.persistence_file, 'w') as f:
                    json.dump(data, f, indent=2)
                
                logger.debug(f"💾 State saved to {self.persistence_file}")
                
        except Exception as e:
            logger.error(f"❌ Error saving state: {e}")
    
    def cleanup_stale_data(self):
        """Clean up stale data to prevent memory leaks"""
        with self.lock:
            now = datetime.now()
            
            # Clean active_interviews older than 10 minutes
            stale_interviews = []
            for user_id, interview in self.active_interviews.items():
                if 'start_time' in interview:
                    start_time = datetime.fromisoformat(interview['start_time']) if isinstance(interview['start_time'], str) else interview['start_time']
                    if (now - start_time).total_seconds() > 600:  # 10 minutes
                        stale_interviews.append(user_id)
            
            for user_id in stale_interviews:
                del self.active_interviews[user_id]
            
            # Clean interview_timeouts older than 1 hour
            stale_timeouts = []
            for user_id, timeout_data in self.interview_timeouts.items():
                if 'timestamp' in timeout_data:
                    timestamp = datetime.fromisoformat(timeout_data['timestamp']) if isinstance(timeout_data['timestamp'], str) else timeout_data['timestamp']
                    if (now - timestamp).total_seconds() > 3600:  # 1 hour
                        stale_timeouts.append(user_id)
            
            for user_id in stale_timeouts:
                del self.interview_timeouts[user_id]
            
            # Clean last_online older than 7 days
            stale_online = []
            for user_id, last_time in self.last_online.items():
                if (now - last_time).days > 7:
                    stale_online.append(user_id)
            
            for user_id in stale_online:
                del self.last_online[user_id]
            
            # Clean recent_joins older than 1 hour
            stale_joins = []
            for user_id, join_time in self.recent_joins.items():
                if (now - join_time).total_seconds() > 3600:
                    stale_joins.append(user_id)
            
            for user_id in stale_joins:
                del self.recent_joins[user_id]
            
            # Clean demoted_users older than 30 days
            stale_demoted = []
            for user_id, demotion_time in self.demoted_users.items():
                if (now - demotion_time).days > 30:
                    stale_demoted.append(user_id)
            
            for user_id in stale_demoted:
                del self.demoted_users[user_id]
            
            # Clean checked_users if too large
            if len(self.checked_users) > 1000:
                self.checked_users.clear()
            
            logger.info(f"🧹 Cleaned stale data: {len(stale_interviews)} interviews, {len(stale_timeouts)} timeouts")
    
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
    
    def add_recent_join(self, user_id, join_time):
        with self.lock:
            self.recent_joins[user_id] = join_time
    
    def get_recent_join(self, user_id):
        with self.lock:
            return self.recent_joins.get(user_id)
    
    def remove_recent_join(self, user_id):
        with self.lock:
            if user_id in self.recent_joins:
                del self.recent_joins[user_id]
