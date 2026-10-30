# SPDX-License-Identifier: GPL-3.0-or-later
import hashlib
import io
import json
import unittest
from unittest import mock

from u2c_customfw import fetch
from u2c_customfw.firmware import image


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener(listing, dat, fail=None):
    def op(req, timeout=None):
        if fail:
            raise fail
        url = req.full_url if hasattr(req, "full_url") else req
        return Resp(listing if url.endswith("/firmware/select") else dat)
    return op


DAT = bytes(0x1C) + bytes(range(256)) * 4
LIST = json.dumps({"list": [{"version": 1.06, "filePathName": "/old.dat"}, {"version": 1.09, "filePathName": "/new.dat"}]}).encode()


class FetchTest(unittest.TestCase):
    def patched(self, dat=DAT):
        return mock.patch.object(image, "STOCK_DAT_SHA256", hashlib.sha256(dat).hexdigest())

    def test_returns_bank_a_of_the_checked_dat(self):
        with self.patched():
            self.assertEqual(fetch.fetch_stock(opener(LIST, DAT)), DAT[0x1C:])

    def test_version_missing(self):
        with self.patched(), self.assertRaises(fetch.FetchError) as e:
            fetch.fetch_stock(opener(json.dumps({"list": [{"version": 1.06, "filePathName": "/x"}]}).encode(), DAT))
        self.assertIn("1.09", str(e.exception))

    def test_not_json(self):
        with self.patched(), self.assertRaises(fetch.FetchError):
            fetch.fetch_stock(opener(b"<html>error</html>", DAT))

    def test_wrong_hash(self):
        with self.patched(), self.assertRaises(fetch.FetchError) as e:
            fetch.fetch_stock(opener(LIST, DAT + b"x"))
        self.assertIn("checksum", str(e.exception))

    def test_network_error(self):
        with self.assertRaises(fetch.FetchError) as e:
            fetch.fetch_stock(opener(LIST, DAT, fail=OSError("unreachable")))
        self.assertIn("unreachable", str(e.exception))


if __name__ == "__main__":
    unittest.main()
