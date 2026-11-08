#!/bin/zsh
# Opens the built Mac app on simulated devices and data, to look at its screens without a controller:
#   macos/preview.sh [QUERY]      QUERY is the page simulator's (u2c_customfw/web/static/diagsim.js), for example
#   "diagsim=cable&tweaks=all&open=firmware" (the default), "diagsim=bt", "diagsim=boot", "diagsim=dongle", "diagsim=donglepaired".
# The core runs with U2C_SIM, so it never reaches a real device and keeps its files in a temporary folder.
cd "${0:A:h}/.."
osascript -e 'tell application "Firmware Toolkit" to quit' 2>/dev/null
U2C_SIM=1 U2C_CORE_PATH="$PWD" U2C_PAGE_QUERY="&${1:-diagsim=cable&tweaks=all&open=firmware}" exec "dist/Firmware Toolkit.app/Contents/MacOS/u2c-customfw"
