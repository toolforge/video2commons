# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>

"""Helper functions for cleaning up user-provided wikitext."""

import re
from urllib.parse import unquote

import wikitextparser

CATEGORY_TARGET_RE = re.compile(r"category\s*:\s*(.+)", re.IGNORECASE)

# Characters that can't appear in a page title. If percent-decoding a target
# yields one of them, the decoded target would break the surrounding wikitext.
INVALID_TITLE_CHARS = set("[]{}|<>")


def normalize_category_target(target: str) -> str | None:
    """Normalize the target of a category link, e.g. ' category: a_b '.

    Returns 'Category:a b', or None if the target isn't a category.
    """
    # Category names copied from a URL are percent-encoded.
    try:
        decoded = unquote(target, errors="strict")
    except UnicodeDecodeError:
        decoded = target

    if not INVALID_TITLE_CHARS.intersection(decoded):
        target = decoded

    # MediaWiki treats underscores as spaces and collapses runs of them.
    target = " ".join(target.replace("_", " ").split())

    # A target with a leading colon, e.g. '[[:Category:A]]', is a link to the
    # category rather than a categorization, so it doesn't match here.
    match = CATEGORY_TARGET_RE.fullmatch(target)
    if not match:
        return None

    return f"Category:{match.group(1)}"


def normalize_categories(wikitext: str) -> str:
    """Clean up the category links of a file description.

    The namespace is normalized to 'Category', underscores are replaced with
    spaces, extra whitespace is removed and each category that isn't nested in
    a template, a tag or another link is moved to its own line.
    """
    parsed = wikitextparser.parse(wikitext)
    toplevel_categories = []

    for wikilink in parsed.wikilinks:
        target = normalize_category_target(wikilink.target)
        if target is None:
            continue

        wikilink.target = target
        if not wikilink.ancestors():
            toplevel_categories.append(wikilink)

    text = parsed.string
    result = ""
    pos = 0

    for wikilink in toplevel_categories:
        start, end = wikilink.span
        result += text[pos:start]

        # Start a new line, unless the category already starts one. Whitespace
        # before it is removed, since a line starting with a space is
        # preformatted text.
        line_start = result.rfind("\n") + 1
        if result[line_start:].strip(" \t"):
            result = result.rstrip(" \t") + "\n"
        else:
            result = result[:line_start]

        result += text[start:end]

        # Whitespace after the category is removed too, and anything that
        # follows it on the same line is moved to the next line.
        pos = end
        while pos < len(text) and text[pos] in " \t":
            pos += 1
        if pos < len(text) and text[pos] not in "\r\n":
            result += "\n"

    return result + text[pos:]
