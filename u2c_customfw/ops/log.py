# SPDX-License-Identifier: GPL-3.0-or-later
import logging
from pathlib import Path


def get_logger(store: Path | None = None) -> logging.Logger:
    log = logging.getLogger("u2c_customfw")
    log.setLevel(logging.INFO)
    if store is not None and not any(isinstance(h, logging.FileHandler) for h in log.handlers):
        store.mkdir(parents=True, exist_ok=True)
        h = logging.FileHandler(store / "u2c-customfw.log")
        h.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        log.addHandler(h)
    return log
