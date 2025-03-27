# Calendar Sync Tool

A simple, user-friendly tool to automatically sync external calendars to Google Calendar with frequent updates.

## Features

- Sync external iCal format calendars to your Google Calendar
- Perform historical sync and keep calendars updated
- Automatically sync every 5 minutes by default (configurable)
- Handle event additions, updates, and deletions
- Properly handle duplicate events and syncing errors
- Maintain declined instances of recurring events (NEW)
- Special support for recurring events with proper timezone handling (NEW)
- Simple Jupyter Notebook UI for configuration

## Getting Started

### Prerequisites

- Python 3.7+
- Google Cloud account with Calendar API enabled
- External calendar with iCal URL (Outlook, iCloud, etc.)

### Installation

1. Clone this repository:
```bash
git clone https://github.com/malachi-mindwyre/calendar-sync.git
cd calendar-sync
```

2. Install required packages:
```bash
pip install -r requirements.txt
```

3. Set up Google Calendar API:

   a. Go to [Google Cloud Console](https://console.cloud.google.com/)
   
   b. Create a new project or select an existing one
   
   c. Navigate to "APIs & Services" > "Library"
   
   d. Search for "Google Calendar API" and enable it
   
   e. Go to "APIs & Services" > "Credentials"
   
   f. Click "Create Credentials" > "OAuth client ID"
   
   g. Choose "Desktop app" as application type and give it a name
   
   h. Download the credentials JSON file
   
   i. Rename the file to `google_calendar_key.json` and place it in the project directory 
      (This file contains sensitive data and is excluded from version control)

4. Add yourself as a test user (to avoid "App not verified" warnings):

   a. Go to "APIs & Services" > "OAuth consent screen"
   
   b. Add your Google email address in the "Test users" section
   
   c. Save changes

### Configuration

There are two ways to configure your calendar sync:

#### Option 1: Using the Jupyter Notebook (Recommended for beginners)

1. Start the Jupyter Notebook:
```bash
jupyter notebook CalendarSync.ipynb
```

2. Follow the interactive UI to:
   - Add your calendar URLs and names
   - Configure sync intervals and time windows
   - Save your configuration
   - Start the sync process

#### Option 2: Editing configuration directly

1. Open `run_calendar_sync.py`
2. Edit the `calendars` list with your calendar details

Example configuration:
```python
calendars = [
    { 
        'url': 'https://your-calendar-url.ics',
        'calendarName': 'Work Calendar',
        'daysBack': 30,
        'daysForward': 60,
        'syncInterval': 5  # 5 minutes
    }
]
```

### Running the Sync

#### From the Jupyter Notebook

Use the "Start Sync" button in the notebook.

#### From the command line

Run the sync process in the background:

**On macOS/Linux:**
```bash
nohup python run_calendar_sync.py > calendar_sync.log 2>&1 &
```

**On Windows:**
Create a batch file with:
```batch
start /B pythonw run_calendar_sync.py
```

### Finding Your Calendar URL

- **Outlook**: Calendar settings > Shared Calendars > Publish Calendar > Copy the ICS link
- **iCloud**: Calendar settings > Share Calendar > Public Calendar > Copy the link
- **Google Calendar**: Calendar settings > Integrate calendar > Secret address in iCal format
- **Microsoft 365**: Calendar > Settings > Calendar Settings > Shared Calendars > Publish Calendar

## Troubleshooting

### OAuth Consent Screen Issues

If you see "App not verified" warnings:

1. Make sure you've added your email as a test user in the OAuth consent screen settings
2. When authenticating, click "Advanced" and then "Go to [app name] (unsafe)"

### Duplicate Event Issues

The tool is designed to handle duplicate events by:
- Using the `import_` method when possible
- Looking up existing events by iCalUID
- Updating existing events instead of creating duplicates
- Creating events without problematic IDs as a fallback

### Recurring Events and Declined Instances

The tool now properly handles recurring events and maintains your declined status:
- Preserves declined instances of recurring events during sync (NEW)
- Handles timezone information for recurring events correctly
- Provides special handling for complex recurrence rules (RRULE)

#### Handling Declined Events

The calendar sync tool now properly handles declined events in two ways:

1. **Declining in Google Calendar**:
   - When you decline a specific instance of a recurring event in Google Calendar
   - The tool will automatically detect and preserve this declined status 
   - Even when the original recurring event is updated from the source calendar
   - Your declined instances will remain declined after syncs

2. **Declining in Source Calendar** (NEW):
   - When you decline an event in your source calendar (e.g., Outlook, work email)
   - The tool will detect the declined status in the source calendar's iCal feed
   - It will automatically cancel/decline the corresponding event in Google Calendar
   - This works for both regular events and recurring event instances
   - Status changes are synchronized during each sync interval

This feature is especially useful for managing recurring meetings where you need to decline specific occurrences, regardless of which calendar system you use to decline them.

#### Debugging Recurring Events

To debug recurring event issues, use the enhanced debug tool:
```bash
# Check all recurring events and their instances
python debug_calendar.py --recurring

# Check recurring events with a specific name
python debug_calendar.py --recurring --search "Meeting Name" --verbose

# Examine a specific event by ID 
python debug_calendar.py --event-id "event_id_here"

# Decline a specific instance of a recurring event
python debug_calendar.py --decline-instance "instance_id_here"

# Restore a previously declined instance
python debug_calendar.py --restore-instance "instance_id_here"

# Force a sync after examining events
python debug_calendar.py --search "Meeting Name" --force-sync
```

#### Testing Declined Meetings (NEW)

Two new test scripts have been added to help verify that declined recurring meetings are properly handled:

1. **simple_run.py** - A simplified runner for testing calendar sync:
```bash
# Run a sync for a specific calendar
python simple_run.py "IPSOS"

# Check specifically for Russell meetings
python simple_run.py "IPSOS" --russell

# Check for declined Russell meetings without syncing
python simple_run.py "IPSOS" --check-declined-russell

# Run a sync and then check for declined Russell meetings
python simple_run.py "IPSOS" --check-after-sync
```

2. **test_russell_event.py** - A focused test for the "Malachi & Russell weekly catch-up" March 3, 2025 meeting:
```bash
# Test if the March 3, 2025 declined meeting is properly handled
python test_russell_event.py "IPSOS"

# Check all dates of the Russell meeting series
python test_russell_event.py "IPSOS" --check-all-dates

# Force decline the March 3 instance if it's not properly cancelled
python test_russell_event.py "IPSOS" --force-decline
```

### Token Expiration

Tokens are automatically refreshed when possible. If you encounter authentication errors:
- Delete the token files (token_*.pickle)
- Run the sync again to generate new tokens

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Thanks to the Google Calendar API team for their documentation
- This project was inspired by the need for more reliable calendar syncing between platforms