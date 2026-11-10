# SPDX-License-Identifier: GPL-3.0-or-later
"""Whether a newer version is out: one question to GitHub's API, which sends nothing but the request itself."""
import json
import re
import urllib.request

from . import __version__

REPO = "carlosbrownef-source/8bitdo-ultimate-2c-toolkit"
LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"   # never a prerelease or a draft
VERSION = re.compile(r"v?(\d+)\.(\d+)\.(\d+)(?:b(\d+)|-beta\.(\d+))?")


def key(version: str):
    """Sortable: 1.0.2b1 (as the app names itself) and v1.0.2-beta.1 (as its tag does) come before 1.0.2."""
    m = VERSION.fullmatch(version)
    if not m:
        return None
    major, minor, patch, b1, b2 = m.groups()
    beta = b1 or b2
    return int(major), int(minor), int(patch), beta is None, int(beta or 0)


def _latest() -> dict:
    req = urllib.request.Request(LATEST, headers={"User-Agent": "firmware-toolkit", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.load(r)


def newer(current: str = __version__, latest=_latest) -> dict | None:
    """The latest release, if it's newer than this one. Offline, rate-limited or anything unexpected: None."""
    try:
        tag = latest()["tag_name"]
    except Exception:
        return None
    if not isinstance(tag, str) or key(tag) is None or key(current) is None or key(tag) <= key(current):
        return None
    return {"version": tag.removeprefix("v"), "url": f"https://github.com/{REPO}/releases/tag/{tag}"}   # the link is built here, not taken from the answer
