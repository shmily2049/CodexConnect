#!/bin/bash
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
  python3 app.py
  status=$?
else
  status=127
fi
if [ "$status" -ne 0 ]; then
  printf '\nPlease install Python 3.11+ with Tcl/Tk from https://www.python.org/downloads/macos/\n'
  printf 'Then run: python3 app.py\n'
  read -r -p 'Press Enter to close. '
fi
