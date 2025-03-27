#!/usr/bin/env python3
import importlib.util
import threading
import time
import os
import logging
import sys

# Set up logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("calendar_sync_runner.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Import the CalendarSync class from the script
spec = importlib.util.spec_from_file_location("calendar_sync", "calendar_sync.py")
calendar_sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(calendar_sync)

# Define your calendars here
calendars = [
        {
            "url": "https://outlook.office365.com/owa/calendar/70428bd059d14219bddf1221b4b3d621@ipsos.com/6764ef7293d54ee68e91b63fe5c4876910567899067948008408/calendar.ics",
            "calendarName": "IPSOS",
            "daysBack": 365,
            "daysForward": 365,
            "syncInterval": 5
        },
        {
            "url": "https://ical.titan.email/feed/2973177/LfmH6NurIpULTZxvLvAW6dW7543wAgy3",
            "calendarName": "Titan Mail",
            "daysBack": 365,
            "daysForward": 365,
            "syncInterval": 5
        }
    ]

def sync_calendar(calendar_config):
    """Function to sync a single calendar in a separate thread"""
    logger.info(f"Starting sync for calendar: {calendar_config['calendarName']}")
    """Function to sync a single calendar in a separate thread"""
    logger.info(f"Starting sync for calendar: {calendar_config['calendarName']}")
    try:
        sync = calendar_sync.CalendarSync(
            ical_url=calendar_config['url'],
            calendar_name=calendar_config['calendarName'],
            days_back=calendar_config.get('daysBack', 30),
            days_forward=calendar_config.get('daysForward', 60),
            sync_interval=calendar_config.get('syncInterval', 5)
        )
        sync.run()
    except Exception as e:
        logger.error(f"Error in calendar sync for {calendar_config['calendarName']}: {e}")

def main():
    """Main function to start all calendar syncs"""
    # Check if we have a special command line argument to run a single sync
    if len(sys.argv) > 1 and sys.argv[1] == "--single-sync":
        logger.info("Running a single sync cycle for all calendars...")
        for calendar in calendars:
            try:
                logger.info(f"Starting single sync for calendar: {calendar['calendarName']}")
                sync = calendar_sync.CalendarSync(
                    ical_url=calendar['url'],
                    calendar_name=calendar['calendarName'],
                    days_back=calendar.get('daysBack', 30),
                    days_forward=calendar.get('daysForward', 60),
                    sync_interval=calendar.get('syncInterval', 5)
                )
                # Just do an initial sync and exit
                sync.initial_sync()
                logger.info(f"Completed single sync for calendar: {calendar['calendarName']}")
            except Exception as e:
                logger.error(f"Error in single sync for {calendar['calendarName']}: {e}")
        return
    
    # Normal continuous syncing mode
    threads = []
    for calendar in calendars:
        thread = threading.Thread(target=sync_calendar, args=(calendar,))
        thread.daemon = True
        threads.append(thread)
        thread.start()
        logger.info(f"Started syncing calendar: {calendar['calendarName']}")
    
    # Keep the main thread running to monitor the calendar sync threads
    try:
        while True:
            time.sleep(60)  # Check every minute
            # Check if all threads are still alive
            for i, (thread, calendar) in enumerate(zip(threads, calendars)):
                if not thread.is_alive():
                    logger.warning(f"Calendar sync for {calendar['calendarName']} stopped. Restarting...")
                    # Restart the thread
                    new_thread = threading.Thread(target=sync_calendar, args=(calendar,))
                    new_thread.daemon = True
                    new_thread.start()
                    threads[i] = new_thread
    except KeyboardInterrupt:
        logger.info("Stopping calendar syncs...")

if __name__ == "__main__":
    main()
