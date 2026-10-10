"""Shared helpers and constants for the parsel_text test-suite."""

from pathlib import Path

import bs4
from parsel import Selector

FIXTURES = Path(__file__).parent / "fixtures"


# Non-breaking space (U+00A0). Python's str.split() treats it as whitespace, so
# parsel_text collapses it away like any ordinary space.
NBSP = " "

# The exact document used in the README example.
README_HTML = (
    "<html><body><div id='content'>"
    "<p>Hello, world!</p>"
    "<p>Welcome to the parsel_text library.</p>"
    "</div></body></html>"
)


def sel(html: str) -> Selector:
    """Build a parsel Selector from an HTML string."""
    return Selector(text=html)


def soup(html: str) -> bs4.BeautifulSoup:
    """Build a BeautifulSoup (lxml) object from an HTML string."""
    return bs4.BeautifulSoup(html, features="lxml")


def mojibake(text: str) -> str:
    """Return a deterministic mojibake version of *text*.

    Simulates UTF-8 bytes wrongly decoded as latin-1, e.g.
    ``"café" -> "cafÃ©"`` -- exactly what ftfy.fix_encoding is meant to undo.
    """
    return text.encode("utf-8").decode("latin-1")


def load_fixture(name: str) -> str:
    """Read a production-like HTML fixture from tests/fixtures/."""
    return (FIXTURES / name).read_text(encoding="utf-8")


def search_results_html(n: int = 1000) -> str:
    """Build a search-results page with *n* repeated result cards.

    Kept as a generator (not a committed file) because the interesting variable
    is scale -- a 1000-card page is ~270 KB.
    """
    cards = [
        f'<div class="result-card">'
        f'<h3><a href="/item/{i}">Resultado número {i}</a></h3>'
        f'<p class="snippet">Este es el <em>fragmento</em> del resultado {i}, '
        f"con texto de relleno para simular un extracto real.</p>"
        f'<span class="meta">Precio: {i},99 · rating {i % 5 + 1}/5</span>'
        f"</div>"
        for i in range(n)
    ]
    return (
        "<!DOCTYPE html><html><body><main id='results'>"
        + "".join(cards)
        + "</main></body></html>"
    )


def deep_nested_html(depth: int, leaf: str = "DEEP_LEAF") -> str:
    """Build a pathologically deep DOM to probe recursion limits."""
    return (
        "<html><body>"
        + "<div>" * depth
        + leaf
        + "</div>" * depth
        + "</body></html>"
    )
