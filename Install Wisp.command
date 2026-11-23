#!/bin/bash
# Double-click this to install Wisp on your Mac.
# (If macOS says it can't be opened: right-click it > Open > Open.)
cd "$(dirname "$0")"
bash ./install.sh --local
echo
read -n 1 -s -r -p "Press any key to close this window."
