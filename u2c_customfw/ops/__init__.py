# SPDX-License-Identifier: GPL-3.0-or-later
"""User-level operations: find devices, back up, patch, restore, report."""

# Recipes kept in the code but never offered or shown by the app: still recognised, but out of every list and summary.
HIDDEN_TWEAKS = frozenset({"ble_interval"})


def shown(keys) -> list:
    return [k for k in keys if k not in HIDDEN_TWEAKS]
