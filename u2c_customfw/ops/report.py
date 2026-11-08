# SPDX-License-Identifier: GPL-3.0-or-later
"""A text report for bug reports. Device IDs, mode, firmware state and the log tail: never the MAC, the Bluetooth
bonds or any backup data."""
import platform
from pathlib import Path

from .. import __version__
from . import shown


def log_tail(store, n: int = 30) -> str:
    """The last n lines of the app's log, or an empty string if there is none yet."""
    log = Path(store) / "u2c-customfw.log"
    return "\n".join(log.read_text().splitlines()[-n:]) if log.exists() else ""


def clean_extras(raw) -> dict:
    """What the page may add to the report: only these fields, of these types, limited in length."""
    if not isinstance(raw, dict):
        return {}
    out, macos, seen = {}, {}, raw.get("macos")
    if isinstance(seen, dict):
        for key in ("name", "category"):
            if isinstance(seen.get(key), str):
                macos[key] = seen[key][:80]
        if isinstance(seen.get("localities"), list):
            macos["localities"] = [x[:40] for x in seen["localities"] if isinstance(x, str)][:8]
    if macos:
        out["macos"] = macos
    if isinstance(raw.get("boot_identity"), int) and not isinstance(raw["boot_identity"], bool):
        out["boot_identity"] = raw["boot_identity"]
    if isinstance(raw.get("firmware"), str):
        out["firmware"] = raw["firmware"][:120]
    if isinstance(raw.get("pending"), bool):
        out["pending"] = raw["pending"]
    return out


def report(found, state, log_tail: str, extras: dict | None = None) -> str:
    lines = [f"Firmware Toolkit {__version__}", f"python {platform.python_version()} on {platform.platform()}", "", "Devices:"]
    for f in found:
        i = f.info
        lines.append(f"  {f.mode}: {i.vendor:04x}:{i.product:04x} page {i.usage_page:#06x} via {i.transport}  {i.name!r}")
    if not found:
        lines.append("  none found")
    extras = extras or {}
    if state is None:
        lines.append(f"Firmware: {extras.get('firmware', 'not read')}")
    elif state.known:
        keys = shown(state.recipes)
        lines.append("Firmware: original 1.09" + (f" with tweaks: {', '.join(keys)}" if keys else ""))
    else:
        lines.append("Firmware: unknown (not the original 1.09, with or without the tweaks)")
    if "macos" in extras:
        m = extras["macos"]
        category = f" ({m['category']})" if m.get("category") else ""
        vibration = f", vibration: {', '.join(m['localities'])}" if m.get("localities") else ""
        lines.append(f"macOS sees: {m.get('name', 'a controller')}{category}{vibration}")
    if "boot_identity" in extras:
        lines.append(f"Update-mode identity: {extras['boot_identity']:#06x}")
    if "pending" in extras:
        lines.append(f"Pending update: {'yes' if extras['pending'] else 'no'}")
    lines += ["", "Last log lines:", log_tail.strip() or "  (empty)"]
    return "\n".join(lines) + "\n"
