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

# Set up logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("calendar_sync.log"), logging.StreamHandler()]
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
        token_path = f'token_{self.calendar_name.replace(" ", "_")}.pickle'
        
        # Try to load existing token
        if os.path.exists(token_path):
            with open(token_path, 'rb') as token:
                creds = pickle.load(token)
                
        # Check if credentials are invalid or don't exist
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'google_calendar_key.json', SCOPES)
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
            
        # Convert to Google Calendar event format
        google_event = {
            'summary': str(event.get('SUMMARY', 'No Title')),
            'location': str(event.get('LOCATION', '')),
            'description': description,
            'start': start,
            'end': end,
            'status': 'confirmed',
            'iCalUID': str(event.get('UID', '')),
            'extendedProperties': {
                'private': {
                    'externalCalendarId': self.ical_url,
                    'externalEventId': str(event.get('UID', '')),
                    'isRecurring': 'true' if rrule else 'false'
                }
            }
        }
        
        # Add recurrence information if available
        if recurrence:
            google_event['recurrence'] = recurrence
        
        return google_event
    
    def _get_google_events(self):
        """Get all events from the target Google Calendar."""
        time_min = (datetime.utcnow() - timedelta(days=self.days_back)).isoformat() + 'Z'
        time_max = (datetime.utcnow() + timedelta(days=self.days_forward)).isoformat() + 'Z'
        
        events_result = self.service.events().list(
            calendarId=self.target_calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        google_events = {}
        for event in events_result.get('items', []):
            # Only consider events that we created from external calendar
            if event.get('extendedProperties', {}).get('private', {}).get('externalCalendarId') == self.ical_url:
                ext_id = event.get('extendedProperties', {}).get('private', {}).get('externalEventId')
                if ext_id:
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
                
                return master_event
        except Exception as e:
            logger.error(f"Error finding event by iCalUID: {e}")
        
        return None
        
    def _create_or_update_recurring_event(self, google_event):
        """Special handling for recurring events to ensure they're created properly."""
        if 'recurrence' not in google_event:
            return None
            
        try:
            logger.info(f"Special handling for recurring event: {google_event.get('summary')}")
            
            # First try to find by iCalUID
            existing = self._get_event_by_icaluid(google_event['iCalUID'])
            
            if existing:
                # Update existing recurring event
                logger.info(f"Updating existing recurring event: {existing.get('id')}")
                updated = self.service.events().update(
                    calendarId=self.target_calendar_id,
                    eventId=existing['id'],
                    body=google_event
                ).execute()
                return updated
            else:
                # Try direct insert with recurrence rule
                logger.info(f"Creating new recurring event with rule: {google_event['recurrence']}")
                
                # Ensure time zone is set for recurring events
                for time_field in ['start', 'end']:
                    if 'dateTime' in google_event[time_field] and 'timeZone' not in google_event[time_field]:
                        google_event[time_field]['timeZone'] = 'America/New_York'
                
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
                                    
                                    # Make sure start/end have timeZone
                                    for time_field in ['start', 'end']:
                                        if 'dateTime' in event_copy[time_field] and 'timeZone' not in event_copy[time_field]:
                                            event_copy[time_field]['timeZone'] = 'America/New_York'  # Default to Eastern Time
                                
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
                    logger.info(f"  Is recurring: {is_recurring}")
                    if is_recurring:
                        logger.info(f"  Recurrence rule: {rrule}")
        
        logger.info(f"Examination complete. Found {events_found} matching events, {recurring_events} are recurring.")
        return events_found
    
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
                
                # If the event already exists in Google Calendar
                if event_uid in google_events:
                    # Update the event
                    existing_event = google_events[event_uid]
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
                        # Update the existing event
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
                                    
                                    # Make sure start/end have timeZone
                                    for time_field in ['start', 'end']:
                                        if 'dateTime' in event_copy[time_field] and 'timeZone' not in event_copy[time_field]:
                                            event_copy[time_field]['timeZone'] = 'America/New_York'  # Default to Eastern Time
                                
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