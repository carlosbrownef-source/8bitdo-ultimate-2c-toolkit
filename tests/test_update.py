# SPDX-License-Identifier: GPL-3.0-or-later
import unittest

from u2c_customfw import update


def answer(tag):
    return lambda: {"tag_name": tag, "html_url": "https://example.com/elsewhere"}


class UpdateTest(unittest.TestCase):
    def test_a_newer_release_is_offered_with_a_link_built_here(self):
        self.assertEqual(update.newer("1.0.1", answer("v1.0.2")),
                         {"version": "1.0.2", "url": "https://github.com/carlosbrownef-source/8bitdo-ultimate-2c-toolkit/releases/tag/v1.0.2"})

    def test_the_same_or_an_older_release_is_not(self):
        for current, tag in (("1.0.2", "v1.0.2"), ("1.0.2", "v1.0.1"), ("1.0.2b1", "v1.0.1"), ("1.0.10", "v1.0.9")):
            self.assertIsNone(update.newer(current, answer(tag)), (current, tag))

    def test_a_beta_is_older_than_its_release(self):
        self.assertEqual(update.newer("1.0.2b1", answer("v1.0.2"))["version"], "1.0.2")
        self.assertLess(update.key("v1.0.2-beta.1"), update.key("1.0.2"))
        self.assertEqual(update.key("v1.0.2-beta.1"), update.key("1.0.2b1"))

    def test_no_answer_or_an_odd_one_offers_nothing(self):
        def offline():
            raise OSError("no network")
        for latest in (offline, lambda: {}, lambda: {"tag_name": None}, answer("nightly"), answer("v2.0.0/../../x")):
            self.assertIsNone(update.newer("1.0.1", latest))


if __name__ == "__main__":
    unittest.main()
