#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build Firmware Toolkit.app (unsigned apart from an ad-hoc signature) and its release zip, for one architecture:
#   macos/build.sh            Apple silicon: dist/Firmware Toolkit.app and dist/firmware-toolkit-X.Y.Z-macos-arm64.zip
#   macos/build.sh x86_64     Intel: dist/x86_64/Firmware Toolkit.app and dist/firmware-toolkit-X.Y.Z-macos-x86_64.zip
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
arch=${1:-arm64}
version=$(python3 -c "import re; print(re.search(r'version = \"(.+?)\"', open('pyproject.toml').read()).group(1))")
PBS=https://github.com/astral-sh/python-build-standalone/releases/download/20261026/cpython-3.12.16%2B20261026
case "$arch" in
  arm64) pbs_arch=aarch64; PBS_SHA256="fbf4afef53c2a6b72bb741bc06d5671a9dfaf87bd84e5aa73ac9b3d0d589f14e"; out=dist ;;
  x86_64) pbs_arch=x86_64; PBS_SHA256="a962e47df522889eaa7ff0d6a56203f1079f68aabb65ffdbe8455f362bc769f3"; out=dist/x86_64 ;;
  *) echo "architecture: arm64 or x86_64" >&2; exit 2 ;;
esac

mkdir -p dist/cache "$out"
tarball=dist/cache/python-$pbs_arch.tar.gz
[ -f "$tarball" ] || curl -fsSL -o "$tarball" "$PBS-$pbs_arch-apple-darwin-install_only.tar.gz"
echo "$PBS_SHA256  $tarball" | shasum -a 256 -c -

app="$out/Firmware Toolkit.app"
rm -rf "$app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources/app"
tar xzf "$tarball" -C "$app/Contents/Resources"
rsync -a --exclude __pycache__ --exclude diagsim.js u2c_customfw "$app/Contents/Resources/app/"
cp DISCLAIMER.md LICENSE "$app/Contents/Resources/app/"
cp macos/AppIcon.icns "$app/Contents/Resources/"  # rendered from macos/icon.svg
sed "s/@VERSION@/$version/g" macos/Info.plist > "$app/Contents/Info.plist"
swiftc -O -target "$arch-apple-macos13.0" -o "$app/Contents/MacOS/u2c-customfw" macos/main.swift macos/Diagnostics.swift -framework AppKit -framework WebKit -framework IOKit -framework GameController -framework CoreHaptics
codesign --force --deep -s - "$app"
zip="firmware-toolkit-$version-macos-$arch.zip"
(cd "$out" && rm -f "$root/dist/$zip" && ditto -c -k --keepParent "Firmware Toolkit.app" "$root/dist/$zip")
ls -lh "dist/$zip"
