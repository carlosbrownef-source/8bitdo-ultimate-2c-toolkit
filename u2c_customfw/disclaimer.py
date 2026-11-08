# SPDX-License-Identifier: GPL-3.0-or-later
"""The disclaimer text: DISCLAIMER.md at the repository root, or the copy the macOS app bundles next to the package."""
from pathlib import Path

_HERE = Path(__file__).parent


def text() -> str:
    for p in (_HERE.parent / "DISCLAIMER.md", _HERE / "DISCLAIMER.md"):
        if p.exists():
            return p.read_text()
    return "No warranty. Installing modified firmware probably voids the controller's warranty. Ultimate 2C firmware 1.09 only."
