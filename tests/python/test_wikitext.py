"""Tests for video2commons.shared.wikitext."""

import pytest

from video2commons.shared.wikitext import (
    normalize_categories,
    normalize_category_target,
)


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("Category:A", "Category:A"),
        (" category: a ", "Category:a"),
        ("CATEGORY : b_c", "Category:b c"),
        ("Category_:__Foo___bar_", "Category:Foo bar"),
        ("Category:A#Section", "Category:A#Section"),
        # Percent-encoded names, e.g. copied from a URL.
        ("Category:Caf%C3%A9_au_lait", "Category:Café au lait"),
        ("Category:100% cotton", "Category:100% cotton"),
        # Invalid UTF-8 or characters that would break the wikitext.
        ("Category:Caf%E9", "Category:Caf%E9"),
        ("Category:A%5D%5D", "Category:A%5D%5D"),
        ("Category:A%7Cb", "Category:A%7Cb"),
    ],
)
def test_normalize_category_target(target, expected):
    assert normalize_category_target(target) == expected


@pytest.mark.parametrize(
    "target",
    [
        "Foo",
        "File:Category:A.jpg",
        ":Category:A",
        " :category:a",
        "Category:",
        "Category: _",
    ],
)
def test_normalize_category_target_not_a_category(target):
    assert normalize_category_target(target) is None


@pytest.mark.parametrize(
    ("wikitext", "expected"),
    [
        # The example from the issue.
        (
            "[[ category: a ]] [[ category: b_c]]",
            "[[Category:a]]\n[[Category:b c]]",
        ),
        ("", ""),
        ("No categories here.", "No categories here."),
        # Already clean wikitext is left untouched.
        (
            "Text\n\n[[Category:A]]\n[[Category:B]]\n",
            "Text\n\n[[Category:A]]\n[[Category:B]]\n",
        ),
        ("[[Category:A]]\r\n[[Category:B]]", "[[Category:A]]\r\n[[Category:B]]"),
        # Sort keys are kept as is.
        ("[[category:A_b| key ]]", "[[Category:A b| key ]]"),
        # Categories are moved out of a line of text.
        ("Text [[Category:A]] more text", "Text\n[[Category:A]]\nmore text"),
        # Whitespace around a category is removed.
        ("  [[Category:A]]  \n\t[[Category:B]]\t", "[[Category:A]]\n[[Category:B]]"),
        # Links to categories and other links are left untouched.
        (
            "[[:category:a_b]] [[Foo_bar]] [[File:A_b.jpg]]",
            "[[:category:a_b]] [[Foo_bar]] [[File:A_b.jpg]]",
        ),
        ("[[Category:]] [[Category:A]]", "[[Category:]]\n[[Category:A]]"),
        # Nested categories are normalized but stay where they are.
        (
            "{{Information\n|description=Foo [[category:a_b]] bar\n}}",
            "{{Information\n|description=Foo [[Category:a b]] bar\n}}",
        ),
        (
            "[[File:A.jpg|thumb|[[category:b_c]]]] text",
            "[[File:A.jpg|thumb|[[Category:b c]]]] text",
        ),
        (
            "<gallery>\nA.jpg|[[category:b]]\n</gallery>",
            "<gallery>\nA.jpg|[[Category:b]]\n</gallery>",
        ),
        # Categories in comments and nowiki tags are not real categories.
        ("<!-- [[category: a]] -->", "<!-- [[category: a]] -->"),
        ("<nowiki>[[category: a]]</nowiki>", "<nowiki>[[category: a]]</nowiki>"),
    ],
)
def test_normalize_categories(wikitext, expected):
    assert normalize_categories(wikitext) == expected


def test_normalize_categories_is_idempotent():
    wikitext = "Text [[ category: a ]] [[ category: b_c|key]] {{T|[[category:d]]}}"
    once = normalize_categories(wikitext)

    assert normalize_categories(once) == once
