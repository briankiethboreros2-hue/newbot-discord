import json
import asyncio
import threading
from datetime import datetime, timedelta
import os
import logging

logger = logging.getLogger(__name__)

class StateManager:
    def __init__(self, data_file="state_data.json"):
        self.data_file = data_file
        self.lock = threading.Lock()
        
        # Initialize state data
        self.state = {
            'active_interviews': {},      # {user_id: interview_data}
            'completed_interviews': [],   # List of completed interview user_ids
            'failed_interviews': [],      # List of failed interview user_ids
            'interview_timeouts': {},     # {user_id: timeout_data}
            'recent_joins': {},           # {user_id: join_time} - IN-MEMORY ONLY
            'online_tracking': {},        # {user_id: tracking_data}
            'cleanup_check_dates': {},    # {user_id: last_check_date}
            'last_save': None
        }
        
        # Load existing state
        self.load_state()
    
    def load_state(self):
        """Load state from file"""
        try:
            if os.path.exists(self.data_file):
                with self.lock:
                    with open(self.data_file, 'r') as f:
                        loaded_state = json.load(f)
                        
                        # Merge loaded state with default structure
                        for key in self.state:
                            if key in loaded_state:
                                # Skip recent_joins - keep in memory only
                                if key != 'recent_joins':
                                    self.state[key] = loaded_state[key]
                        
                        logger.info(f"✅ Loaded state from {self.data_file}")
            else:
                logger.info(f"📁 No state file found, starting fresh")
        except Exception as e:
            logger.error(f"❌ Error loading state: {e}")
            # Keep default state on error
    
    def save_state(self):
        """Save state to file - WITHOUT recent_joins"""
        try:
            # Create a copy of state WITHOUT recent_joins
            state_copy = self.state.copy()
            state_copy.pop('recent_joins', None)  # Remove recent_joins - don't save to file
            state_copy['last_save'] = datetime.now().isoformat()
            
            # Try to acquire lock with timeout to prevent deadlock
            if self.lock.acquire(timeout=1.0):  # 1 second timeout
                try:
                    with open(self.data_file, 'w') as f:
                        json.dump(state_copy, f, indent=2, default=str)
                    logger.debug(f"💾 Saved state to {self.data_file}")
                except Exception as e:
                    logger.error(f"❌ Error saving state: {e}")
                finally:
                    self.lock.release()
            else:
                logger.warning("⏰ Could not acquire lock for save_state - skipping save")
        except Exception as e:
            logger.error(f"❌ Error in save_state: {e}")
    
    def start_auto_save(self):
        """Start automatic saving every 5 minutes"""
        self.auto_save_task.start()
    
    @tasks.loop(minutes=5)
    async def auto_save_task(self):
        """Auto-save state every 5 minutes"""
        self.save_state()
    
    @auto_save_task.before_loop
    async def before_auto_save(self):
        """Wait 10 seconds before starting auto-save"""
        await asyncio.sleep(10)
    
    def cleanup_recent_joins_on_demand(self):
        """Clean recent joins without saving state - call this when checking"""
        try:
            now = datetime.now()
            cleaned = 0
            
            if 'recent_joins' in self.state:
                user_ids_to_remove = []
                for user_id_str, join_time_str in list(self.state['recent_joins'].items()):
                    try:
                        join_time = datetime.fromisoformat(join_time_str)
                        if (now - join_time).total_seconds() > 300:  # 5 minutes
                            user_ids_to_remove.append(user_id_str)
                            cleaned += 1
                    except:
                        user_ids_to_remove.append(user_id_str)
                
                for user_id_str in user_ids_to_remove:
                    del self.state['recent_joins'][user_id_str]
            
            if cleaned > 0:
                logger.debug(f"🧹 Cleaned {cleaned} stale recent joins")
            return cleaned
        except Exception as e:
            logger.error(f"Error in cleanup_recent_joins_on_demand: {e}")
            return 0
    
    # ======== INTERVIEW MANAGEMENT ========
    
    def set_active_interview(self, user_id, interview_data):
        """Set active interview data"""
        self.state['active_interviews'][str(user_id)] = interview_data
    
    def get_active_interview(self, user_id):
        """Get active interview data"""
        return self.state['active_interviews'].get(str(user_id))
    
    def remove_active_interview(self, user_id):
        """Remove active interview"""
        user_id_str = str(user_id)
        if user_id_str in self.state['active_interviews']:
            del self.state['active_interviews'][user_id_str]
            return True
        return False
    
    def add_completed_interview(self, user_id):
        """Add user to completed interviews"""
        if user_id not in self.state['completed_interviews']:
            self.state['completed_interviews'].append(user_id)
    
    def add_failed_interview(self, user_id):
        """Add user to failed interviews"""
        if user_id not in self.state['failed_interviews']:
            self.state['failed_interviews'].append(user_id)
    
    # ======== TIMEOUT MANAGEMENT ========
    
    @property
    def interview_timeouts(self):
        """Get interview timeouts"""
        return self.state['interview_timeouts']
    
    @interview_timeouts.setter
    def interview_timeouts(self, value):
        """Set interview timeouts"""
        self.state['interview_timeouts'] = value
    
    # ======== RECENT JOINS MANAGEMENT ========
    
    def add_recent_join(self, user_id, join_time):
        """Add recent join to prevent rapid rejoins"""
        self.state['recent_joins'][str(user_id)] = join_time.isoformat()
    
    def get_recent_join(self, user_id):
        """Get recent join time"""
        join_time_str = self.state['recent_joins'].get(str(user_id))
        if join_time_str:
            try:
                return datetime.fromisoformat(join_time_str)
            except:
                return None
        return None
    
    # ======== ONLINE TRACKING ========
    
    def set_online_tracking(self, user_id, tracking_data):
        """Set online tracking data"""
        self.state['online_tracking'][str(user_id)] = tracking_data
    
    def get_online_tracking(self, user_id):
        """Get online tracking data"""
        return self.state['online_tracking'].get(str(user_id))
    
    def remove_online_tracking(self, user_id):
        """Remove online tracking"""
        user_id_str = str(user_id)
        if user_id_str in self.state['online_tracking']:
            del self.state['online_tracking'][user_id_str]
            return True
        return False
    
    def get_all_tracked_users(self):
        """Get all tracked users"""
        return list(self.state['online_tracking'].keys())
    
    # ======== CLEANUP CHECK DATES ========
    
    def get_cleanup_check_date(self, user_id):
        """Get cleanup check date for a member"""
        check_date_str = self.state['cleanup_check_dates'].get(str(user_id))
        if check_date_str:
            try:
                return datetime.fromisoformat(check_date_str)
            except:
                return None
        return None
    
    def set_cleanup_check_date(self, user_id, check_date):
        """Set cleanup check date for a member"""
        self.state['cleanup_check_dates'][str(user_id)] = check_date.isoformat()
    
    def remove_cleanup_check_date(self, user_id):
        """Remove cleanup check date"""
        user_id_str = str(user_id)
        if user_id_str in self.state['cleanup_check_dates']:
            del self.state['cleanup_check_dates'][user_id_str]
            return True
        return False
    
    # ======== PROPERTIES FOR COMPATIBILITY ========
    
    @property
    def active_interviews(self):
        """Get active interviews"""
        return self.state['active_interviews']
