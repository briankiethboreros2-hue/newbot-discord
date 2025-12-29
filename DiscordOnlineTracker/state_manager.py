"""
state_manager.py - Simple state management
"""
import json
import threading
import asyncio
from datetime import datetime
import os
import logging

logger = logging.getLogger(__name__)

class StateManager:
    def __init__(self, persistence_file="bot_state.json"):
        self.persistence_file = persistence_file
        self.lock = threading.Lock()
        
        # Initialize state dictionaries
        self.active_interviews = {}
        self.interview_timeouts = {}
        self.checked_users = set()
        self.last_online = {}
        self.recent_joins = {}
        self.demoted_users = {}
        
        # Load persisted state if exists
        self.load_state()
    
    def load_state(self):
        """Load state from file"""
        try:
            if os.path.exists(self.persistence_file):
                with open(self.persistence_file, 'r') as f:
                    data = json.load(f)
                
                self.active_interviews = data.get('active_interviews', {})
                self.interview_timeouts = data.get('interview_timeouts', {})
                self.checked_users = set(data.get('checked_users', []))
                self.last_online = data.get('last_online', {})
                self.recent_joins = data.get('recent_joins', {})
                self.demoted_users = data.get('demoted_users', {})
                
                logger.info("✅ Loaded state from file")
        except Exception as e:
            logger.error(f"❌ Error loading state: {e}")
    
    def save_state(self):
        """Save state to file"""
        try:
            with self.lock:
                data = {
                    'active_interviews': self.active_interviews,
                    'interview_timeouts': self.interview_timeouts,
                    'checked_users': list(self.checked_users),
                    'last_online': self.last_online,
                    'recent_joins': self.recent_joins,
                    'demoted_users': self.demoted_users,
                    'saved_at': datetime.now().isoformat()
                }
                
                with open(self.persistence_file, 'w') as f:
                    json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"❌ Error saving state: {e}")
    
    def cleanup_stale_data(self):
        """Clean up stale data"""
        with self.lock:
            now = datetime.now()
            
            # Clean recent_joins older than 1 hour
            stale_joins = []
            for user_id, join_time_str in self.recent_joins.items():
                try:
                    join_time = datetime.fromisoformat(join_time_str)
                    if (now - join_time).total_seconds() > 3600:
                        stale_joins.append(user_id)
                except:
                    stale_joins.append(user_id)
            
            for user_id in stale_joins:
                del self.recent_joins[user_id]
            
            # Save after cleanup
            self.save_state()
    
    # Helper methods
    def get_recent_join(self, user_id):
        with self.lock:
            join_time_str = self.recent_joins.get(str(user_id))
            if join_time_str:
                try:
                    return datetime.fromisoformat(join_time_str)
                except:
                    return None
            return None
    
    def add_recent_join(self, user_id, join_time):
        with self.lock:
            self.recent_joins[str(user_id)] = join_time.isoformat()
    
    def start_auto_save(self):
        """Start auto-save task (called from main)"""
        async def auto_save():
            while True:
                await asyncio.sleep(300)  # Save every 5 minutes
                self.save_state()
        
        asyncio.create_task(auto_save())
    
    def stop_auto_save(self):
        """Stop auto-save (called on shutdown)"""
        self.save_state()
