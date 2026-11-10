"""The fixed set of Tailwind classes service partials may use (NERD007 SPEC006).

The stylesheet is precompiled and cannot see templates in other repos, so the
build sources css/partial-classes.txt, and hmd-base-service warns about any
class a partial uses outside it.
"""

import pathlib
import re

CSS_DIR = pathlib.Path(__file__).resolve().parent.parent / "css"


def partial_classes():
    lines = (CSS_DIR / "partial-classes.txt").read_text().splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def test_the_build_sources_the_class_list():
    source = (CSS_DIR / "app.src.css").read_text()
    assert '@source "./partial-classes.txt";' in source


def test_one_well_formed_class_per_line_without_duplicates():
    classes = partial_classes()
    assert len(classes) == len(set(classes))
    assert all(re.fullmatch(r"[a-z0-9:.\-]+", c) for c in classes), [
        c for c in classes if not re.fullmatch(r"[a-z0-9:.\-]+", c)
    ]


def test_the_services_own_denial_fragment_is_covered():
    # hmd-base-service renders a 403 fragment with these classes.
    assert {"rounded-md", "bg-red-50", "p-4", "text-sm", "text-red-700"} <= set(
        partial_classes()
    )
