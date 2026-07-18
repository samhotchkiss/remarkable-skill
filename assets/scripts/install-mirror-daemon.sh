#!/bin/bash
# Install the reMarkable mirror sync as a launchd agent (macOS).
# Runs one sync pass every 3 minutes; logs to <mirror>/.mirror/sync.log
set -e

SKILL_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
MIRROR="${REMARKABLE_MIRROR:-$HOME/reMarkable}"
LABEL="com.remarkable.mirror"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

mkdir -p "$MIRROR/.mirror" "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>cd "$SKILL_DIR" &amp;&amp; PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin REMARKABLE_MIRROR="$MIRROR" npx tsx assets/scripts/mirror-sync.ts</string>
    </array>
    <key>StartInterval</key><integer>180</integer>
    <key>RunAtLoad</key><true/>
    <key>StandardOutPath</key><string>$MIRROR/.mirror/sync.log</string>
    <key>StandardErrorPath</key><string>$MIRROR/.mirror/sync.log</string>
    <key>Nice</key><integer>10</integer>
    <key>LowPriorityIO</key><true/>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed $LABEL — mirror at $MIRROR, sync every 3 min."
echo "Logs: $MIRROR/.mirror/sync.log"
