# SPDX-License-Identifier: GPL-3.0-or-later
"""A text report for bug reports. Device IDs, mode, firmware state and the log tail: never the MAC, the Bluetooth
bonds or any backup data."""
import platform

from .. import __version__


def report(found, state, log_tail: str) -> str:
    lines = [f"u2c-customfw {__version__}", f"python {platform.python_version()} on {platform.platform()}", "", "Devices:"]
    for f in found:
        i = f.info
        lines.append(f"  {f.mode}: {i.vendor:04x}:{i.product:04x} page {i.usage_page:#06x} via {i.transport}  {i.name!r}")
    if not found:
        lines.append("  none found")
    if state is None:
        lines.append("Firmware: not read")
    elif state.known:
        lines.append("Firmware: stock v1.09" + (f" plus {', '.join(state.recipes)}" if state.recipes else ""))
    else:
        lines.append("Firmware: unknown (not stock v1.09 or one of ours)")
    lines += ["", "Last log lines:", log_tail.strip() or "  (empty)"]
    return "\n".join(lines) + "\n"
