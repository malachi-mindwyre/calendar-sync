#!/usr/bin/env python3
import importlib.util
import logging
import sys
import os
from datetime import datetime, timedelta

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
    
    # Check command line arguments
    import argparse
    parser = argparse.ArgumentParser(description='Debug calendar sync operations')
    parser.add_argument('--calendar', type=str, default='IPSOS', help='Calendar name to examine')
    parser.add_argument('--search', type=str, help='Search term for events')
    parser.add_argument('--day', type=str, help='Day of week to search for (e.g., "Tuesday")')
    parser.add_argument('--google-only', action='store_true', help='Only examine Google Calendar events')
    parser.add_argument('--recurring', action='store_true', help='Focus on recurring events and their instances')
    parser.add_argument('--event-id', type=str, help='Examine a specific event by ID')
    parser.add_argument('--instance-id', type=str, help='Examine a specific instance by ID')
    parser.add_argument('--decline-instance', type=str, help='Decline a specific instance by ID')
    parser.add_argument('--restore-instance', type=str, help='Restore a previously declined instance by ID')
    parser.add_argument('--decline-demo', action='store_true', help='Run a demo of declining and syncing')
    parser.add_argument('--force-sync', action='store_true', help='Force an incremental sync after examining')
    parser.add_argument('--verbose', action='store_true', help='Show more details about events')
    args = parser.parse_args()
    
    # Find the requested calendar
    target_calendar = next((cal for cal in calendars if cal['calendarName'] == args.calendar), None)
    
    if not target_calendar:
        logger.error(f"{args.calendar} calendar not found in configuration!")
        logger.info(f"Available calendars: {[cal['calendarName'] for cal in calendars]}")
        return
    
    logger.info(f"Examining calendar: {target_calendar['calendarName']} ({target_calendar['url']})")
    
    # Create a CalendarSync instance
    sync = calendar_sync.CalendarSync(
        ical_url=target_calendar['url'],
        calendar_name=target_calendar['calendarName'],
        days_back=target_calendar.get('daysBack', 30),
        days_forward=target_calendar.get('daysForward', 60),
        sync_interval=target_calendar.get('syncInterval', 5)
    )
    
    # If running the decline demo
    if args.decline_demo:
        logger.info("\nRunning decline instance demo...")
        
        # First, find a recurring event (preferably with Russell in the name)
        time_min = (datetime.utcnow() - timedelta(days=sync.days_back)).isoformat() + 'Z'
        time_max = (datetime.utcnow() + timedelta(days=sync.days_forward)).isoformat() + 'Z'
        
        # Get recurring events (master events)
        master_events = sync.service.events().list(
            calendarId=sync.target_calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=False,  # Get master events
            orderBy='updated'
        ).execute()
        
        # Find a recurring event, preferably matching search term if provided
        target_event = None
        for event in master_events.get('items', []):
            if 'recurrence' in event:
                if args.search:
                    summary = event.get('summary', '').lower()
                    if args.search.lower() in summary:
                        target_event = event
                        break
                else:
                    # If no search term, just take the first recurring event
                    target_event = event
                    break
        
        if not target_event:
            # Try again without search filter
            for event in master_events.get('items', []):
                if 'recurrence' in event:
                    target_event = event
                    break
        
        if not target_event:
            logger.error("Could not find any recurring events in the calendar")
            return
        
        logger.info(f"Found target recurring event: {target_event.get('summary')}")
        logger.info(f"  ID: {target_event.get('id')}")
        
        # Get the instances of this event
        instances = sync.service.events().instances(
            calendarId=sync.target_calendar_id,
            eventId=target_event['id']
        ).execute()
        
        if not instances.get('items'):
            logger.error("No instances found for this recurring event")
            return
        
        # Pick the first instance that's confirmed (not already declined)
        target_instance = None
        for instance in instances.get('items', []):
            if instance.get('status') == 'confirmed':
                target_instance = instance
                break
        
        if not target_instance:
            logger.error("Could not find a confirmed instance to decline")
            return
        
        instance_date = target_instance.get('start', {}).get('dateTime') or target_instance.get('start', {}).get('date')
        logger.info(f"Found confirmed instance on {instance_date}")
        logger.info(f"  Instance ID: {target_instance.get('id')}")
        
        # Decline this instance
        logger.info(f"Declining this instance...")
        try:
            declined = sync.service.events().patch(
                calendarId=sync.target_calendar_id,
                eventId=target_instance['id'],
                body={'status': 'cancelled'}
            ).execute()
            
            logger.info(f"Successfully declined instance. New status: {declined.get('status')}")
            
            # Update the master event to simulate a sync
            logger.info(f"Simulating a sync to test preservation of declined status...")
            result = sync._create_or_update_recurring_event(target_event)
            
            # Verify that our declined status was preserved
            verify_instances = sync.service.events().instances(
                calendarId=sync.target_calendar_id,
                eventId=target_event['id']
            ).execute()
            
            for verify_instance in verify_instances.get('items', []):
                if verify_instance['id'] == target_instance['id']:
                    final_status = verify_instance.get('status')
                    logger.info(f"Status after sync: {final_status}")
                    if final_status == 'cancelled':
                        logger.info("SUCCESS: Declined status was preserved!")
                    else:
                        logger.error("FAILURE: Declined status was not preserved.")
            
            return
        except Exception as e:
            logger.error(f"Error in decline demo: {e}")
            return
    
    # If declining a specific instance
    if args.decline_instance:
        logger.info(f"\nDeclining instance with ID: {args.decline_instance}")
        try:
            # First get the instance to see its details
            instance = sync.service.events().get(
                calendarId=sync.target_calendar_id,
                eventId=args.decline_instance
            ).execute()
            
            start_date = instance.get('start', {}).get('dateTime') or instance.get('start', {}).get('date')
            logger.info(f"Found instance: {instance.get('summary')} on {start_date}")
            
            # Update the instance status to cancelled/declined
            instance['status'] = 'cancelled'
            
            # Update the instance
            updated = sync.service.events().update(
                calendarId=sync.target_calendar_id,
                eventId=args.decline_instance,
                body=instance
            ).execute()
            
            logger.info(f"Successfully declined instance. New status: {updated.get('status')}")
            
            # Force a sync to preserve this declined status
            if 'recurringEventId' in instance:
                master_id = instance['recurringEventId']
                logger.info(f"Updating master event to preserve declined status: {master_id}")
                
                # Get the master event
                master = sync.service.events().get(
                    calendarId=sync.target_calendar_id,
                    eventId=master_id
                ).execute()
                
                # Update a simple field to force the sync system to notice the change
                if 'description' in master:
                    master['description'] += " [Modified to preserve declined instance]"
                else:
                    master['description'] = "Contains declined instances that should be preserved during sync."
                
                # Update the master event
                sync.service.events().update(
                    calendarId=sync.target_calendar_id,
                    eventId=master_id,
                    body=master
                ).execute()
                
                logger.info(f"Updated master event to preserve declined status")
            
            return
        except Exception as e:
            logger.error(f"Error declining instance: {e}")
            return
    
    # If restoring a previously declined instance
    if args.restore_instance:
        logger.info(f"\nRestoring instance with ID: {args.restore_instance}")
        try:
            # First get the instance to see its details
            instance = sync.service.events().get(
                calendarId=sync.target_calendar_id,
                eventId=args.restore_instance
            ).execute()
            
            start_date = instance.get('start', {}).get('dateTime') or instance.get('start', {}).get('date')
            logger.info(f"Found instance: {instance.get('summary')} on {start_date}")
            
            # Update the instance status to confirmed
            instance['status'] = 'confirmed'
            
            # Update the instance
            updated = sync.service.events().update(
                calendarId=sync.target_calendar_id,
                eventId=args.restore_instance,
                body=instance
            ).execute()
            
            logger.info(f"Successfully restored instance. New status: {updated.get('status')}")
            return
        except Exception as e:
            logger.error(f"Error restoring instance: {e}")
            return
    
    # If examining a specific instance ID
    if args.instance_id:
        logger.info(f"\nExamining specific instance with ID: {args.instance_id}")
        try:
            instance = sync.service.events().get(
                calendarId=sync.target_calendar_id,
                eventId=args.instance_id
            ).execute()
            
            logger.info(f"Instance details:")
            logger.info(f"  Summary: {instance.get('summary')}")
            logger.info(f"  Status: {instance.get('status')}")
            logger.info(f"  ID: {instance.get('id')}")
            logger.info(f"  Start: {instance.get('start', {}).get('dateTime') or instance.get('start', {}).get('date')}")
            
            # Check if it's an instance of a recurring event
            if 'recurringEventId' in instance:
                logger.info(f"  Part of recurring series with ID: {instance.get('recurringEventId')}")
            
            # Show all properties in verbose mode
            if args.verbose:
                for key, value in instance.items():
                    if key not in ['summary', 'status', 'id', 'start', 'recurringEventId']:
                        logger.info(f"  {key}: {value}")
            
            return
        except Exception as e:
            logger.error(f"Error fetching instance: {e}")
            return
    
    # If examining a specific event ID
    if args.event_id:
        logger.info(f"\nExamining specific event with ID: {args.event_id}")
        try:
            event = sync.service.events().get(
                calendarId=sync.target_calendar_id,
                eventId=args.event_id
            ).execute()
            
            logger.info(f"Event details:")
            logger.info(f"  Summary: {event.get('summary')}")
            logger.info(f"  Status: {event.get('status')}")
            logger.info(f"  ID: {event.get('id')}")
            logger.info(f"  iCalUID: {event.get('iCalUID', 'None')}")
            
            # Check if it's recurring
            if 'recurrence' in event:
                logger.info(f"  Recurrence: {event.get('recurrence')}")
                
                # Get instances of this recurring event
                instances = sync.service.events().instances(
                    calendarId=sync.target_calendar_id,
                    eventId=event['id']
                ).execute()
                
                logger.info(f"  Found {len(instances.get('items', []))} instances of this event")
                
                # Show all instances
                for i, instance in enumerate(instances.get('items', [])):
                    start_date = instance.get('start', {}).get('dateTime') or instance.get('start', {}).get('date')
                    status = instance.get('status')
                    instance_id = instance.get('id')
                    logger.info(f"    Instance {i+1}: Date={start_date}, Status={status}, ID={instance_id}")
                    
                    if args.verbose:
                        logger.info(f"      Instance ID: {instance.get('id')}")
                        logger.info(f"      Instance Status: {instance.get('status')}")
                        if 'extendedProperties' in instance:
                            logger.info(f"      Extended Properties: {instance.get('extendedProperties')}")
            
            return
        except Exception as e:
            logger.error(f"Error fetching event: {e}")
            return
    
    # If focusing on recurring events in Google Calendar
    if args.recurring:
        logger.info("\nExamining recurring events in Google Calendar...")
        
        # If verbose mode is on, modify the debug function to show more details
        if args.verbose:
            # Time range
            time_min = (datetime.utcnow() - timedelta(days=sync.days_back)).isoformat() + 'Z'
            time_max = (datetime.utcnow() + timedelta(days=sync.days_forward)).isoformat() + 'Z'
            
            # First get recurring events (master events)
            master_events_result = sync.service.events().list(
                calendarId=sync.target_calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=False,  # Get master events
                orderBy='updated'
            ).execute()
            
            recurring_events = []
            for event in master_events_result.get('items', []):
                if 'recurrence' in event:
                    # Check for search term
                    if args.search and args.search.lower() not in event.get('summary', '').lower():
                        continue
                    
                    recurring_events.append(event)
                    
                    logger.info(f"Found recurring event: {event.get('summary')}")
                    logger.info(f"  ID: {event.get('id')}")
                    logger.info(f"  iCalUID: {event.get('iCalUID', 'None')}")
                    logger.info(f"  Recurrence: {event.get('recurrence')}")
                    
                    # Get instances of this recurring event
                    try:
                        instances = sync.service.events().instances(
                            calendarId=sync.target_calendar_id,
                            eventId=event['id']
                        ).execute()
                        
                        logger.info(f"  Found {len(instances.get('items', []))} instances of this event")
                        
                        # Show all instances with status
                        for i, instance in enumerate(instances.get('items', [])):
                            start_date = instance.get('start', {}).get('dateTime') or instance.get('start', {}).get('date')
                            status = instance.get('status')
                            instance_id = instance.get('id')
                            logger.info(f"    Instance {i+1}: Date={start_date}, Status={status}, ID={instance_id}")
                            
                            # For the first instance of Russell meeting, try declining it as a demo
                            if args.search and "Russell" in args.search and i == 0 and status == 'confirmed':
                                logger.info(f"    DEMO: Declining the first instance of Russell meeting as a test")
                                
                                # Decline this instance
                                declined = sync.service.events().patch(
                                    calendarId=sync.target_calendar_id,
                                    eventId=instance_id,
                                    body={'status': 'cancelled'}
                                ).execute()
                                
                                logger.info(f"    DEMO: New status: {declined.get('status')}")
                                
                                # Force a sync to see if our code preserves this
                                master_event = sync.service.events().get(
                                    calendarId=sync.target_calendar_id,
                                    eventId=event['id']
                                ).execute()
                                
                                logger.info(f"    DEMO: Running test sync to see if declined status is preserved...")
                                result = sync._create_or_update_recurring_event(master_event)
                                
                                # Verify that declined status was preserved
                                verify_instances = sync.service.events().instances(
                                    calendarId=sync.target_calendar_id,
                                    eventId=event['id']
                                ).execute()
                                
                                for verify_instance in verify_instances.get('items', []):
                                    if verify_instance['id'] == instance_id:
                                        logger.info(f"    DEMO: Final status after sync: {verify_instance.get('status')}")
                    except Exception as e:
                        logger.error(f"  Error getting instances: {e}")
        else:
            # Use the regular debug function
            sync.debug_check_recurring_events(search_term=args.search)
        
        return
    
    # Skip external calendar examination if only checking Google Calendar
    if not args.google_only:
        # Debug: Look at the external calendar
        if args.search:
            logger.info(f"\nLooking for events matching: {args.search} in external calendar")
            sync.debug_examine_calendar(search_term=args.search)
        
        if args.day:
            logger.info(f"\nLooking for {args.day} events in external calendar...")
            sync.debug_examine_calendar(day_of_week=args.day)
            
        if not args.search and not args.day:
            logger.info("\nLooking for all events in external calendar...")
            sync.debug_examine_calendar()
    
    # Always look at Google Calendar recurring events for comparison
    logger.info("\nExamining recurring events in Google Calendar for comparison...")
    sync.debug_check_recurring_events(search_term=args.search)
    
    # Force an incremental sync if requested
    if args.force_sync:
        logger.info("\nForcing an incremental sync to update changes...")
        sync.incremental_sync()

if __name__ == "__main__":
    main()