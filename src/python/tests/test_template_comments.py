"""Django's ``{# ... #}`` comment is single-line only.

One that spans lines is not a comment: Django renders it as text, so the
explanation meant for the next reader shows up on the page instead (it did, on
the change set instance card). A multi-line note needs
``{% comment %}...{% endcomment %}``.
"""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
OPENER = re.compile(r"\{#")


def _unclosed_comments():
    found = []
    for path in sorted(SRC.rglob("*.html")):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            for match in OPENER.finditer(line):
                if "#}" not in line[match.end() :]:
                    found.append(f"{path.relative_to(SRC)}:{number}")
    return found


def test_no_template_comment_spans_lines():
    assert _unclosed_comments() == []
