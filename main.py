#!/usr/bin/env python3
"""
Calendar Sync Tool - Main entry point
This script provides multiple ways to run the calendar sync tool.
"""
import argparse
import importlib.util
import json
import logging
import os
import sys
import threading
import time

# Get the script directory for relative paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Set up logging with a path relative to the script location
LOG_FILE = os.path.join(SCRIPT_DIR, "calendar_sync.log")
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Import the CalendarSync class
calendar_sync_path = os.path.join(SCRIPT_DIR, "calendar_sync.py")
spec = importlib.util.spec_from_file_location("calendar_sync", calendar_sync_path)
calendar_sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(calendar_sync)

def load_calendars():
    """Load calendar configuration from JSON file"""
    config_file = os.path.join(SCRIPT_DIR, 'calendar_config.json')
    sample_config_file = os.path.join(SCRIPT_DIR, 'calendar_config.json.sample')
    
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
            return config.get('calendars', [])
    except FileNotFoundError:
        logger.error(f"Calendar configuration file '{config_file}' not found. Please create it first.")
        # Create a sample config file to help users get started
        sample_config = {
            "calendars": [
                {
                    "url": "https://example.com/your-calendar.ics",
                    "calendarName": "Example Calendar",
                    "daysBack": 30,
                    "daysForward": 60,
                    "syncInterval": 5
                }
            ]
        }
        try:
            with open(sample_config_file, 'w') as f:
                json.dump(sample_config, f, indent=4)
            logger.info(f"Created sample configuration file '{sample_config_file}'. "
                        f"Rename it to 'calendar_config.json' and update with your calendar details.")
        except Exception as write_error:
            logger.error(f"Failed to create sample config file: {write_error}")
        return []
    except Exception as e:
        logger.error(f"Failed to load calendar config from {config_file}: {e}")
        return []

def sync_calendar(calendar_config):
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

def run_single_sync(calendars, calendar_name=None):
    """Run a single sync cycle for all calendars or a specific one"""
    if calendar_name:
        # Sync only the specified calendar
        target_calendar = next((cal for cal in calendars if cal['calendarName'] == calendar_name), None)
        if not target_calendar:
            logger.error(f"Calendar '{calendar_name}' not found in configuration")
            return
            
        calendars_to_sync = [target_calendar]
    else:
        # Sync all calendars
        calendars_to_sync = calendars
    
    for calendar in calendars_to_sync:
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

def run_continuous_sync(calendars, calendar_name=None):
    """Run continuous sync for all calendars or a specific one"""
    if calendar_name:
        # Sync only the specified calendar
        target_calendar = next((cal for cal in calendars if cal['calendarName'] == calendar_name), None)
        if not target_calendar:
            logger.error(f"Calendar '{calendar_name}' not found in configuration")
            return
            
        calendars_to_sync = [target_calendar]
    else:
        # Sync all calendars
        calendars_to_sync = calendars
    
    threads = []
    # Add a slight delay between starting threads to avoid API rate limits
    for calendar in calendars_to_sync:
        thread = threading.Thread(target=sync_calendar, args=(calendar,))
        thread.daemon = True
        threads.append((thread, calendar))
        thread.start()
        logger.info(f"Started syncing calendar: {calendar['calendarName']}")
        # Add a delay between calendar starts to avoid hitting rate limits
        time.sleep(5)  # 5 seconds between calendar syncs
    
    # Keep the main thread running to monitor the calendar sync threads
    try:
        while True:
            time.sleep(60)  # Check every minute
            # Check if all threads are still alive
            for i, (thread, calendar) in enumerate(threads):
                if not thread.is_alive():
                    logger.warning(f"Calendar sync for {calendar['calendarName']} stopped. Restarting...")
                    # Restart the thread
                    new_thread = threading.Thread(target=sync_calendar, args=(calendar,))
                    new_thread.daemon = True
                    new_thread.start()
                    threads[i] = (new_thread, calendar)
                    # Wait a bit before checking the next thread to avoid rate limits
                    time.sleep(2)
    except KeyboardInterrupt:
        logger.info("Stopping calendar syncs...")

def main():
    """Main function to parse arguments and start the appropriate sync mode"""
    parser = argparse.ArgumentParser(description='Calendar Sync Tool')
    parser.add_argument('--single', action='store_true', help='Run a single sync and exit')
    parser.add_argument('--calendar', type=str, help='Sync only the specified calendar')
    parser.add_argument('--list', action='store_true', help='List available calendars')
    
    args = parser.parse_args()
    
    # Load calendar configuration
    calendars = load_calendars()
    
    if not calendars:
        logger.error("No calendars configured. Please set up your calendars in calendar_config.json")
        return
    
    # List calendars if requested
    if args.list:
        print("Available calendars:")
        for cal in calendars:
            print(f"  - {cal['calendarName']}")
        return
    
    # Run in single sync mode if requested
    if args.single:
        run_single_sync(calendars, args.calendar)
    else:
        # Run in continuous mode
        run_continuous_sync(calendars, args.calendar)

if __name__ == "__main__":
    main()