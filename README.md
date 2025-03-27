# Calendar Sync Tool

A simple, user-friendly tool to automatically sync external calendars to Google Calendar with frequent updates.

## Features

- Sync external iCal format calendars to your Google Calendar
- Perform historical sync and keep calendars updated
- Automatically sync every 5 minutes by default (configurable)
- Handle event additions, updates, and deletions
- Properly handle duplicate events and syncing errors
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

### Token Expiration

Tokens are automatically refreshed when possible. If you encounter authentication errors:
- Delete the token files (token_*.pickle)
- Run the sync again to generate new tokens

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Thanks to the Google Calendar API team for their documentation
- This project was inspired by the need for more reliable calendar syncing between platforms