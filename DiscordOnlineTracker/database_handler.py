# modules/database_handler.py - SQLite database operations
import aiosqlite
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import asyncio
from utils.logger import logger
from utils.error_handler import with_error_handling
from config import Config

class DatabaseHandler:
    def __init__(self):
        self.db_path = Config.DATABASE_PATH
        self.conn = None
        self._lock = asyncio.Lock()
    
    async def initialize(self):
        """Initialize database connection and create tables"""
        try:
            # Create data directory if it doesn't exist
            import os
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            
            self.conn = await aiosqlite.connect(self.db_path)
            await self._create_tables()
            await self._create_indexes()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise
    
    async def _create_tables(self):
        """Create database tables"""
        tables = [
            # User activity tracking
            '''
            CREATE TABLE IF NOT EXISTS user_activity (
                user_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_message TIMESTAMP,
                last_voice TIMESTAMP,
                days_inactive INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                current_role_id INTEGER,
                last_warning TIMESTAMP,
                demotion_date TIMESTAMP,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''',
            
            # Vote tracking
            '''
            CREATE TABLE IF NOT EXISTS vote_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_user_id INTEGER NOT NULL,
                target_username TEXT,
                voter_id INTEGER NOT NULL,
                voter_username TEXT,
                action TEXT NOT NULL,
                poll_id INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                result TEXT,
                FOREIGN KEY (target_user_id) REFERENCES user_activity(user_id)
            )
            ''',
            
            # Poll tracking
            '''
            CREATE TABLE IF NOT EXISTS polls (
                poll_id INTEGER PRIMARY KEY,
                message_id INTEGER,
                channel_id INTEGER NOT NULL,
                creator_id INTEGER,
                question TEXT NOT NULL,
                poll_type TEXT DEFAULT 'cleanup',
                status TEXT DEFAULT 'open',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                result TEXT
            )
            ''',
            
            # Cleanup actions
            '''
            CREATE TABLE IF NOT EXISTS cleanup_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                action_type TEXT NOT NULL,
                reason TEXT,
                performed_by INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES user_activity(user_id)
            )
            ''',
            
            # Settings
            '''
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            '''
        ]
        
        async with self._lock:
            for table_sql in tables:
                await self.conn.execute(table_sql)
            await self.conn.commit()
    
    async def _create_indexes(self):
        """Create database indexes for performance"""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_user_status ON user_activity(status)",
            "CREATE INDEX IF NOT EXISTS idx_user_inactive ON user_activity(days_inactive)",
            "CREATE INDEX IF NOT EXISTS idx_votes_target ON vote_history(target_user_id)",
            "CREATE INDEX IF NOT EXISTS idx_votes_voter ON vote_history(voter_id)",
            "CREATE INDEX IF NOT EXISTS idx_polls_status ON polls(status)",
            "CREATE INDEX IF NOT EXISTS idx_polls_expiry ON polls(expires_at)",
        ]
        
        async with self._lock:
            for index_sql in indexes:
                await self.conn.execute(index_sql)
            await self.conn.commit()
    
    @with_error_handling
    async def update_user_activity(self, user_id: int, username: str, 
                                   activity_type: str = "message") -> bool:
        """Update user's last activity timestamp"""
        async with self._lock:
            # Get current timestamp
            now = datetime.utcnow().isoformat()
            
            # Update based on activity type
            if activity_type == "message":
                await self.conn.execute('''
                    INSERT OR REPLACE INTO user_activity 
                    (user_id, username, last_active, last_message, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, username, now, now, now))
            elif activity_type == "voice":
                await self.conn.execute('''
                    INSERT OR REPLACE INTO user_activity 
                    (user_id, username, last_active, last_voice, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, username, now, now, now))
            else:
                await self.conn.execute('''
                    INSERT OR REPLACE INTO user_activity 
                    (user_id, username, last_active, updated_at)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, username, now, now))
            
            await self.conn.commit()
            return True
    
    @with_error_handling
    async def calculate_inactivity(self) -> List[Dict[str, Any]]:
        """Calculate inactivity for all users and return inactive users"""
        async with self._lock:
            # First, update days_inactive for all users
            await self.conn.execute('''
                UPDATE user_activity 
                SET days_inactive = CAST(
                    (julianday('now') - julianday(last_active)) AS INTEGER
                ),
                updated_at = CURRENT_TIMESTAMP
                WHERE status != 'inactive'
            ''')
            
            # Get users who are now inactive (15+ days)
            cursor = await self.conn.execute('''
                SELECT user_id, username, days_inactive, last_active
                FROM user_activity 
                WHERE days_inactive >= ? 
                AND status = 'active'
                AND current_role_id = ?
            ''', (Config.INACTIVITY_DEMOTION_DAYS, Config.IMPERIUS_ROLE_ID))
            
            inactive_users = await cursor.fetchall()
            await self.conn.commit()
            
            return [
                {
                    'user_id': row[0],
                    'username': row[1],
                    'days_inactive': row[2],
                    'last_active': row[3]
                }
                for row in inactive_users
            ]
    
    @with_error_handling
    async def update_user_status(self, user_id: int, status: str, 
                                 notes: str = "", role_id: Optional[int] = None) -> bool:
        """Update user status and optionally role"""
        async with self._lock:
            updates = []
            params = []
            
            updates.append("status = ?")
            params.append(status)
            
            if notes:
                updates.append("notes = ?")
                params.append(notes)
            
            if role_id:
                updates.append("current_role_id = ?")
                params.append(role_id)
            
            if status == 'inactive':
                updates.append("demotion_date = CURRENT_TIMESTAMP")
            elif status == 'active' and role_id == Config.IMPERIUS_ROLE_ID:
                updates.append("demotion_date = NULL")
            
            updates.append("updated_at = CURRENT_TIMESTAMP")
            
            params.append(user_id)
            
            query = f'''
                UPDATE user_activity 
                SET {', '.join(updates)}
                WHERE user_id = ?
            '''
            
            await self.conn.execute(query, params)
            await self.conn.commit()
            
            # Log the status change
            await self.log_cleanup_action(
                user_id=user_id,
                action_type=f"status_change_{status}",
                reason=notes
            )
            
            return True
    
    @with_error_handling
    async def log_vote(self, target_user_id: int, target_username: str,
                       voter_id: int, voter_username: str, 
                       action: str, poll_id: Optional[int] = None,
                       result: str = "pending") -> int:
        """Log a vote action"""
        async with self._lock:
            cursor = await self.conn.execute('''
                INSERT INTO vote_history 
                (target_user_id, target_username, voter_id, voter_username, 
                 action, poll_id, result)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (target_user_id, target_username, voter_id, voter_username,
                  action, poll_id, result))
            
            await self.conn.commit()
            return cursor.lastrowid
    
    @with_error_handling
    async def log_cleanup_action(self, user_id: int, action_type: str,
                                 reason: str = "", performed_by: Optional[int] = None):
        """Log a cleanup action"""
        async with self._lock:
            await self.conn.execute('''
                INSERT INTO cleanup_actions 
                (user_id, action_type, reason, performed_by)
                VALUES (?, ?, ?, ?)
            ''', (user_id, action_type, reason, performed_by))
            
            await self.conn.commit()
    
    @with_error_handling
    async def get_user_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user information"""
        async with self._lock:
            cursor = await self.conn.execute('''
                SELECT user_id, username, last_active, days_inactive, 
                       status, current_role_id, demotion_date, notes
                FROM user_activity 
                WHERE user_id = ?
            ''', (user_id,))
            
            row = await cursor.fetchone()
            
            if row:
                return {
                    'user_id': row[0],
                    'username': row[1],
                    'last_active': row[2],
                    'days_inactive': row[3],
                    'status': row[4],
                    'current_role_id': row[5],
                    'demotion_date': row[6],
                    'notes': row[7]
                }
            return None
    
    @with_error_handling
    async def get_ghost_users(self, guild) -> List[Dict[str, Any]]:
        """Get users with no roles (ghost users)"""
        ghost_users = []
        
        for member in guild.members:
            if len(member.roles) == 1:  # Only @everyone role
                user_info = await self.get_user_info(member.id)
                if not user_info:
                    # Add to database if not exists
                    await self.update_user_activity(member.id, member.name)
                    user_info = await self.get_user_info(member.id)
                
                ghost_users.append({
                    'member': member,
                    'info': user_info
                })
        
        return ghost_users
    
    async def close(self):
        """Close database connection"""
        if self.conn:
            await self.conn.close()
            logger.info("Database connection closed")
    
    async def backup(self):
        """Create database backup"""
        import shutil
        import os
        from datetime import datetime
        
        backup_dir = Config.BACKUP_PATH
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(backup_dir, f"backup_{timestamp}.db")
        
        # Close connection for backup
        if self.conn:
            await self.conn.close()
        
        # Copy database file
        shutil.copy2(self.db_path, backup_file)
        
        # Reopen connection
        self.conn = await aiosqlite.connect(self.db_path)
        
        logger.info(f"Database backed up to {backup_file}")
        return backup_file
