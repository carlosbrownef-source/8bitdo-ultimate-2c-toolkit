# SPDX-License-Identifier: GPL-3.0-or-later
import os
import sys
from pathlib import Path

from .. import state
from .server import serve

store = Path(sys.argv[1]) if len(sys.argv) > 1 else state.default_store()
if os.environ.get("U2C_SIM"):
    from .. import sim
    sim.install(store, unknown=os.environ["U2C_SIM"] == "unknown")
serve(store)
