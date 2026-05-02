#!/bin/bash

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
"$REPO_ROOT/scripts/launch_webcalyzer_macos.sh"
STATUS=$?

if [ "$STATUS" -ne 0 ]; then
  printf '\nLaunch failed. Press Return to close this window.'
  read -r _
fi

exit "$STATUS"
