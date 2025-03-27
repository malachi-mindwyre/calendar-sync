#!/usr/bin/env python3
import importlib.util
import logging
import sys
import os

# Set up logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("calendar_debug.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Import the CalendarSync class from the script
spec = importlib.util.spec_from_file_location("calendar_sync", "calendar_sync.py")
calendar_sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(calendar_sync)

def main():
    """Debug function to examine calendar contents"""
    # Load calendar config
    import json
    with open('calendar_config.json', 'r') as f:
        calendars = json.load(f)
    
    if not calendars:
        logger.error("No calendars configured!")
        return
    
    # Find the IPSOS calendar
    ipsos_calendar = next((cal for cal in calendars if cal['calendarName'] == 'IPSOS'), None)
    
    if not ipsos_calendar:
        logger.error("IPSOS calendar not found in configuration!")
        return
    
    logger.info(f"Examining IPSOS calendar: {ipsos_calendar['url']}")
    
    # Create a CalendarSync instance
    sync = calendar_sync.CalendarSync(
        ical_url=ipsos_calendar['url'],
        calendar_name=ipsos_calendar['calendarName'],
        days_back=ipsos_calendar.get('daysBack', 30),
        days_forward=ipsos_calendar.get('daysForward', 60),
        sync_interval=ipsos_calendar.get('syncInterval', 5)
    )
    
    # Debug: Look for all recurring events
    logger.info("Looking for all recurring events...")
    sync.debug_examine_calendar()
    
    # Debug: Look for Tuesday events
    logger.info("\nLooking for Tuesday events...")
    sync.debug_examine_calendar(day_of_week="Tuesday")
    
    # Debug: Look for Thursday events
    logger.info("\nLooking for Thursday events...")
    sync.debug_examine_calendar(day_of_week="Thursday")
    
    # Debug: If user provided a search term, use it
    if len(sys.argv) > 1:
        search_term = sys.argv[1]
        logger.info(f"\nLooking for events matching: {search_term}")
        sync.debug_examine_calendar(search_term=search_term)

if __name__ == "__main__":
    main()