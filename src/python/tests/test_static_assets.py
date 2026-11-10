"""The GUI must not compile CSS or fetch core scripts from a CDN at page load."""

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES = sorted(
    p
    for d in ("templates", "deployments/templates")
    for p in (ROOT / d).rglob("*.html")
)
BASE = ROOT / "deployments" / "templates" / "base.html"
STATIC = ROOT / "deployments" / "static" / "deployments"


@pytest.mark.parametrize(
    "host",
    [
        "cdn.tailwindcss.com",
        "unpkg.com",
        "cdn.jsdelivr.net",
        "googleapis.com",
        "gstatic.com",
    ],
)
def test_no_template_loads_from(host):
    offenders = [str(p) for p in TEMPLATES if host in p.read_text()]
    assert not offenders


def test_base_links_the_precompiled_stylesheet_and_local_htmx():
    html = BASE.read_text()
    assert "deployments/css/app.css" in html
    assert "deployments/js/vendor/htmx.min.js" in html
    assert "deployments/js/vendor/alpine.min.js" in html
    assert "deployments/css/fonts.css" in html
    assert "tailwind.config" not in html


def test_htmx_is_vendored_and_pinned():
    js = (STATIC / "js" / "vendor" / "htmx.min.js").read_text()
    assert js.startswith("var htmx=")
    assert 'version:"2.0.0"' in js


def test_theme_carries_the_brand_tokens_and_is_overridable():
    css = (ROOT / "css" / "app.src.css").read_text()
    assert "@theme {" in css and "@theme inline" not in css
    for token in (
        "--color-ns-navy",
        "--color-ns-magenta",
        "--font-heading",
        "--font-body",
    ):
        assert token in css


VENDORED = {
    "htmx.min.js": 'version:"2.0.0"',
    "dagre.min.js": "dagre",
    "cytoscape.min.js": "3.30.4",
    "cytoscape-dagre.js": "cytoscapeDagre",
    "alpine.min.js": "3.17.5",
}


@pytest.mark.parametrize("name,marker", sorted(VENDORED.items()))
def test_vendored_script_is_present_at_its_pinned_version(name, marker):
    assert marker in (STATIC / "js" / "vendor" / name).read_text()


def test_every_font_face_points_at_a_vendored_file():
    import re

    css = (STATIC / "css" / "fonts.css").read_text()
    urls = re.findall(r"url\(\.\./fonts/([^)]+)\)", css)
    assert urls and "http" not in css.split("*/", 1)[1]
    assert all((STATIC / "fonts" / u).is_file() for u in urls)
