#!/usr/bin/env python3
"""
Simple script to run a single calendar sync.
This is helpful for testing and debugging.
"""
import logging
import sys
import os
import json
from calendar_sync import CalendarSync
from datetime import datetime, timedelta

# Set up logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("simple_sync.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

def check_for_declined_russell_meetings(sync):
    """
    Specifically check for the declined "Malachi & Russell weekly catch-up" meeting
    for March 3, 2025 that was the original issue.
    """
    logger.info("\n============== CHECKING FOR DECLINED RUSSELL MEETINGS ==============")
    
    # First examine the source calendar for the meeting with "Canceled:" prefix
    logger.info("Looking for 'Canceled: Malachi & Russell weekly catch-up' in source calendar...")
    sync.debug_examine_calendar(search_term="Russell")
    
    # Check Google Calendar for the same event to see if it's properly marked as cancelled
    logger.info("\nChecking Google Calendar for Russell meetings and their status...")
    recurring_events = sync.debug_check_recurring_events(search_term="Russell")
    
    # If we found recurring events, check for March 3, 2025 instance specifically
    target_date = None
    try:
        target_date = datetime(2025, 3, 3)  # March 3, 2025
        logger.info(f"\nSpecifically looking for Russell meeting instance on {target_date.strftime('%Y-%m-%d')}")
        
        # Get time range for the API
        time_min = (target_date - timedelta(days=1)).isoformat() + 'Z'
        time_max = (target_date + timedelta(days=1)).isoformat() + 'Z'
        
        # For each recurring event containing Russell in the name
        for event in recurring_events:
            event_id = event.get('id')
            event_summary = event.get('summary', '')
            
            logger.info(f"Checking instances of recurring event: {event_summary}")
            
            try:
                # Get all instances in the date range
                instances = sync.service.events().instances(
                    calendarId=sync.target_calendar_id,
                    eventId=event_id,
                    timeMin=time_min,
                    timeMax=time_max
                ).execute()
                
                instance_count = len(instances.get('items', []))
                logger.info(f"Found {instance_count} instances around {target_date.strftime('%Y-%m-%d')}")
                
                # Check each instance
                for instance in instances.get('items', []):
                    instance_date = instance.get('start', {}).get('dateTime') or instance.get('start', {}).get('date')
                    instance_status = instance.get('status', 'unknown')
                    instance_summary = instance.get('summary', '')
                    
                    logger.info(f"Instance on {instance_date}: Status={instance_status}, Summary={instance_summary}")
                    
                    # Detect if the prefixed cancelled event is properly synced
                    if instance_status == 'cancelled':
                        logger.info(f"SUCCESS: Found cancelled instance of Russell meeting on {instance_date}")
                    elif "Canceled:" in instance_summary or "Cancelled:" in instance_summary:
                        logger.info(f"SUCCESS: Found instance with canceled prefix in summary: {instance_summary}")
                    elif target_date.strftime('%Y-%m-%d') in instance_date:
                        # If this is our target date but not marked cancelled, that's a problem
                        logger.error(f"ISSUE: Meeting on {instance_date} is not marked as cancelled in Google Calendar")
            except Exception as e:
                logger.error(f"Error checking instances: {e}")
    except Exception as e:
        logger.error(f"Error during targeted search: {e}")
    
    logger.info("============== FINISHED CHECKING RUSSELL MEETINGS ==============\n")

def main():
    """Run a simple sync for a single calendar."""
    # Determine which calendar to sync
    calendar_name = "IPSOS"
    if len(sys.argv) > 1:
        calendar_name = sys.argv[1]
    
    logger.info(f"Starting simple sync for calendar: {calendar_name}")
    
    # Load configuration
    try:
        with open('calendar_config.json', 'r') as f:
            calendars = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load calendar config: {e}")
        return
    
    # Find the requested calendar
    target_calendar = next((cal for cal in calendars if cal['calendarName'] == calendar_name), None)
    if not target_calendar:
        logger.error(f"Calendar '{calendar_name}' not found in configuration")
        return
    
    # Run the sync
    try:
        sync = CalendarSync(
            ical_url=target_calendar['url'],
            calendar_name=target_calendar['calendarName'],
            days_back=target_calendar.get('daysBack', 30),
            days_forward=target_calendar.get('daysForward', 60),
            sync_interval=target_calendar.get('syncInterval', 5)
        )
        
        # Check for declined Russell meetings
        if len(sys.argv) > 2 and sys.argv[2] == "--check-declined-russell":
            check_for_declined_russell_meetings(sync)
        
        # Check for Russell meetings specifically
        elif len(sys.argv) > 2 and sys.argv[2] == "--russell":
            logger.info("Checking specifically for Russell meetings...")
            sync.debug_examine_calendar(search_term="Russell")
            # Also look in Google Calendar
            sync.debug_check_recurring_events(search_term="Russell")
        
        # Perform the sync
        logger.info("Running initial sync...")
        sync.initial_sync()
        logger.info(f"Completed sync for {calendar_name}")
        
        # If explicitly requested, check for declined Russell meetings after sync
        if len(sys.argv) > 2 and sys.argv[2] == "--check-after-sync":
            check_for_declined_russell_meetings(sync)
        
    except Exception as e:
        logger.error(f"Error during sync: {e}", exc_info=True)

if __name__ == "__main__":
    main()