#!/bin/bash
# Double-click me to install Wisp. (If macOS blocks it: right-click > Open > Open.)
cd "$(dirname "$0")"
xattr -dr com.apple.quarantine . 2>/dev/null || true
if /bin/bash ./install.sh; then
  echo ""
  echo "All done - you can close this window."
else
  echo ""
  echo "Something went wrong - see the messages above. You can send them to the developer from Wisp's feedback page."
fi
read -r -p "Press Enter to close..." _
