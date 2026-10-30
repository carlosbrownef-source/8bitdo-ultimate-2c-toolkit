# SPDX-License-Identifier: GPL-3.0-or-later
"""Download 8BitDo's controller firmware v1.09 from its update server, accepted only if its SHA-256 is the known one."""
import hashlib
import json
import urllib.request

from .firmware import image

BASE = "http://dl.8bitdo.com:8080"
TYPE_ULTIMATE_2C = "75"


class FetchError(Exception):
    pass


def fetch_stock(opener=urllib.request.urlopen) -> bytes:
    """Bank A (the .dat without its 0x1C-byte header) of v1.09."""
    try:
        req = urllib.request.Request(BASE + "/firmware/select", data=b"", method="POST",
                                     headers={"Beta": "1", "Type": TYPE_ULTIMATE_2C})
        with opener(req, timeout=15) as r:
            entries = json.loads(r.read()).get("list") or []
        entry = next((e for e in entries if round(float(e.get("version", 0)), 2) == 1.09), None)
        if entry is None:
            raise FetchError("8BitDo's server does not list firmware 1.09 for the Ultimate 2C")
        with opener(BASE + entry["filePathName"], timeout=60) as r:
            dat = r.read()
    except FetchError:
        raise
    except (OSError, ValueError, KeyError, AttributeError, TypeError) as e:
        raise FetchError(f"could not download the firmware: {e}") from e
    if hashlib.sha256(dat).hexdigest() != image.STOCK_DAT_SHA256:
        raise FetchError("the downloaded file's checksum is not v1.09's: it was not used")
    return dat[0x1C:]
