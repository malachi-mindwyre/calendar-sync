#!/usr/bin/env python3
import os
import time
import argparse
import logging
import pickle
from datetime import datetime, timedelta
import icalendar
import requests
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Get the script directory for relative paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Set up logging with dynamic paths
LOG_FILE = os.path.join(SCRIPT_DIR, "calendar_sync.log")
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Google Calendar API scopes
SCOPES = ['https://www.googleapis.com/auth/calendar']

class CalendarSync:
    def __init__(self, ical_url, calendar_name, days_back=30, days_forward=60, sync_interval=5):
        """
        Initialize the calendar sync object.
        
        Args:
            ical_url (str): URL of the iCal calendar to sync from
            calendar_name (str): Name for the Google Calendar
            days_back (int): Number of days in the past to sync initially
            days_forward (int): Number of days in the future to sync initially
            sync_interval (int): Minutes between sync operations
        """
        self.ical_url = ical_url
        self.calendar_name = calendar_name
        self.days_back = days_back
        self.days_forward = days_forward
        self.sync_interval = sync_interval
        self.service = self._authenticate_google()
        self.target_calendar_id = self._get_or_create_calendar()
        self.synced_events = {}  # Dictionary to track synced events by UID
        
    def _authenticate_google(self):
        """Authenticate with Google Calendar API."""
        creds = None
        # Use a filename safe version of the calendar name for the token file
        safe_name = self.calendar_name.replace(" ", "_").replace("/", "_").replace("\\", "_")
        token_path = os.path.join(SCRIPT_DIR, f'token_{safe_name}.pickle')
        key_path = os.path.join(SCRIPT_DIR, 'google_calendar_key.json')
        
        # Try to load existing token
        if os.path.exists(token_path):
            with open(token_path, 'rb') as token:
                creds = pickle.load(token)
                
        # Check if credentials are invalid or don't exist
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(key_path):
                    raise FileNotFoundError(
                        f"Google Calendar API key not found at {key_path}. "
                        "Please download it from Google Cloud Console and rename it to google_calendar_key.json"
                    )
                
                flow = InstalledAppFlow.from_client_secrets_file(key_path, SCOPES)
                creds = flow.run_local_server(port=0)
                
            # Save the token
            with open(token_path, 'wb') as token:
                pickle.dump(creds, token)
                
        return build('calendar', 'v3', credentials=creds)
    
    def _get_or_create_calendar(self):
        """Get existing calendar or create a new one with the specified name."""
        # List existing calendars
        calendar_list = self.service.calendarList().list().execute()
        
        # Check if our calendar already exists
        for calendar in calendar_list.get('items', []):
            if calendar.get('summary') == self.calendar_name:
                logger.info(f"Found existing calendar: {self.calendar_name}")
                return calendar['id']
        
        # If not found, create a new calendar
        logger.info(f"Creating new calendar: {self.calendar_name}")
        calendar = {
            'summary': self.calendar_name,
            'timeZone': 'UTC'
        }
        created_calendar = self.service.calendars().insert(body=calendar).execute()
        return created_calendar['id']
    
    def fetch_ical_events(self):
        """Fetch events from the iCal URL."""
        try:
            response = requests.get(self.ical_url)
            response.raise_for_status()  # Raise an exception for HTTP errors
            
            calendar = icalendar.Calendar.from_ical(response.text)
            logger.info(f"Successfully fetched calendar data from {self.ical_url}")
            return calendar
        except Exception as e:
            logger.error(f"Error fetching iCal data: {e}")
            return None
    
    def _convert_ical_to_google_event(self, event):
        """Convert an iCal event to Google Calendar format."""
        start_dt = event.get('DTSTART').dt
        
        # Handle datetime vs date events differently
        if hasattr(start_dt, 'tzinfo'):  # It's a datetime
            # Check if timezone info is present
            if start_dt.tzinfo is None:
                # No timezone, use UTC
                logger.warning(f"Event {event.get('SUMMARY')} has no timezone. Using UTC.")
                start = {
                    'dateTime': start_dt.strftime('%Y-%m-%dT%H:%M:%S'),
                    'timeZone': 'UTC'
                }
            else:
                # Has timezone, keep it
                start = {
                    'dateTime': start_dt.strftime('%Y-%m-%dT%H:%M:%S'),
                    'timeZone': str(start_dt.tzinfo)
                }
        else:  # It's a date (all-day event)
            start = {'date': start_dt.strftime('%Y-%m-%d')}
            
        # Get end time or use start time if not present
        end_dt = event.get('DTEND', event.get('DTSTART')).dt
        
        # Handle datetime vs date events for end time
        if hasattr(end_dt, 'tzinfo'):  # It's a datetime
            # Check if timezone info is present
            if end_dt.tzinfo is None:
                # No timezone, use UTC
                end = {
                    'dateTime': end_dt.strftime('%Y-%m-%dT%H:%M:%S'),
                    'timeZone': 'UTC'
                }
            else:
                # Has timezone, keep it
                end = {
                    'dateTime': end_dt.strftime('%Y-%m-%dT%H:%M:%S'),
                    'timeZone': str(end_dt.tzinfo)
                }
        else:  # It's a date (all-day event)
            end = {'date': end_dt.strftime('%Y-%m-%d')}
            
        # Format the description to include original event details and sync info
        description = event.get('DESCRIPTION', '')
        if description:
            description += '\n\n'
        description += f"Synced from external calendar on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        # Check for event status - default is confirmed
        event_status = 'confirmed'  
        
        # ===== IMPORTANT: DETECTION OF CANCELLED EVENTS =====
        # Different calendar systems represent cancelled/declined events in different ways.
        # We need to check multiple indicators to properly detect cancelled status.
        
        # 1. First check summary for "Canceled:" or "Cancelled:" prefix
        # This is how Outlook/Exchange represents cancelled events in the iCal export
        event_summary = str(event.get('SUMMARY', ''))
        if event_summary.startswith('Canceled:') or event_summary.startswith('Cancelled:'):
            event_status = 'cancelled'
            logger.info(f"Found cancelled event in source calendar (from summary prefix): {event_summary}")
        
        # 2. Check for STATUS property in the iCal event
        # STATUS property in iCal can be: TENTATIVE, CONFIRMED, or CANCELLED
        ical_status = event.get('STATUS')
        if ical_status:
            ical_status_str = str(ical_status).upper()
            if ical_status_str == 'CANCELLED':
                event_status = 'cancelled'
                logger.info(f"Found cancelled event in source calendar (from STATUS): {event.get('SUMMARY')}")
            elif ical_status_str == 'TENTATIVE':
                event_status = 'tentative'
                logger.info(f"Found tentative event in source calendar: {event.get('SUMMARY')}")
        
        # 3. Check for PARTSTAT (participation status) for attendees
        # This indicates if a specific attendee has declined the event
        # Values can be: NEEDS-ACTION, ACCEPTED, DECLINED, TENTATIVE, DELEGATED, etc.
        attendee = event.get('ATTENDEE')
        if attendee:
            # Find if the current user declined the event - use a generic approach
            # We can't assume user's email, so just look for any DECLINED status
            for att in attendee if isinstance(attendee, list) else [attendee]:
                att_str = str(att)
                if 'PARTSTAT=DECLINED' in att_str.upper():
                    event_status = 'cancelled'
                    logger.info(f"Event declined by an attendee in source calendar: {event.get('SUMMARY')}")
                    break
        
        # Check if event is recurring
        rrule = event.get('RRULE')
        recurrence = None
        if rrule:
            logger.info(f"Found recurring event with summary: {event.get('SUMMARY')} and UID: {event.get('UID')}")
            logger.info(f"Recurrence rule: {rrule}")
            
            # More detailed logging of the recurrence rule components
            freq = rrule.get('FREQ', ['NONE'])[0]
            byday = rrule.get('BYDAY', ['NONE'])
            interval = rrule.get('INTERVAL', [1])[0]
            until = rrule.get('UNTIL', [None])[0]
            
            logger.info(f"Detailed recurrence: FREQ={freq}, BYDAY={byday}, INTERVAL={interval}, UNTIL={until}")
            
            # Convert the iCal RRULE to Google Calendar recurrence format
            try:
                rrule_str = rrule.to_ical().decode('utf-8')
                logger.info(f"Raw RRULE string: {rrule_str}")
                recurrence = [f"RRULE:{rrule_str}"]
            except Exception as e:
                logger.error(f"Error converting recurrence rule: {e}")
                # Manually construct the recurrence rule
                rrule_parts = []
                if freq:
                    rrule_parts.append(f"FREQ={freq}")
                if byday != ['NONE']:
                    rrule_parts.append(f"BYDAY={','.join(byday)}")
                if interval != 1:
                    rrule_parts.append(f"INTERVAL={interval}")
                if until:
                    rrule_parts.append(f"UNTIL={until.strftime('%Y%m%dT%H%M%SZ')}")
                
                manual_rrule = ";".join(rrule_parts)
                logger.info(f"Manually constructed RRULE: {manual_rrule}")
                recurrence = [f"RRULE:{manual_rrule}"]
                
            # Check for RECURRENCE-ID which indicates an exception to a recurring event
            recurrence_id = event.get('RECURRENCE-ID')
            
            # Initialize extended_properties regardless of recurrence_id
            extended_properties = {
                'private': {
                    'externalCalendarId': self.ical_url,
                    'externalEventId': str(event.get('UID', '')),
                    'isRecurring': 'true' if rrule else 'false',
                    'sourceCalendarStatus': str(ical_status) if ical_status else 'none'
                }
            }
            
            if recurrence_id:
                logger.info(f"Found exception to recurring event: {event.get('SUMMARY')} on {recurrence_id.dt}")
                
                # This is a special case - need to handle as an exception
                # Mark in extended properties that this is a recurring event exception
                exception_date = recurrence_id.dt
                exception_date_str = ""
                if hasattr(exception_date, 'strftime'):
                    exception_date_str = exception_date.strftime('%Y-%m-%dT%H:%M:%S')
                else:
                    exception_date_str = str(exception_date)
                    
                logger.info(f"Exception date: {exception_date_str}")
                
                # Add recurrence exception info to extended_properties
                extended_properties['private']['recurrenceException'] = 'true'
                extended_properties['private']['recurrenceExceptionDate'] = exception_date_str
                
                # If this exception is cancelled, it means this specific instance was declined
                if event_status == 'cancelled':
                    logger.info(f"This recurring event exception is cancelled: {event.get('SUMMARY')} on {exception_date_str}")
            
        # Convert to Google Calendar event format
        google_event = {
            'summary': str(event.get('SUMMARY', 'No Title')),
            'location': str(event.get('LOCATION', '')),
            'description': description,
            'start': start,
            'end': end,
            'status': event_status,  # Use the detected status
            'iCalUID': str(event.get('UID', '')),
            'extendedProperties': extended_properties
        }
        
        # Add recurrence information if available
        if recurrence:
            google_event['recurrence'] = recurrence
            
        # Log if we found a cancelled event
        if event_status == 'cancelled':
            logger.info(f"Converting event with cancelled status: {google_event.get('summary')}")
        
        return google_event
    
    def _get_google_events(self):
        """Get all events from the target Google Calendar."""
        time_min = (datetime.utcnow() - timedelta(days=self.days_back)).isoformat() + 'Z'
        time_max = (datetime.utcnow() + timedelta(days=self.days_forward)).isoformat() + 'Z'
        
        # First get all master events (including recurring)
        master_events_result = self.service.events().list(
            calendarId=self.target_calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=False,  # Get master events for recurring events
            orderBy='updated'
        ).execute()
        
        # Then get expanded instances to identify declined occurrences
        instance_events_result = self.service.events().list(
            calendarId=self.target_calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,  # Get individual instances
            orderBy='startTime'
        ).execute()
        
        # Create a map of recurring event IDs to their instances
        recurring_event_instances = {}
        for event in instance_events_result.get('items', []):
            # Check if this is an instance of a recurring event
            if 'recurringEventId' in event:
                master_id = event['recurringEventId']
                if master_id not in recurring_event_instances:
                    recurring_event_instances[master_id] = []
                recurring_event_instances[master_id].append(event)
        
        # Process the master events and attach instance info
        google_events = {}
        for event in master_events_result.get('items', []):
            # Only consider events that we created from external calendar
            if event.get('extendedProperties', {}).get('private', {}).get('externalCalendarId') == self.ical_url:
                ext_id = event.get('extendedProperties', {}).get('private', {}).get('externalEventId')
                if ext_id:
                    # Check if this is a recurring event with instances
                    if 'recurrence' in event and event['id'] in recurring_event_instances:
                        # Add instances to the event for reference
                        event['_instances'] = recurring_event_instances[event['id']]
                        
                        # Log any declined instances
                        declined_instances = [
                            instance for instance in event['_instances'] 
                            if instance.get('status') == 'cancelled'
                        ]
                        if declined_instances:
                            logger.info(f"Found {len(declined_instances)} declined instances for recurring event: {event.get('summary')}")
                    
                    google_events[ext_id] = event
                    
        return google_events
    
    def _get_event_by_icaluid(self, ical_uid):
        """Get existing Google Calendar event by iCalUID."""
        try:
            # Try to find existing event with this UID
            existing_events = self.service.events().list(
                calendarId=self.target_calendar_id,
                iCalUID=ical_uid,
                singleEvents=False  # Important: Get the recurring event master, not instances
            ).execute()
            
            if existing_events.get('items'):
                master_event = existing_events['items'][0]
                logger.info(f"Found existing event by iCalUID: {master_event.get('summary')}")
                
                # Check if it's a recurring event
                if 'recurrence' in master_event:
                    logger.info(f"This is a recurring event with rule: {master_event['recurrence']}")
                    
                    # Also fetch the instances to get exceptions (declined, modified instances)
                    try:
                        instances = self.service.events().instances(
                            calendarId=self.target_calendar_id,
                            eventId=master_event['id']
                        ).execute()
                        
                        # Add information about instances to the master event for reference
                        master_event['_instances'] = instances.get('items', [])
                        logger.info(f"Found {len(master_event['_instances'])} instances of recurring event")
                        
                        # Log any declined instances
                        declined_instances = [
                            instance for instance in master_event['_instances'] 
                            if instance.get('status') == 'cancelled'
                        ]
                        if declined_instances:
                            logger.info(f"Found {len(declined_instances)} declined instances of recurring event")
                    except Exception as e:
                        logger.error(f"Error fetching instances of recurring event: {e}")
                
                return master_event
        except Exception as e:
            logger.error(f"Error finding event by iCalUID: {e}")
        
        return None
        
    def _create_or_update_recurring_event(self, google_event):
        """
        Special handling for recurring events to ensure they're created properly,
        and that any declined instances are preserved during updates.
        
        The challenge with recurring events is that when you update a recurring event's
        master record, Google Calendar will reset all instances to their default state
        based on the recurrence rule. This means any previously declined instances 
        would revert back to "confirmed" status.
        
        To solve this, we:
        1. First identify and store any declined instances before updating
        2. Update the master recurring event
        3. Re-apply the "cancelled" status to those instances that were previously declined
        4. Verify that the declined status was properly preserved
        
        This ensures that when a user declines a specific instance of a recurring meeting,
        that declined status persists even when the master event is updated from the
        source calendar.
        """
        if 'recurrence' not in google_event:
            return None
            
        try:
            logger.info(f"Special handling for recurring event: {google_event.get('summary')}")
            
            # First try to find by iCalUID
            existing = self._get_event_by_icaluid(google_event['iCalUID'])
            
            if existing:
                # Update existing recurring event
                logger.info(f"Updating existing recurring event: {existing.get('id')}")
                
                # Store the event ID for later use with instances
                event_id = existing['id']
                
                # CRITICAL STEP 1: Find and store declined instances BEFORE updating the master event
                # ALWAYS fetch the latest instance information directly from Google Calendar
                try:
                    instances_result = self.service.events().instances(
                        calendarId=self.target_calendar_id,
                        eventId=event_id
                    ).execute()
                    
                    # Find all declined/cancelled instances before updating
                    declined_instances = [
                        instance for instance in instances_result.get('items', []) 
                        if instance.get('status') == 'cancelled'
                    ]
                    
                    if declined_instances:
                        logger.info(f"Found {len(declined_instances)} declined instances that need to be preserved")
                        for instance in declined_instances:
                            instance_date = instance.get('originalStartTime', {}).get('dateTime') or instance.get('originalStartTime', {}).get('date')
                            logger.info(f"  Declined instance on {instance_date} with ID {instance.get('id')}")
                    
                except Exception as e:
                    logger.error(f"Error fetching instances directly: {e}")
                    declined_instances = []
                    
                    # Fallback to cached instances if available
                    if '_instances' in existing:
                        # Use cached instance information
                        declined_instances = [
                            instance for instance in existing['_instances'] 
                            if instance.get('status') == 'cancelled'
                        ]
                        logger.info(f"Using cached data: Preserving {len(declined_instances)} declined instances during update")
                
                # Remove our custom field before update if it exists
                if '_instances' in existing:
                    del existing['_instances']
                
                # CRITICAL STEP 2: Update the master event - this will reset all instances
                updated = self.service.events().update(
                    calendarId=self.target_calendar_id,
                    eventId=event_id,
                    body=google_event
                ).execute()
                
                # CRITICAL STEP 3: Re-apply declined status to instances that were previously declined
                for instance in declined_instances:
                    try:
                        # Get the instance ID and date
                        instance_id = instance['id']
                        instance_date = instance.get('originalStartTime', {}).get('dateTime') or instance.get('originalStartTime', {}).get('date')
                        
                        logger.info(f"Re-applying declined status to instance on {instance_date}")
                        
                        # Cancel/decline this specific instance
                        updated_instance = self.service.events().patch(
                            calendarId=self.target_calendar_id,
                            eventId=instance_id,
                            body={'status': 'cancelled'}
                        ).execute()
                        
                        if updated_instance.get('status') == 'cancelled':
                            logger.info(f"Successfully preserved declined status for instance on {instance_date}")
                        else:
                            logger.warning(f"Failed to preserve declined status for instance on {instance_date}")
                    except Exception as e:
                        logger.error(f"Error preserving declined instance: {e}")
                
                # CRITICAL STEP 4: Verify that declined instances were actually preserved
                try:
                    verify_instances = self.service.events().instances(
                        calendarId=self.target_calendar_id,
                        eventId=event_id
                    ).execute()
                    
                    verified_declined = [
                        instance for instance in verify_instances.get('items', []) 
                        if instance.get('status') == 'cancelled'
                    ]
                    
                    if verified_declined:
                        logger.info(f"Verification: Successfully preserved {len(verified_declined)} declined instances")
                    else:
                        logger.warning(f"Verification: No declined instances were preserved! This is likely a bug.")
                except Exception as e:
                    logger.error(f"Error verifying declined instances: {e}")
                
                return updated
            else:
                # Try direct insert with recurrence rule
                logger.info(f"Creating new recurring event with rule: {google_event['recurrence']}")
                
                # Ensure time zone is set for recurring events
                for time_field in ['start', 'end']:
                    if 'dateTime' in google_event[time_field] and 'timeZone' not in google_event[time_field]:
                        google_event[time_field]['timeZone'] = 'UTC'  # Use UTC as default instead of hardcoded timezone
                
                # Try to create without iCalUID first
                event_copy = google_event.copy()
                if 'iCalUID' in event_copy:
                    del event_copy['iCalUID']
                    
                created = self.service.events().insert(
                    calendarId=self.target_calendar_id,
                    body=event_copy
                ).execute()
                
                logger.info(f"Successfully created recurring event: {created.get('id')}")
                return created
                
        except Exception as e:
            logger.error(f"Error in special recurring event handling: {e}")
            return None
    
    def initial_sync(self):
        """Perform the initial sync of calendar events."""
        logger.info("Starting initial sync...")
        
        # Fetch external calendar
        ical_calendar = self.fetch_ical_events()
        if not ical_calendar:
            logger.error("Failed to fetch external calendar. Aborting sync.")
            return
        
        # Get existing Google Calendar events
        google_events = self._get_google_events()
        logger.info(f"Found {len(google_events)} existing events in Google Calendar")
        
        # Process all events from the iCal file
        events_added = 0
        events_updated = 0
        
        for component in ical_calendar.walk():
            if component.name == "VEVENT":
                event_uid = str(component.get('UID', ''))
                
                # Skip events without UID
                if not event_uid:
                    logger.warning("Skipping event without UID")
                    continue
                
                # Convert to Google format
                google_event = self._convert_ical_to_google_event(component)
                
                # If the event already exists in Google Calendar by UID in our tracking
                if event_uid in google_events:
                    # Update the event
                    existing_event = google_events[event_uid]
                    
                    # Check if this is a recurring event
                    if 'recurrence' in google_event:
                        # Fetch full event info including instances
                        full_event = self._get_event_by_icaluid(google_event['iCalUID'])
                        if full_event and '_instances' in full_event:
                            # Use special handling for recurring events
                            logger.info(f"Using special recurring event handling for existing event during initial sync")
                            result = self._create_or_update_recurring_event(google_event)
                            if result:
                                events_updated += 1
                                continue
                    
                    # Regular update if not recurring or special handling failed
                    self.service.events().update(
                        calendarId=self.target_calendar_id,
                        eventId=existing_event['id'],
                        body=google_event
                    ).execute()
                    events_updated += 1
                else:
                    # Special handling for recurring events
                    if 'recurrence' in google_event:
                        logger.info(f"Using special handling for recurring event: {google_event.get('summary')}")
                        result = self._create_or_update_recurring_event(google_event)
                        
                        if result:
                            if result.get('status') == 'confirmed':
                                events_added += 1
                                logger.info(f"Successfully created/updated recurring event: {google_event.get('summary')}")
                            continue
                    
                    # Regular handling for non-recurring events or if special handling failed
                    existing_event = self._get_event_by_icaluid(google_event['iCalUID'])
                    
                    if existing_event:
                        # Update the existing event
                        self.service.events().update(
                            calendarId=self.target_calendar_id,
                            eventId=existing_event['id'],
                            body=google_event
                        ).execute()
                        events_updated += 1
                        logger.info(f"Updated existing event with UID: {event_uid}")
                    else:
                        # Create new event with import flag to avoid duplicates
                        try:
                            # Log the event details before import
                            logger.info(f"Attempting to import event: {google_event.get('summary')}")
                            if 'recurrence' in google_event:
                                logger.info(f"With recurrence: {google_event['recurrence']}")
                            
                            self.service.events().import_(
                                calendarId=self.target_calendar_id,
                                body=google_event
                            ).execute()
                            events_added += 1
                            logger.info(f"Successfully imported event: {google_event.get('summary')}")
                        except Exception as e:
                            logger.error(f"Error importing event: {e}")
                            
                            # Fall back to insert if import fails
                            try:
                                # Make a clean copy for insertion
                                event_copy = google_event.copy()
                                
                                # Remove problematic fields if present
                                if 'iCalUID' in event_copy:
                                    logger.info(f"Removing iCalUID for direct insert")
                                    del event_copy['iCalUID']
                                
                                # Ensure explicit timezone for recurring events
                                if 'recurrence' in event_copy:
                                    logger.info(f"Ensuring timezone for recurring event insert: {event_copy.get('summary')}")
                                    
                                    # Make sure start/end have timeZone with UTC instead of hardcoded timezone
                                    for time_field in ['start', 'end']:
                                        if 'dateTime' in event_copy[time_field] and 'timeZone' not in event_copy[time_field]:
                                            event_copy[time_field]['timeZone'] = 'UTC'
                                
                                logger.info(f"Attempting direct insert for: {event_copy.get('summary')}")
                                created_event = self.service.events().insert(
                                    calendarId=self.target_calendar_id,
                                    body=event_copy
                                ).execute()
                                
                                events_added += 1
                                logger.info(f"Successfully inserted event: {event_copy.get('summary')} with ID: {created_event.get('id')}")
                            except Exception as insert_e:
                                logger.error(f"Error creating event: {insert_e}")
                
                # Keep track of synced events
                self.synced_events[event_uid] = True
        
        # Find and delete events that no longer exist in the source calendar
        for ext_id, event in google_events.items():
            if ext_id not in self.synced_events:
                self.service.events().delete(
                    calendarId=self.target_calendar_id,
                    eventId=event['id']
                ).execute()
                logger.info(f"Deleted event {event.get('summary')} (no longer in source)")
        
        logger.info(f"Initial sync complete. Added {events_added} events, updated {events_updated} events.")
    
    def debug_examine_calendar(self, search_term=None, day_of_week=None):
        """Debug helper to examine events in the source calendar."""
        logger.info(f"Examining source calendar for events matching: {search_term} or day of week: {day_of_week}")
        
        # Fetch external calendar
        ical_calendar = self.fetch_ical_events()
        if not ical_calendar:
            logger.error("Failed to fetch external calendar for examination.")
            return
        
        events_found = 0
        recurring_events = 0
        cancelled_events = 0
        exceptions_found = 0
        
        for component in ical_calendar.walk():
            if component.name == "VEVENT":
                summary = str(component.get('SUMMARY', 'No Title'))
                uid = str(component.get('UID', 'No UID'))
                start = component.get('DTSTART').dt
                
                # Check if event matches search criteria
                matches_search = search_term and search_term.lower() in summary.lower()
                
                # Check for day of week
                matches_day = False
                if day_of_week and hasattr(start, 'weekday'):
                    weekday = start.weekday()
                    weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                    day_str = weekday_names[weekday]
                    matches_day = day_of_week.lower() == day_str.lower()
                
                if matches_search or matches_day or not (search_term or day_of_week):
                    events_found += 1
                    rrule = component.get('RRULE')
                    is_recurring = rrule is not None
                    if is_recurring:
                        recurring_events += 1
                    
                    logger.info(f"Found event: {summary}")
                    logger.info(f"  UID: {uid}")
                    logger.info(f"  Start: {start}")
                    
                    # Check for cancellation in the summary
                    event_summary = str(component.get('SUMMARY', ''))
                    if event_summary.startswith('Canceled:') or event_summary.startswith('Cancelled:'):
                        cancelled_events += 1
                        logger.info(f"  Event is CANCELLED via summary prefix in source calendar!")
                    
                    # Check for STATUS property
                    status = component.get('STATUS')
                    if status:
                        logger.info(f"  Status: {status}")
                        if str(status).upper() == 'CANCELLED':
                            cancelled_events += 1
                            logger.info(f"  Event is CANCELLED via STATUS in source calendar!")
                    
                    # Check for RECURRENCE-ID (indicates exception to recurring event)
                    recurrence_id = component.get('RECURRENCE-ID')
                    if recurrence_id:
                        exceptions_found += 1
                        logger.info(f"  This is an EXCEPTION to a recurring event for date: {recurrence_id.dt}")
                        
                    # Check for attendee status
                    attendee = component.get('ATTENDEE')
                    if attendee:
                        logger.info(f"  Event has attendees:")
                        for att in attendee if isinstance(attendee, list) else [attendee]:
                            att_str = str(att)
                            # Look for participation status
                            if 'PARTSTAT=' in att_str.upper():
                                partstat_start = att_str.upper().find('PARTSTAT=') + 9
                                partstat_end = att_str.find(';', partstat_start) 
                                if partstat_end == -1:
                                    partstat_end = att_str.find(':', partstat_start)
                                if partstat_end == -1:
                                    partstat_end = len(att_str)
                                partstat = att_str[partstat_start:partstat_end]
                                
                                # Extract email 
                                email_start = att_str.find('mailto:') + 7 if 'mailto:' in att_str else att_str.rfind(':') + 1
                                email = att_str[email_start:]
                                
                                logger.info(f"    Attendee: {email}, Status: {partstat}")
                                
                                # If the attendee has declined and it's the user, mark this
                                if partstat == 'DECLINED':
                                    logger.info(f"    Attendee {email} has DECLINED this event")
                    
                    logger.info(f"  Is recurring: {is_recurring}")
                    if is_recurring:
                        logger.info(f"  Recurrence rule: {rrule}")
        
        logger.info(f"Examination complete. Found {events_found} matching events:")
        logger.info(f"  - {recurring_events} are recurring events")
        logger.info(f"  - {exceptions_found} are exceptions to recurring events")  
        logger.info(f"  - {cancelled_events} are cancelled in the source calendar")
        return events_found
    
    def debug_check_recurring_events(self, search_term=None):
        """Debug helper to examine recurring events and their instances in Google Calendar."""
        logger.info(f"Examining Google Calendar for recurring events matching: {search_term}")
        
        # Get time range
        time_min = (datetime.utcnow() - timedelta(days=self.days_back)).isoformat() + 'Z'
        time_max = (datetime.utcnow() + timedelta(days=self.days_forward)).isoformat() + 'Z'
        
        # First get recurring events (master events)
        master_events_result = self.service.events().list(
            calendarId=self.target_calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=False,  # Get master events
            orderBy='updated'
        ).execute()
        
        recurring_events = []
        for event in master_events_result.get('items', []):
            if 'recurrence' in event:
                # Check for search term
                if search_term and search_term.lower() not in event.get('summary', '').lower():
                    continue
                
                recurring_events.append(event)
                
                logger.info(f"Found recurring event: {event.get('summary')}")
                logger.info(f"  ID: {event.get('id')}")
                logger.info(f"  iCalUID: {event.get('iCalUID', 'None')}")
                logger.info(f"  Recurrence: {event.get('recurrence')}")
                
                # Get instances of this recurring event
                try:
                    instances = self.service.events().instances(
                        calendarId=self.target_calendar_id,
                        eventId=event['id']
                    ).execute()
                    
                    logger.info(f"  Found {len(instances.get('items', []))} instances of this event")
                    
                    # Check for declined/cancelled instances
                    declined_instances = [
                        instance for instance in instances.get('items', [])
                        if instance.get('status') == 'cancelled'
                    ]
                    
                    if declined_instances:
                        logger.info(f"  {len(declined_instances)} instances are marked as declined/cancelled:")
                        for declined in declined_instances:
                            start_date = declined.get('originalStartTime', {}).get('dateTime') or declined.get('originalStartTime', {}).get('date')
                            logger.info(f"    Declined instance on {start_date}")
                
                except Exception as e:
                    logger.error(f"  Error fetching instances: {e}")
        
        logger.info(f"Recurring event examination complete. Found {len(recurring_events)} recurring events.")
        return recurring_events
    
    def incremental_sync(self):
        """Perform an incremental sync to update changes."""
        logger.info("Starting incremental sync...")
        
        # Fetch external calendar
        ical_calendar = self.fetch_ical_events()
        if not ical_calendar:
            logger.error("Failed to fetch external calendar. Aborting sync.")
            return
        
        # Get existing Google Calendar events
        google_events = self._get_google_events()
        
        # Preserve event cache - VERY important for recurring events with declined instances
        recurring_events_cache = {}
        for uid, event in google_events.items():
            if 'recurrence' in event and '_instances' in event:
                recurring_events_cache[uid] = event['_instances']
                logger.info(f"Caching {len(event['_instances'])} instances for recurring event {event.get('summary')}")
                
                # Look for declined instances
                declined = [inst for inst in event['_instances'] if inst.get('status') == 'cancelled']
                if declined:
                    logger.info(f"Found {len(declined)} declined instances to preserve")
        
        # Track the events that still exist
        current_events = {}
        events_added = 0
        events_updated = 0
        
        for component in ical_calendar.walk():
            if component.name == "VEVENT":
                event_uid = str(component.get('UID', ''))
                
                # Skip events without UID
                if not event_uid:
                    logger.warning("Skipping event without UID")
                    continue
                
                # Mark this event as still existing
                current_events[event_uid] = True
                
                # Convert to Google format
                google_event = self._convert_ical_to_google_event(component)
                
                # Check if this is a recurring event that needs special handling
                is_recurring = 'recurrence' in google_event
                
                # If the event already exists in Google Calendar
                if event_uid in google_events:
                    # Get the existing event
                    existing_event = google_events[event_uid]
                    
                    # Special handling for recurring events to preserve declined instances
                    if is_recurring:
                        logger.info(f"Using special recurring event handling for existing tracked event during incremental sync")
                        result = self._create_or_update_recurring_event(google_event)
                        if result:
                            events_updated += 1
                            logger.info(f"Updated recurring event with preserved declined instances")
                            continue
                    
                    # Normal update if not recurring or special handling failed
                    self.service.events().update(
                        calendarId=self.target_calendar_id,
                        eventId=existing_event['id'],
                        body=google_event
                    ).execute()
                    events_updated += 1
                else:
                    # Check if event exists by iCalUID
                    existing_event = self._get_event_by_icaluid(google_event['iCalUID'])
                    
                    if existing_event:
                        # Special handling for recurring events to preserve declined instances
                        if is_recurring:
                            # Use the special handling for recurring events
                            logger.info(f"Using special recurring event handling for existing event by iCalUID during incremental sync")
                            result = self._create_or_update_recurring_event(google_event)
                            if result:
                                events_updated += 1
                                logger.info(f"Updated recurring event with preserved declined instances")
                                continue
                        
                        # Normal update if not recurring or special handling failed
                        self.service.events().update(
                            calendarId=self.target_calendar_id,
                            eventId=existing_event['id'],
                            body=google_event
                        ).execute()
                        events_updated += 1
                    else:
                        # Create new event with import flag to avoid duplicates
                        try:
                            # Log the event details before import
                            logger.info(f"Attempting to import event in incremental sync: {google_event.get('summary')}")
                            if 'recurrence' in google_event:
                                logger.info(f"With recurrence: {google_event['recurrence']}")
                            
                            self.service.events().import_(
                                calendarId=self.target_calendar_id,
                                body=google_event
                            ).execute()
                            events_added += 1
                            logger.info(f"Successfully imported event in incremental sync: {google_event.get('summary')}")
                        except Exception as e:
                            logger.error(f"Error importing event in incremental sync: {e}")
                            
                            # Fall back to insert if import fails
                            try:
                                # Make a clean copy for insertion
                                event_copy = google_event.copy()
                                
                                # Remove problematic fields if present
                                if 'iCalUID' in event_copy:
                                    logger.info(f"Removing iCalUID for direct insert in incremental sync")
                                    del event_copy['iCalUID']
                                
                                # Ensure explicit timezone for recurring events
                                if 'recurrence' in event_copy:
                                    logger.info(f"Ensuring timezone for recurring event insert in incremental sync: {event_copy.get('summary')}")
                                    
                                    # Make sure start/end have timeZone with UTC instead of hardcoded timezone
                                    for time_field in ['start', 'end']:
                                        if 'dateTime' in event_copy[time_field] and 'timeZone' not in event_copy[time_field]:
                                            event_copy[time_field]['timeZone'] = 'UTC'
                                
                                logger.info(f"Attempting direct insert in incremental sync for: {event_copy.get('summary')}")
                                created_event = self.service.events().insert(
                                    calendarId=self.target_calendar_id,
                                    body=event_copy
                                ).execute()
                                
                                events_added += 1
                                logger.info(f"Successfully inserted event in incremental sync: {event_copy.get('summary')} with ID: {created_event.get('id')}")
                            except Exception as insert_e:
                                logger.error(f"Error creating event in incremental sync: {insert_e}")
        
        # Find and delete events that no longer exist in the source calendar
        events_deleted = 0
        for ext_id, event in google_events.items():
            if ext_id not in current_events:
                self.service.events().delete(
                    calendarId=self.target_calendar_id,
                    eventId=event['id']
                ).execute()
                events_deleted += 1
        
        logger.info(f"Incremental sync complete. Added {events_added}, updated {events_updated}, deleted {events_deleted} events.")
    
    def run(self):
        """Run the sync process continuously."""
        # Perform initial sync
        self.initial_sync()
        
        # Continuous sync loop
        try:
            while True:
                logger.info(f"Waiting {self.sync_interval} minutes until next sync...")
                time.sleep(self.sync_interval * 60)
                self.incremental_sync()
        except KeyboardInterrupt:
            logger.info("Sync process interrupted by user. Exiting...")

def main():
    """Main function to parse arguments and start the sync process."""
    parser = argparse.ArgumentParser(description='Sync external calendars to Google Calendar')
    parser.add_argument('--url', required=True, help='iCal URL to sync from')
    parser.add_argument('--name', required=True, help='Name for the Google Calendar')
    parser.add_argument('--days-back', type=int, default=30, help='Number of days in the past to sync initially')
    parser.add_argument('--days-forward', type=int, default=60, help='Number of days in the future to sync initially')
    parser.add_argument('--interval', type=int, default=5, help='Minutes between sync operations')
    
    args = parser.parse_args()
    
    # Create and run the sync process
    sync = CalendarSync(
        ical_url=args.url,
        calendar_name=args.name,
        days_back=args.days_back,
        days_forward=args.days_forward,
        sync_interval=args.interval
    )
    
    sync.run()

if __name__ == '__main__':
    main()