"""guess_layout=True: text joined the way a browser lays it out."""

import pytest
from conftest import (
    deep_nested_html,
    load_fixture,
    mojibake,
    search_results_html,
    sel,
    soup,
)
from parsel import Selector

from parsel_text import get_bs4_soup_text, get_results_row_text, get_xpath_text


def layout(html: str, xpath: str = "//body", **kwargs) -> str:
    return get_xpath_text(parsel_sel=sel(html), xpath=xpath, guess_layout=True, **kwargs)


class TestInline:
    def test_inline_tags_keep_the_sentence_together(self):
        html = '<p><b>Total</b>: 42 (<a href="#">ver</a>).</p>'
        assert layout(html, "//p") == "Total: 42 (ver)."

    def test_original_spacing_is_respected(self):
        assert layout("<p>Hola<b>mundo</b> y <i>chau</i></p>", "//p") == "Holamundo y chau"

    def test_whitespace_between_inline_tags_is_one_space(self):
        assert layout("<p><b>Hola</b>   <i>mundo</i></p>", "//p") == "Hola mundo"

    def test_nbsp_collapsed(self):
        assert layout("<p>a&nbsp;&nbsp;<b>b</b></p>", "//p") == "a b"

    def test_comment_does_not_split_a_word(self):
        assert layout("<div>Antes<!-- c -->Después</div>", "//div") == "AntesDespués"

    def test_excluded_tags_add_no_space(self):
        assert layout("<div>a<style>.x{}</style>b</div>", "//div") == "ab"
        assert (
            layout("<div>Texto<script>var x = 1;</script> visible</div>", "//div")
            == "Texto visible"
        )


class TestBlocks:
    def test_headings_lists_and_paragraphs(self):
        html = (
            "<div><h2>Título</h2><ul><li>Uno</li><li>Dos</li></ul>"
            "<p>Párrafo A</p><p>Párrafo B</p></div>"
        )
        assert layout(html, "//div") == "Título\n\nUno\nDos\n\nPárrafo A\n\nPárrafo B"

    def test_br_starts_a_new_line(self):
        assert layout("<p>Línea 1<br>Línea 2</p>", "//p") == "Línea 1\nLínea 2"

    def test_consecutive_br_leave_at_most_one_blank_line(self):
        assert layout("<p>a<br><br>b</p>", "//p") == "a\n\nb"
        assert layout("<p>a<br><br><br><br>b</p>", "//p") == "a\n\nb"

    def test_trailing_br_inside_a_block_adds_nothing(self):
        assert layout("<ul><li>a<br></li><li>b</li></ul>", "//ul") == "a\nb"

    def test_table_cells_spaced_rows_on_their_own_line(self):
        html = (
            "<table><tr><td>Color</td><td>Rojo</td></tr>"
            "<tr><td>Tamaño</td><td>Grande</td></tr></table>"
        )
        assert layout(html, "//table") == "Color Rojo\nTamaño Grande"

    def test_select_options_spaced(self):
        html = (
            "<div>Elegí: <select><option>Montevideo</option>"
            "<option>Canelones</option></select> y seguí</div>"
        )
        assert layout(html, "//div") == "Elegí: Montevideo Canelones y seguí"

    def test_pre_kept_verbatim_between_blank_lines(self):
        html = "<div><p>Código:</p><pre>\ndef f():\n    return 1\n</pre><p>Fin</p></div>"
        assert layout(html, "//div") == "Código:\n\ndef f():\n    return 1\n\nFin"

    def test_namespaced_xhtml(self):
        s = Selector(
            text='<html xmlns="http://www.w3.org/1999/xhtml"><body><p>a</p><p>b</p></body></html>',
            type="xml",
        )
        result = get_xpath_text(
            parsel_sel=s, xpath="//*[local-name()='body']", guess_layout=True
        )
        assert result == "a\n\nb"


class TestSelection:
    def test_text_xpath_equals_element_xpath(self):
        html = '<p><b>Total</b>: 42 (<a href="#">ver</a>).</p>'
        assert layout(html, "//p//text()") == layout(html, "//p")

    def test_pre_text_node_kept_verbatim(self):
        assert layout("<pre>a\n    b</pre>", "//pre/text()") == "a\n    b"

    def test_several_elements(self):
        assert layout("<ul><li>Uno</li><li>Dos</li></ul>", "//li") == "Uno\nDos"
        assert layout("<div><p>One</p><p>Two</p></div>", "//p") == "One\n\nTwo"

    def test_unselected_text_between_matches_becomes_a_space(self):
        assert layout("<p><b>A</b>,<b>B</b></p>", "//b") == "A B"

    def test_nested_matches_not_duplicated(self):
        assert layout("<div>Externo <div>Interno</div></div>", "//div") == "Externo\nInterno"

    def test_attributes_and_scalars_unchanged(self):
        assert layout('<a href="http://x.com">link</a>', "//a/@href") == "http://x.com"
        assert layout("<script src='/app.js'></script>", "//script/@src") == "/app.js"
        assert layout("<p>a</p><p>b</p>", "count(//p)") == "2.0"
        assert layout("<p> a  b </p>", "string(//p)") == "a b"

    def test_selected_text_inside_script_is_kept(self):
        html = '<script type="application/ld+json">{"a": 1}</script>'
        assert layout(html, "//script/text()") == '{"a": 1}'

    def test_excluded_element_selected_directly_is_empty(self):
        assert layout("<div>x<script>y</script></div>", "//script") == ""

    def test_empty_match(self):
        assert layout("<p>x</p>", "//nothing") == ""

    def test_invalid_xpath_raises_value_error(self):
        with pytest.raises(ValueError):
            layout("<p>x</p>", "//p[")

    def test_object_with_selector_like_a_scrapy_response(self):
        class Response:
            def __init__(self, html):
                self.selector = sel(html)

            def xpath(self, query):
                return self.selector.xpath(query)

        result = get_xpath_text(
            parsel_sel=Response("<p><b>Hola</b> mundo</p>"),
            xpath="//p//text()",
            guess_layout=True,
        )
        assert result == "Hola mundo"

    def test_deep_dom_does_not_crash(self):
        assert layout(deep_nested_html(1500)) == "DEEP_LEAF"

    def test_mojibake_still_fixed(self):
        assert layout("<p>" + mojibake("café") + " <b>x</b></p>", "//p") == "café x"


class TestDefaultUnchanged:
    def test_default_is_still_one_text_node_per_line(self):
        html = '<p><b>Total</b>: 42 (<a href="#">ver</a>).</p>'
        assert get_xpath_text(parsel_sel=sel(html), xpath="//p") == "Total\n: 42 (\nver\n)."

    @pytest.mark.parametrize(
        ("fixture", "xpath"),
        [
            ("news.html", "//article"),
            ("news.html", "//article//text()"),
            ("product.html", "//main"),
            ("product.html", "//main//text()"),
            ("data_table.html", "//table"),
            ("data_table.html", "//td"),
            ("messy.html", "//body"),
            ("messy.html", "//body//text()"),
            ("encoding.html", "//body"),
            ("whitespace.html", "//body"),
            ("whitespace.html", "//pre//text()"),
            ("svg.html", "//body"),
        ],
    )
    def test_only_whitespace_changes(self, fixture, xpath):
        s = sel(load_fixture(fixture))
        plain = get_xpath_text(parsel_sel=s, xpath=xpath, fix_mojibake=False)
        laid_out = get_xpath_text(
            parsel_sel=s, xpath=xpath, fix_mojibake=False, guess_layout=True
        )
        assert "".join(laid_out.split()) == "".join(plain.split())


class TestOtherFunctions:
    def test_rows(self):
        html = (
            "<div class='c'><h3>T1</h3><p>a <b>b</b></p></div>"
            "<div class='c'><h3>T2</h3></div>"
        )
        rows = get_results_row_text(
            parsel_sel=sel(html), xpath="//div[@class='c']", guess_layout=True
        )
        assert rows == ["T1\n\na b", "T2"]

    def test_rows_keep_one_row_per_match(self):
        rows = get_results_row_text(
            parsel_sel=sel(search_results_html(50)),
            xpath="//div[@class='result-card']",
            guess_layout=True,
        )
        assert len(rows) == 50
        assert rows[0].startswith("Resultado número 0\n\nEste es el fragmento del resultado 0,")

    def test_bs4_soup(self):
        result = get_bs4_soup_text(
            bs4_soup=soup("<div><p>a <b>b</b></p><p>c</p></div>"), guess_layout=True
        )
        assert result == "a b\n\nc"
