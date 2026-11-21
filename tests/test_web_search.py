from __future__ import annotations

import unittest
from types import SimpleNamespace

from tg_gpt_bot.web_search import (
    contains_web_search_trigger,
    search_citations,
    search_query_from_text,
)


class WebSearchTests(unittest.TestCase):
    def test_search_query_accepts_command_with_bot_username(self) -> None:
        self.assertEqual(search_query_from_text("/search@helper_bot latest Python release"), "latest Python release")

    def test_search_query_returns_none_for_regular_message(self) -> None:
        self.assertIsNone(search_query_from_text("search this"))

    def test_russian_search_triggers(self) -> None:
        for prompt in (
            "Погугли, когда вышел Python 3.14",
            "Загуглите последние новости",
            "Поищи в интернете документацию",
            "Найди в сети расписание",
        ):
            with self.subTest(prompt=prompt):
                self.assertTrue(contains_web_search_trigger(prompt))

    def test_english_search_triggers(self) -> None:
        for prompt in (
            "Google it: current exchange rate",
            "Search the web for current docs",
            "Look it up",
            "Find this online",
        ):
            with self.subTest(prompt=prompt):
                self.assertTrue(contains_web_search_trigger(prompt))

    def test_unrelated_text_does_not_trigger_search(self) -> None:
        self.assertFalse(contains_web_search_trigger("I use Google Docs every day"))

    def test_citations_extract_and_deduplicate_source_urls(self) -> None:
        response = SimpleNamespace(
            output=[
                SimpleNamespace(
                    content=[
                        SimpleNamespace(
                            annotations=[
                                SimpleNamespace(
                                    type="url_citation",
                                    url="https://example.com",
                                    title="Example",
                                ),
                                SimpleNamespace(
                                    type="url_citation",
                                    url="https://example.com",
                                    title="Duplicate",
                                ),
                            ]
                        )
                    ]
                )
            ]
        )

        self.assertEqual(search_citations(response), [("Example", "https://example.com")])


if __name__ == "__main__":
    unittest.main()
