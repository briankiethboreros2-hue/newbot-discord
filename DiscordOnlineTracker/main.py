    @tasks.loop(hours=1)
    async def cleanup_state_task(self):
        """Clean up stale state data hourly"""
        try:
            if hasattr(self.state, 'cleanup_stale_data'):
                # Run cleanup without saving (to avoid deadlock)
                now = datetime.now()
                cleaned = 0
                
                # Clean recent joins older than 5 minutes (simple version)
                if hasattr(self.state.state, 'recent_joins'):
                    user_ids_to_remove = []
                    for user_id_str, join_time_str in self.state.state['recent_joins'].items():
                        try:
                            join_time = datetime.fromisoformat(join_time_str)
                            if (now - join_time).total_seconds() > 300:  # 5 minutes
                                user_ids_to_remove.append(user_id_str)
                                cleaned += 1
                        except:
                            user_ids_to_remove.append(user_id_str)
                    
                    for user_id_str in user_ids_to_remove:
                        del self.state.state['recent_joins'][user_id_str]
                    
                    if cleaned > 0:
                        logger.info(f"🧹 Cleaned {cleaned} stale recent joins")
                
        except Exception as e:
            logger.error(f"❌ Error in cleanup_state_task: {e}")
    
    @cleanup_state_task.before_loop
    async def before_cleanup_state(self):
        await self.wait_until_ready()
