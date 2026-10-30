# SPDX-License-Identifier: GPL-3.0-or-later
"""The controller's two protocols: normal-mode update-channel reads (app) and the bootloader (boot)."""


class ProtocolError(Exception):
    pass
