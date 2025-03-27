#!/bin/bash
# This script installs the calendar sync as a background service
# For macOS, it uses LaunchAgents
# For Linux, it uses systemd user services

# Set variables
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PYTHON_PATH=$(which python3)

echo "Installing Calendar Sync background service..."

case "$(uname -s)" in
    Darwin)
        # macOS
        echo "Detected macOS. Installing as LaunchAgent..."
        
        # Create LaunchAgent directory if it doesn't exist
        mkdir -p "$HOME/Library/LaunchAgents"
        
        # Update paths in the plist file
        sed -i '' "s|/usr/bin/python3|$PYTHON_PATH|g" "$SCRIPT_DIR/com.malachi.calendarsync.plist"
        sed -i '' "s|/Users/malachi/Documents/Github/calendar|$SCRIPT_DIR|g" "$SCRIPT_DIR/com.malachi.calendarsync.plist"
        
        # Copy the plist file to LaunchAgents
        cp "$SCRIPT_DIR/com.malachi.calendarsync.plist" "$HOME/Library/LaunchAgents/"
        
        # Load the LaunchAgent
        launchctl load -w "$HOME/Library/LaunchAgents/com.malachi.calendarsync.plist"
        
        echo "Calendar Sync is now running in the background."
        echo "To uninstall, run: launchctl unload -w ~/Library/LaunchAgents/com.malachi.calendarsync.plist"
        ;;
        
    Linux)
        # Linux (assumes systemd)
        echo "Detected Linux. Installing as systemd user service..."
        
        # Create systemd user directory if it doesn't exist
        mkdir -p "$HOME/.config/systemd/user"
        
        # Create systemd service file
        cat > "$HOME/.config/systemd/user/calendar-sync.service" << EOF
[Unit]
Description=Calendar Sync Service
After=network.target

[Service]
Type=simple
ExecStart=$PYTHON_PATH $SCRIPT_DIR/main.py
WorkingDirectory=$SCRIPT_DIR
Restart=always
RestartSec=30

[Install]
WantedBy=default.target
EOF

        # Enable and start the service
        systemctl --user daemon-reload
        systemctl --user enable calendar-sync.service
        systemctl --user start calendar-sync.service
        
        echo "Calendar Sync is now running in the background."
        echo "To check status: systemctl --user status calendar-sync.service"
        echo "To uninstall: systemctl --user disable --now calendar-sync.service"
        ;;
        
    *)
        # Unsupported OS
        echo "Unsupported operating system. Please run the script manually with:"
        echo "python3 $SCRIPT_DIR/run_calendar_sync.py"
        exit 1
        ;;
esac

echo "Done! Log files will be created in $SCRIPT_DIR directory."