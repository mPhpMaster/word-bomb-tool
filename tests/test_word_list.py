import time
import unittest

from tests import helpers  # noqa: F401  (puts the project root on sys.path)
import word_list


class WordListTests(unittest.TestCase):
    def test_loads_the_whole_list(self):
        self.assertGreater(word_list.count(), 170_000)

    def test_contains_finds_words_shortest_first_without_the_prompt(self):
        words = word_list.search("HEA", "Contains")
        self.assertIn("head", words)
        self.assertIn("ahead", words)
        self.assertNotIn("hea", words)
        self.assertTrue(all("hea" in w for w in words))
        self.assertTrue(all(len(a) <= len(b) for a, b in zip(words, words[1:])))

    def test_starts_and_ends_with(self):
        starts = word_list.search("qu", "Starts With")
        self.assertTrue(starts)
        self.assertTrue(all(w.startswith("qu") for w in starts))
        ends = word_list.search("ing", "Ends With")
        self.assertTrue(ends)
        self.assertTrue(all(w.endswith("ing") for w in ends))

    def test_rhymes_are_not_answered_locally(self):
        self.assertFalse(word_list.supports("Rhymes"))
        self.assertFalse(word_list.supports("Related Words"))
        self.assertEqual([], word_list.search("cat", "Rhymes"))

    def test_fixes_capital_i_read_as_l(self):
        # A capital I read as l: "lzz" matches nothing, "lgh" only a few rare words.
        self.assertEqual("izz", word_list.fix_il_confusion("lzz", "Contains"))
        self.assertEqual("igh", word_list.fix_il_confusion("lgh", "Contains"))
        # Already-valid letters are left alone.
        self.assertEqual("ill", word_list.fix_il_confusion("ill", "Contains"))
        self.assertEqual("lli", word_list.fix_il_confusion("lli", "Contains"))
        self.assertEqual("li", word_list.fix_il_confusion("li", "Contains"))

    def test_arabic_prompts_search_the_arabic_list_most_common_first(self):
        self.assertGreater(word_list.arabic_count(), 50_000)
        words = word_list.search("يز", "Contains")  # "يز"
        self.assertTrue(words)
        self.assertTrue(all("يز" in w for w in words))
        self.assertNotIn("يز", words)
        self.assertTrue(all(word_list.is_arabic(w) for w in words))
        self.assertTrue(word_list.search("ال", "Starts With"))  # "ال"
        # No English words for Arabic letters, and no I/L swapping on them.
        self.assertEqual("يز", word_list.fix_il_confusion("يز", "Contains"))
        # Most common first: the list order is kept, not re-sorted by length.
        self.assertNotEqual(words, sorted(words, key=len))

    def test_search_returns_a_copy(self):
        a = word_list.search("hea", "Contains")
        a.clear()
        self.assertTrue(word_list.search("hea", "Contains"))

    def test_search_is_fast(self):
        word_list.count()
        start = time.perf_counter()
        for p in ("in", "er", "st", "an", "re"):
            word_list.search(p, "Contains")
        per = (time.perf_counter() - start) / 5 * 1000
        self.assertLess(per, 200, f"{per:.1f}ms per search")


if __name__ == "__main__":
    unittest.main()
