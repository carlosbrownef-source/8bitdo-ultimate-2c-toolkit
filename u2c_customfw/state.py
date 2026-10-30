# SPDX-License-Identifier: GPL-3.0-or-later
"""Per-user state: where things live, and whether the disclaimer has been accepted."""
import sys
from pathlib import Path


def default_store() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "u2c-customfw"
    return Path.home() / ".local" / "share" / "u2c-customfw"


def accepted(store: Path) -> bool:
    return (Path(store) / "disclaimer-accepted").exists()


def accept(store: Path) -> None:
    Path(store).mkdir(parents=True, exist_ok=True)
    (Path(store) / "disclaimer-accepted").write_text("accepted\n")
