"""Поиск по заметкам (services/search.py).

Проверяем главным образом то, что легко сделать неправильно: поиск должен
идти по ЧИТАЕМОМУ тексту, а не по HTML-разметке редактора, и специальные
символы в запросе не должны ломать поиск.
"""
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from models.note import Note
from services import search


def note(note_id, content):
    return Note(id=note_id, content=content)


class PlainTextTests(unittest.TestCase):
    def test_short_text_without_markup_returned_as_is(self):
        self.assertEqual(search.plain_text("просто текст"), "просто текст")

    def test_html_is_stripped(self):
        text = search.plain_text("<p>первая</p><p>вторая</p>")
        self.assertIn("первая", text)
        self.assertIn("вторая", text)
        self.assertNotIn("<p>", text)

    def test_empty_is_empty(self):
        self.assertEqual(search.plain_text(""), "")
        self.assertEqual(search.plain_text(None), "")

    def test_service_attributes_do_not_leak_into_search(self):
        """Иначе поиск «font» находил бы служебные атрибуты Qt у всех заметок."""
        html = (
            '<p style="font-family:Segoe UI; font-size:18pt;">привет</p>'
        )
        text = search.plain_text(html)
        self.assertNotIn("font-family", text)
        self.assertNotIn("Segoe UI", text)
        self.assertIn("привет", text)


class CompileQueryTests(unittest.TestCase):
    def test_empty_query_is_none(self):
        self.assertIsNone(search.compile_query(""))
        self.assertIsNone(search.compile_query("   "))
        self.assertIsNone(search.compile_query(None))

    def test_special_characters_are_literal_by_default(self):
        """«(черновик)» — это текст со скобками, а не группа."""
        pattern = search.compile_query("(черновик)")
        self.assertIsNotNone(pattern.search("пункт (черновик) на завтра"))
        self.assertIsNone(pattern.search("черновик без скобок"))

    def test_asterisk_is_literal_by_default(self):
        pattern = search.compile_query("*важно*")
        self.assertIsNotNone(pattern.search("список *важно* тут"))

    def test_regex_mode_treats_query_as_pattern(self):
        pattern = search.compile_query("черновик\\w*", regex=True)
        self.assertIsNotNone(pattern.search("черновики и черновик"))

    def test_regex_mode_reports_broken_pattern(self):
        with self.assertRaises(search.SearchError):
            search.compile_query("[не закрытая скобка", regex=True)

    def test_case_insensitive(self):
        pattern = search.compile_query("ВажНо")
        self.assertIsNotNone(pattern.search("это ВАЖНО и важно"))


class FindSpansTests(unittest.TestCase):
    def test_finds_all_occurrences(self):
        pattern = search.compile_query("бег")
        spans = search.find_matched_spans("бег бегом бег", pattern)
        self.assertEqual(len(spans), 3)
        for start, end in spans:
            self.assertEqual(end - start, 3)

    def test_no_matches_is_empty_list(self):
        pattern = search.compile_query("неттакого")
        self.assertEqual(search.find_matched_spans("тут ничего", pattern), [])

    def test_zero_length_matches_dropped(self):
        """`.*?` совпадает с пустой строкой на каждой позиции — это залило бы
        весь текст подсветкой."""
        pattern = search.compile_query("a*")
        spans = search.find_matched_spans("бвгд", pattern)
        self.assertEqual(spans, [])

    def test_overlong_match_dropped(self):
        pattern = search.compile_query(".*", regex=True)
        self.assertEqual(
            search.find_matched_spans("x" * (search.MAX_HIGHLIGHT_LENGTH + 5), pattern),
            [],
        )

    def test_spans_point_at_the_right_text(self):
        pattern = search.compile_query("иголка")
        text = "в стоге сена иголка лежит"
        (start, end) = search.find_matched_spans(text, pattern)[0]
        self.assertEqual(text[start:end], "иголка")


class SnippetTests(unittest.TestCase):
    def test_short_text_returned_whole(self):
        pattern = search.compile_query("кот")
        text = "кот спит"
        spans = search.find_matched_spans(text, pattern)
        self.assertEqual(search.snippet(text, spans), "кот спит")

    def test_long_text_is_trimmed_around_match(self):
        pattern = search.compile_query("иголка")
        text = "начало " * 40 + "иголка" + " конец" * 40
        spans = search.find_matched_spans(text, pattern)
        result = search.snippet(text, spans)
        self.assertIn("иголка", result)
        self.assertLess(len(result), len(text))
        self.assertTrue(result.startswith("…"))
        self.assertTrue(result.endswith("…"))

    def test_newlines_collapsed(self):
        text = "первая\n\nвторая\tтретья"
        self.assertNotIn("\n", search.snippet(text, []))

    def test_no_spans_returns_text(self):
        self.assertEqual(search.snippet("просто текст", []), "просто текст")


class MatchNotesTests(unittest.TestCase):
    def test_finds_note_by_text(self):
        notes = [
            note(1, "купить хлеб"),
            note(2, "позвонить маме"),
            note(3, "хлеб и молоко"),
        ]
        results = search.match_notes(notes, "хлеб")
        self.assertEqual([r["id"] for r in results], [1, 3])

    def test_search_ignores_markup(self):
        """Заметка с HTML должна находиться по слову текста, а не разметки."""
        notes = [
            note(1, '<p style="font-size:18pt;">молоко</p>'),
            note(2, "<p>хлеб</p>"),
        ]
        results = search.match_notes(notes, "молоко")
        self.assertEqual([r["id"] for r in results], [1])
        self.assertEqual(search.match_notes(notes, "font-size"), [])

    def test_result_carries_count_and_snippet(self):
        results = search.match_notes([note(1, "бег бегом бег")], "бег")
        self.assertEqual(results[0]["count"], 3)
        self.assertIn("бег", results[0]["snippet"])

    def test_empty_query_matches_nothing(self):
        notes = [note(1, "что угодно")]
        self.assertEqual(search.match_notes(notes, ""), [])
        self.assertEqual(search.match_notes(notes, "   "), [])

    def test_no_matches_returns_empty(self):
        self.assertEqual(search.match_notes([note(1, "текст")], "другое"), [])

    def test_order_follows_input(self):
        notes = [note(3, "слово"), note(1, "слово"), note(2, "слово")]
        self.assertEqual([r["id"] for r in search.match_notes(notes, "слово")], [3, 1, 2])

    def test_regex_mode(self):
        notes = [note(1, "телефон 123-456"), note(2, "телефон без номера")]
        results = search.match_notes(notes, "\\d{3}-\\d{3}", regex=True)
        self.assertEqual([r["id"] for r in results], [1])

    def test_broken_regex_raises(self):
        with self.assertRaises(search.SearchError):
            search.match_notes([note(1, "текст")], "[битое", regex=True)

    def test_note_without_content_skipped(self):
        results = search.match_notes([note(1, ""), note(2, None)], "хоть что")
        self.assertEqual(results, [])

    def test_cyrillic_and_case(self):
        results = search.match_notes([note(1, "Привет Мир")], "привет")
        self.assertEqual([r["id"] for r in results], [1])


class IsActiveTests(unittest.TestCase):
    def test_blank_queries_are_inactive(self):
        for query in ("", "   ", None, "\t\n"):
            self.assertFalse(search.is_active(query), repr(query))

    def test_real_query_is_active(self):
        self.assertTrue(search.is_active("слово"))


if __name__ == "__main__":
    unittest.main()
