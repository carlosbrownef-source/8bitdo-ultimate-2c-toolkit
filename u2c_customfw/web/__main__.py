# SPDX-License-Identifier: GPL-3.0-or-later
import os
import sys
import tempfile
from pathlib import Path

from .. import state
from .server import serve

if len(sys.argv) > 1:
    store = Path(sys.argv[1])
else:  # the simulation's fake backup never goes into the real store
    store = Path(tempfile.mkdtemp(prefix="u2c-sim-")) if os.environ.get("U2C_SIM") else state.default_store()
if os.environ.get("U2C_SIM"):
    from .. import sim
    sim.install(store, unknown=os.environ["U2C_SIM"] == "unknown")
serve(store)
