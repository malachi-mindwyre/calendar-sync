- oal
Create a clean, generalized tool that syncs external calendars (Outlook, iCloud, etc.) to Google Calendar. The tool should have no hardcoded paths, usernames, or personal information, making it easily usable by anyone who downloads it.

## Core Features
1. Sync external calendars (iCal format) to Google Calendar
2. Handle recurring events and declined event instances
3. Background service installation on macOS and Linux
4. User-friendly configuration via Jupyter notebook
5. Command-line interface for headless operation

## Implementation Plan

### 1. Core Structure
- `calendar_sync.py`: Main library with sync functionality
- `main.py`: Command-line interface to run syncs
- `CalendarSync.ipynb`: Interactive Jupyter interface
- `calendar_config.json`: JSON configuration (sample provided, actual file gitignored)
- `install_background_service.sh`: Service installation script
- `com.user.calendarsync.plist`: Template for macOS service

### 2. Path Generalization
- Replace all hardcoded paths with dynamic detection:
  - Use `os.path.expanduser("~")` for home directory
  - Use `os.path.dirname(os.path.abspath(__file__))` for script directory
  - Detect username with `os.environ.get('USER')` or equivalent
  - Use relative paths within the project when possible

### 3. Configuration
- Store calendar configuration in `calendar_config.json`
- Create examples with generic URLs (like `https://example.com/calendar.ics`)
- Include structure:
```json
{
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
```
- Make sure actual config is in .gitignore but a sample is provided

### 4. Service Installation
- Create a template plist file with placeholders (`__PYTHON_PATH__`, `__SCRIPT_DIR__`)
- Have the install script determine the current user and replace placeholders
- Generate a proper plist file with the current username
- Install to the correct LaunchAgents directory
- Equivalent systemd setup for Linux

### 5. Notebook Interface
- Create a clean Jupyter interface that doesn't contain personal information
- Use generic example calendars in the UI
- Dynamically handle user paths and service names
- Provide clean UI for adding/removing calendars

### 6. Testing Plan
1. Test core sync functionality with sample calendars
2. Test installation script on macOS and Linux
3. Verify that no personal information remains in any files
4. Check that paths are properly generalized
5. Test the Jupyter notebook interface
6. Verify configuration loading/saving

### 7. GitHub Setup
1. Ensure .gitignore excludes personal config files and tokens
2. Use generic URLs in the README.md
3. Provide clear installation instructions
4. Add proper sample files for users to rename
5. Test cloning to a fresh environment to verify everything works

## Key Requirements
- ZERO hardcoded usernames or personal paths
- No personal calendar URLs anywhere in the repository
- All paths should be dynamically determined at runtime
- Service installation should generate user-specific files
- Configuration should be straightforward for new users
- Include sample/template files where needed
- Comprehensive README with clear setup instructions

## Guidelines for Implementation
1. Use environment variables and user detection whenever possible
2. Script all installation steps to avoid manual configuration
3. Provide clear error messages when configuration is missing
4. Use relative paths within the project directory
5. Include sample data that makes sense without being personal
6. Thorough testing on fresh installations

Please implement this project, ensuring it works seamlessly for any user who downloads it without requiring them to modify paths or configuration files beyond adding their own calendar details.