# SPDX-License-Identifier: GPL-3.0-or-later
import logging
import os
from pathlib import Path


def get_logger(store: Path | None = None) -> logging.Logger:
    """The app's log, writing to the store given (the last one given, if a process uses several)."""
    log = logging.getLogger("u2c_customfw")
    log.setLevel(logging.INFO)
    if store is not None:
        path = os.path.abspath(Path(store) / "u2c-customfw.log")
        files = [h for h in log.handlers if isinstance(h, logging.FileHandler)]
        if not any(h.baseFilename == path for h in files):
            for h in files:
                log.removeHandler(h)
                h.close()
            Path(store).mkdir(parents=True, exist_ok=True)
            h = logging.FileHandler(path)
            h.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
            log.addHandler(h)
    return log
