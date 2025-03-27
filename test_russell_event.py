#!/usr/bin/env python3
"""
Test script specifically for the "Malachi & Russell weekly catch-up" meeting
that was declined for March 3, 2025.

This script allows testing that the cancellation/declined status is properly
detected in the source calendar and correctly synced to Google Calendar.
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
    handlers=[logging.FileHandler("russell_test.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

def test_russell_meeting():
    """
    Run focused tests on the "Malachi & Russell weekly catch-up" meeting.
    """
    # Check for help flag
    if any(arg in ['--help', '-h'] for arg in sys.argv):
        print(f"Usage: python3 {sys.argv[0]} [CALENDAR_NAME] [OPTIONS]")
        print("\nTests the handling of declined recurring meetings, specifically the")
        print("'Malachi & Russell weekly catch-up' meeting that was declined for March 3, 2025.")
        print("\nArguments:")
        print("  CALENDAR_NAME       Name of the calendar to test (default: IPSOS)")
        print("\nOptions:")
        print("  --check-all-dates   Check all instances of Russell meetings")
        print("  --force-decline     Force decline the March 3 instance if it's not properly cancelled")
        print("  -h, --help          Show this help message and exit")
        return
    
    # Load configuration
    try:
        with open('calendar_config.json', 'r') as f:
            calendars = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load calendar config: {e}")
        return
    
    # Default to IPSOS calendar
    calendar_name = "IPSOS"
    if len(sys.argv) > 1 and not sys.argv[1].startswith('--'):
        calendar_name = sys.argv[1]
    
    # Find the requested calendar
    target_calendar = next((cal for cal in calendars if cal['calendarName'] == calendar_name), None)
    if not target_calendar:
        logger.error(f"Calendar '{calendar_name}' not found in configuration")
        print(f"Available calendars: {[cal['calendarName'] for cal in calendars]}")
        return
    
    # Create sync instance
    sync = CalendarSync(
        ical_url=target_calendar['url'],
        calendar_name=target_calendar['calendarName'],
        days_back=target_calendar.get('daysBack', 30),
        days_forward=target_calendar.get('daysForward', 60),
        sync_interval=target_calendar.get('syncInterval', 5)
    )
    
    logger.info("=" * 80)
    logger.info("TESTING RUSSELL MEETING DECLINED STATUS")
    logger.info("=" * 80)
    
    # Step 1: Check source calendar for cancelled Russell meetings
    logger.info("\nSTEP 1: Checking source calendar for cancelled Russell meetings")
    logger.info("-" * 70)
    events_found = sync.debug_examine_calendar(search_term="Russell")
    
    if events_found == 0:
        logger.error("No Russell meetings found in source calendar!")
        return
    
    # Step 2: Check Google Calendar for Russell meetings
    logger.info("\nSTEP 2: Checking Google Calendar for Russell meetings")
    logger.info("-" * 70)
    recurring_events = sync.debug_check_recurring_events(search_term="Russell")
    
    if not recurring_events:
        logger.warning("No Russell meetings found in Google Calendar. Running initial sync first...")
        sync.initial_sync()
        logger.info("Initial sync complete. Checking Google Calendar again...")
        recurring_events = sync.debug_check_recurring_events(search_term="Russell")
        
        if not recurring_events:
            logger.error("Still no Russell meetings found in Google Calendar after sync!")
            return
    
    # Step 3: Look for the March 3, 2025 instance specifically
    logger.info("\nSTEP 3: Checking for March 3, 2025 instance specifically")
    logger.info("-" * 70)
    
    target_date = datetime(2025, 3, 3)  # March 3, 2025
    logger.info(f"Looking for meeting on {target_date.strftime('%Y-%m-%d')}")
    
    # Get time range for the API
    time_min = (target_date - timedelta(days=1)).isoformat() + 'Z'
    time_max = (target_date + timedelta(days=1)).isoformat() + 'Z'
    
    found_march_3_instance = False
    march_3_cancelled = False
    
    # For each recurring event containing Russell in the name
    for event in recurring_events:
        event_id = event.get('id')
        event_summary = event.get('summary', '')
        
        logger.info(f"Checking instances of: {event_summary} (ID: {event_id})")
        
        try:
            # Get all instances in the date range
            instances = sync.service.events().instances(
                calendarId=sync.target_calendar_id,
                eventId=event_id,
                timeMin=time_min,
                timeMax=time_max
            ).execute()
            
            instance_count = len(instances.get('items', []))
            logger.info(f"Found {instance_count} instances around target date")
            
            # Check each instance
            for instance in instances.get('items', []):
                instance_date = instance.get('start', {}).get('dateTime') or instance.get('start', {}).get('date')
                instance_status = instance.get('status', 'unknown')
                instance_summary = instance.get('summary', '')
                instance_id = instance.get('id')
                
                logger.info(f"Instance on {instance_date}:")
                logger.info(f"  ID: {instance_id}")
                logger.info(f"  Status: {instance_status}")
                logger.info(f"  Summary: {instance_summary}")
                
                # Check if this is our target date
                if target_date.strftime('%Y-%m-%d') in instance_date:
                    found_march_3_instance = True
                    logger.info(f"Found March 3, 2025 instance!")
                    
                    # Check if it's properly cancelled
                    if instance_status == 'cancelled':
                        march_3_cancelled = True
                        logger.info(f"SUCCESS: March 3 instance is properly marked as cancelled")
                    elif "Canceled:" in instance_summary or "Cancelled:" in instance_summary:
                        march_3_cancelled = True
                        logger.info(f"SUCCESS: March 3 instance has canceled prefix in summary")
                    else:
                        logger.warning(f"ISSUE: March 3 instance is NOT marked as cancelled")
                        
                        # Try running an incremental sync to update
                        logger.info("Attempting to fix with incremental sync...")
                        sync.incremental_sync()
                        
                        # Check again
                        try:
                            updated_instance = sync.service.events().get(
                                calendarId=sync.target_calendar_id,
                                eventId=instance_id
                            ).execute()
                            
                            updated_status = updated_instance.get('status', 'unknown')
                            updated_summary = updated_instance.get('summary', '')
                            
                            logger.info(f"After sync: Status={updated_status}, Summary={updated_summary}")
                            
                            if updated_status == 'cancelled' or "Canceled:" in updated_summary or "Cancelled:" in updated_summary:
                                march_3_cancelled = True
                                logger.info(f"SUCCESS: Incremental sync fixed the March 3 instance")
                            else:
                                logger.error(f"FAILED: March 3 instance still not marked as cancelled after sync")
                                
                                # As a last resort, try to manually decline this instance
                                if '--force-decline' in sys.argv:
                                    logger.info("Manually declining the instance as a last resort...")
                                    
                                    declined = sync.service.events().patch(
                                        calendarId=sync.target_calendar_id,
                                        eventId=instance_id,
                                        body={'status': 'cancelled'}
                                    ).execute()
                                    
                                    logger.info(f"Manual decline result: Status={declined.get('status')}")
                                    
                                    if declined.get('status') == 'cancelled':
                                        march_3_cancelled = True
                                        logger.info(f"SUCCESS: Manually declined the March 3 instance")
                        except Exception as e:
                            logger.error(f"Error checking updated instance: {e}")
        except Exception as e:
            logger.error(f"Error checking instances: {e}")
    
    # Step 4: Final test results
    logger.info("\nSTEP 4: Test Results Summary")
    logger.info("-" * 70)
    
    if not found_march_3_instance:
        logger.error("FAILED: Could not find March 3, 2025 instance of Russell meeting")
    elif march_3_cancelled:
        logger.info("SUCCESS: March 3, 2025 instance is properly marked as cancelled")
    else:
        logger.error("FAILED: March 3, 2025 instance exists but is not marked as cancelled")
    
    logger.info("\nAdditional debugging options:")
    logger.info("  --force-decline   : Force decline the March 3 instance if found but not cancelled")
    logger.info("  --check-all-dates : Check all instances of the Russell meeting")
    
    # Optional: Check all instances if requested
    if '--check-all-dates' in sys.argv:
        logger.info("\nSTEP 5: Checking all instances of Russell meeting")
        logger.info("-" * 70)
        
        # Wider date range for all instances
        time_min = (datetime.now() - timedelta(days=365)).isoformat() + 'Z'
        time_max = (datetime.now() + timedelta(days=365)).isoformat() + 'Z'
        
        for event in recurring_events:
            event_id = event.get('id')
            event_summary = event.get('summary', '')
            
            if 'Russell' in event_summary:
                logger.info(f"Checking all instances of: {event_summary}")
                
                try:
                    all_instances = sync.service.events().instances(
                        calendarId=sync.target_calendar_id,
                        eventId=event_id,
                        timeMin=time_min,
                        timeMax=time_max
                    ).execute()
                    
                    logger.info(f"Found {len(all_instances.get('items', []))} total instances")
                    
                    # Count cancelled instances
                    cancelled_count = 0
                    cancelled_dates = []
                    
                    for instance in all_instances.get('items', []):
                        instance_date = instance.get('start', {}).get('dateTime') or instance.get('start', {}).get('date')
                        instance_status = instance.get('status', 'unknown')
                        
                        if instance_status == 'cancelled':
                            cancelled_count += 1
                            cancelled_dates.append(instance_date)
                    
                    logger.info(f"Total cancelled instances: {cancelled_count}")
                    if cancelled_dates:
                        logger.info(f"Cancelled dates: {', '.join(cancelled_dates)}")
                except Exception as e:
                    logger.error(f"Error checking all instances: {e}")

if __name__ == "__main__":
    test_russell_meeting()