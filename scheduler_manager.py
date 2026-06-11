import time
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from download_stock_data import get_wish_list, sync_to_latest
import download_stock_data as dsd

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = BackgroundScheduler()

def sync_all_wish_stocks(api):
    """Syncs all active stocks in the wish list with cooling delays to prevent rate limits."""
    logger.info("Starting background sync for all active wish stocks...")
    stocks = get_wish_list()
    active_stocks = [s for s in stocks if s.get('status') == 'active']
    
    if not active_stocks:
        logger.info("No active stocks in wish list to sync.")
        return

    # Set all active stocks to pending state
    for stock in active_stocks:
        dsd.sync_tracker.set_status(stock['code'], "pending")
        
    for index, stock in enumerate(active_stocks):
        code = stock['code']
        name = stock['name']
        logger.info(f"Syncing stock ({index+1}/{len(active_stocks)}): {code} ({name})")
        
        try:
            sync_to_latest(api, code)
        except Exception as e:
            logger.error(f"Error syncing {code} in background job: {e}")
            
        # Apply 1.5 seconds delay between stocks
        if index < len(active_stocks) - 1:
            logger.info("Applying cooldown delay (1.5s)...")
            time.sleep(1.5)
            
    logger.info("All stocks sync job finished.")

def start_scheduler(api):
    """Starts the APScheduler with daily cron job for Taiwan stock market."""
    if scheduler.running:
        logger.warning("Scheduler is already running.")
        return
        
    logger.info("Starting Background Scheduler for Stock Update...")
    
    try:
        # Schedule daily sync at 13:40 from Monday to Friday (Taiwan market hours end at 13:30)
        scheduler.add_job(
            sync_all_wish_stocks,
            'cron',
            day_of_week='mon-fri',
            hour=13,
            minute=40,
            args=[api],
            id="sync_stock_wish_list_job",
            replace_existing=True
        )
        
        scheduler.start()
        logger.info("Scheduler started successfully. Cron set to Mon-Fri 13:40.")
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")

def stop_scheduler():
    """Stops the scheduler safely."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped.")
