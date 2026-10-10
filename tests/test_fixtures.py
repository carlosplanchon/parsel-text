"""Behaviour of parsel_text on production-like HTML fixtures."""

from conftest import deep_nested_html, load_fixture, search_results_html
from parsel import Selector

from parsel_text import get_results_row_text, get_xpath_text


def sel(html):
    return Selector(text=html)


# --------------------------------------------------------------------------- #
# 1. News article: script/style/comments/noscript excluded even in-scope.
# --------------------------------------------------------------------------- #
class TestNews:
    def _out(self):
        return get_xpath_text(parsel_sel=sel(load_fixture("news.html")), xpath="//article")

    def test_body_text_present(self):
        out = self._out()
        assert "Banco Central" in out
        assert "Juan Pérez" in out

    def test_inline_script_style_comment_excluded(self):
        out = self._out()
        for marker in ("SCRIPT_INLINE_MARKER", "STYLE_INLINE_MARKER", "COMMENT_INLINE_MARKER"):
            assert marker not in out

    def test_noscript_excluded(self):
        assert "NOSCRIPT_MARKER" not in self._out()


# --------------------------------------------------------------------------- #
# 2. Product page: <template> and JSON-LD excluded.
# --------------------------------------------------------------------------- #
class TestProduct:
    def _out(self):
        return get_xpath_text(parsel_sel=sel(load_fixture("product.html")), xpath="//main")

    def test_specs_present(self):
        out = self._out()
        assert "RAM" in out and "16" in out and "núcleos" in out

    def test_inert_template_excluded(self):
        assert "TEMPLATE_MARKER" not in self._out()

    def test_mojibake_review_fixed(self):
        # "TrÃ¨s" -> "Très" when fix_mojibake is on (default).
        assert "Très" in self._out()


# --------------------------------------------------------------------------- #
# 3. Data table: //table matches both tables, the nested one's text appears once.
# --------------------------------------------------------------------------- #
class TestDataTable:
    def _out(self):
        return get_xpath_text(parsel_sel=sel(load_fixture("data_table.html")), xpath="//table")

    def test_cells_present(self):
        out = self._out()
        assert "ACME" in out and "1.234.567" in out

    def test_nested_table_not_duplicated(self):
        out = self._out()
        assert out.count("Sub A") == 1
        assert out.count("Sub B") == 1


# --------------------------------------------------------------------------- #
# 4. Messy / broken HTML: no crash; conditional comment & script excluded.
# --------------------------------------------------------------------------- #
class TestMessy:
    def _out(self):
        return get_xpath_text(parsel_sel=sel(load_fixture("messy.html")), xpath="//body")

    def test_does_not_crash_and_extracts(self):
        out = self._out()
        assert "item 1" in out and "celda A" in out

    def test_conditional_comment_and_script_excluded(self):
        out = self._out()
        assert "CONDITIONAL_COMMENT_MARKER" not in out
        assert "SCRIPT_COMMENT_MARKER" not in out

    def test_entities_decoded(self):
        assert "Empresa & Cía." in self._out()


# --------------------------------------------------------------------------- #
# 5. Encoding hell: mojibake fixed, scripts of the world preserved.
# --------------------------------------------------------------------------- #
class TestEncoding:
    def test_mojibake_fixed_default(self):
        out = get_xpath_text(parsel_sel=sel(load_fixture("encoding.html")), xpath="//body")
        assert "Añoración" in out and "garçon" in out and "Grün" in out

    def test_fix_toggle_changes_output(self):
        html = load_fixture("encoding.html")
        on = get_xpath_text(parsel_sel=sel(html), xpath="//body", fix_mojibake=True)
        off = get_xpath_text(parsel_sel=sel(html), xpath="//body", fix_mojibake=False)
        assert on != off

    def test_cjk_and_rtl_preserved(self):
        out = get_xpath_text(parsel_sel=sel(load_fixture("encoding.html")), xpath="//body")
        assert "日本語" in out
        assert "مرحبا" in out


# --------------------------------------------------------------------------- #
# 6. Whitespace: kept inside <pre>/<code>, collapsed elsewhere.
# --------------------------------------------------------------------------- #
class TestWhitespace:
    def test_pre_code_whitespace_preserved(self):
        out = get_xpath_text(parsel_sel=sel(load_fixture("whitespace.html")), xpath="//code")
        assert "def fibonacci(n):\n    if n < 2:\n        return n" in out

    def test_normal_paragraph_still_collapsed(self):
        out = get_xpath_text(parsel_sel=sel(load_fixture("whitespace.html")), xpath="//p")
        assert out == "Un párrafo normal con muchos espacios."


# --------------------------------------------------------------------------- #
# 7. Inline SVG: <text>/<title>/<desc> are all included.
# --------------------------------------------------------------------------- #
class TestSvg:
    def test_svg_text_metadata_included(self):
        out = get_xpath_text(parsel_sel=sel(load_fixture("svg.html")), xpath="//body")
        assert "SVG_TEXT_MARKER" in out
        assert "SVG_TITLE_MARKER" in out
        assert "SVG_DESC_MARKER" in out


# --------------------------------------------------------------------------- #
# 8. Search results at scale: row API keeps count and order.
# --------------------------------------------------------------------------- #
class TestSearchScale:
    def test_rows_count_and_order(self):
        rows = get_results_row_text(
            parsel_sel=sel(search_results_html(1000)),
            xpath="//div[@class='result-card']",
        )
        assert len(rows) == 1000
        assert "Resultado número 0" in rows[0]
        assert "Resultado número 999" in rows[-1]


# --------------------------------------------------------------------------- #
# 9. Deep DOM: no crash past the recursion limit.
# --------------------------------------------------------------------------- #
class TestDeepDom:
    def test_shallow_ok(self):
        out = get_xpath_text(parsel_sel=sel(deep_nested_html(500)), xpath="//body")
        assert "DEEP_LEAF" in out

    def test_deep_extracts_without_crashing(self):
        out = get_xpath_text(parsel_sel=sel(deep_nested_html(1500)), xpath="//body")
        assert out == "DEEP_LEAF"
