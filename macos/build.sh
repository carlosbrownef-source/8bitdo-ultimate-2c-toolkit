#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build dist/u2c-customfw.app (Apple silicon, unsigned apart from an ad-hoc signature) and the release zip.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
version=$(python3 -c "import re; print(re.search(r'version = \"(.+?)\"', open('pyproject.toml').read()).group(1))")
PBS_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20261026/cpython-3.12.16%2B20261026-aarch64-apple-darwin-install_only.tar.gz"
PBS_SHA256="fbf4afef53c2a6b72bb741bc06d5671a9dfaf87bd84e5aa73ac9b3d0d589f14e"

mkdir -p dist/cache
tarball=dist/cache/python.tar.gz
[ -f "$tarball" ] || curl -fsSL -o "$tarball" "$PBS_URL"
echo "$PBS_SHA256  $tarball" | shasum -a 256 -c -

app=dist/u2c-customfw.app
rm -rf "$app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources/app"
tar xzf "$tarball" -C "$app/Contents/Resources"
rsync -a --exclude __pycache__ u2c_customfw "$app/Contents/Resources/app/"
cp DISCLAIMER.md LICENSE "$app/Contents/Resources/app/"
cp macos/AppIcon.icns "$app/Contents/Resources/"  # rendered from macos/icon.svg
sed "s/@VERSION@/$version/g" macos/Info.plist > "$app/Contents/Info.plist"
swiftc -O -target arm64-apple-macos13.0 -o "$app/Contents/MacOS/u2c-customfw" macos/main.swift macos/Diagnostics.swift -framework AppKit -framework WebKit -framework IOKit -framework GameController -framework CoreHaptics
codesign --force --deep -s - "$app"
(cd dist && rm -f "u2c-customfw-$version-macos-arm64.zip" && ditto -c -k --keepParent u2c-customfw.app "u2c-customfw-$version-macos-arm64.zip")
ls -lh "dist/u2c-customfw-$version-macos-arm64.zip"
