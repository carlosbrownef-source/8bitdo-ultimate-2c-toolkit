# SPDX-License-Identifier: GPL-3.0-or-later
import faulthandler
import os
import sys
import tempfile
from pathlib import Path

from .. import state
from .server import serve

faulthandler.enable()   # a crash in native code (IOKit through ctypes) still leaves a Python traceback in the app's message
if len(sys.argv) > 1:
    store = Path(sys.argv[1])
else:  # the simulation's fake backup never goes into the real store
    store = Path(tempfile.mkdtemp(prefix="u2c-sim-")) if os.environ.get("U2C_SIM") else state.default_store()
if os.environ.get("U2C_SIM"):
    from .. import sim
    sim.install(store, unknown=os.environ["U2C_SIM"] == "unknown")
    state.accept(store)   # a temporary store: no disclaimer for the simulation
serve(store)
