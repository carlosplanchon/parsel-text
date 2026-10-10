"""Behaviour tests for the public API.

These pin the intended behaviour: text joined with newlines in document order,
no trailing newline, script/style/comments/noscript excluded, SVG text kept,
mojibake fixed, whitespace collapsed (except inside <pre>).
"""

import pytest
from conftest import NBSP, README_HTML, load_fixture, mojibake, sel, soup

from parsel_text import (
    get_bs4_soup_text,
    get_css_text,
    get_results_row_text,
    get_selector_text,
    get_xpath_text,
)


class TestGetXpathText:
    def test_readme_example(self):
        result = get_xpath_text(
            parsel_sel=sel(README_HTML),
            xpath="//div[@id='content']/p//text()",
        )
        assert result == "Hello, world!\nWelcome to the parsel_text library."

    def test_no_trailing_newline(self):
        result = get_xpath_text(parsel_sel=sel(README_HTML), xpath="//p")
        assert not result.endswith("\n")

    def test_empty_match_returns_empty_string(self):
        assert get_xpath_text(parsel_sel=sel(README_HTML), xpath="//nonexistent") == ""

    def test_document_order_preserved(self):
        result = get_xpath_text(
            parsel_sel=sel("<div>A<span>B</span>C<p>D</p></div>"), xpath="//div"
        )
        assert result == "A\nB\nC\nD"

    def test_deeply_nested_order(self):
        result = get_xpath_text(
            parsel_sel=sel("<body>A<div>B<span>C</span>D</div>E</body>"),
            xpath="//body",
        )
        assert result == "A\nB\nC\nD\nE"

    def test_multiple_matches_concatenated(self):
        result = get_xpath_text(
            parsel_sel=sel("<div><p>One</p><p>Two</p></div>"), xpath="//p"
        )
        assert result == "One\nTwo"

    def test_element_xpath_equals_text_xpath(self):
        s = sel("<div><p>One</p><p>Two</p></div>")
        assert get_xpath_text(parsel_sel=s, xpath="//p") == get_xpath_text(
            parsel_sel=s, xpath="//p//text()"
        )

    def test_nested_selector_not_duplicated(self):
        result = get_xpath_text(parsel_sel=sel("<div><div>X</div></div>"), xpath="//div")
        assert result == "X"

    # -- mojibake ----------------------------------------------------------- #
    def test_mojibake_fixed_by_default(self):
        s = sel("<p>" + mojibake("café") + "</p>")
        assert get_xpath_text(parsel_sel=s, xpath="//p") == "café"

    def test_mojibake_fix_true(self):
        s = sel("<p>" + mojibake("café") + "</p>")
        assert get_xpath_text(parsel_sel=s, xpath="//p", fix_mojibake=True) == "café"

    def test_mojibake_fix_false_preserves_raw(self):
        s = sel("<p>" + mojibake("café") + "</p>")
        assert get_xpath_text(parsel_sel=s, xpath="//p", fix_mojibake=False) == mojibake(
            "café"
        )

    def test_mojibake_fix_leaves_the_rest_untouched(self):
        rest = "“hello” ﬁle ＡＢＣ Tom &amp; Jerry"
        s = sel("<p>" + mojibake("café") + " " + rest.replace("&", "&amp;") + "</p>")
        assert get_xpath_text(parsel_sel=s, xpath="//p") == "café " + rest

    # -- entities & whitespace --------------------------------------------- #
    def test_entity_amp(self):
        assert (
            get_xpath_text(parsel_sel=sel("<body>Tom &amp; Jerry</body>"), xpath="//body")
            == "Tom & Jerry"
        )

    def test_entity_lt_gt(self):
        assert (
            get_xpath_text(parsel_sel=sel("<body>1 &lt; 2 &gt; 0</body>"), xpath="//body")
            == "1 < 2 > 0"
        )

    def test_nbsp_entity_collapsed(self):
        assert (
            get_xpath_text(parsel_sel=sel("<body>a&nbsp;&nbsp;b</body>"), xpath="//body")
            == "a b"
        )

    def test_nbsp_raw_collapsed(self):
        assert (
            get_xpath_text(
                parsel_sel=sel("<body>a" + NBSP + NBSP + "b</body>"), xpath="//body"
            )
            == "a b"
        )

    def test_internal_whitespace_collapsed(self):
        assert (
            get_xpath_text(
                parsel_sel=sel("<p>the   parsel_text   library</p>"), xpath="//p"
            )
            == "the parsel_text library"
        )

    # -- exclusions --------------------------------------------------------- #
    def test_html_comment_excluded(self):
        assert (
            get_xpath_text(
                parsel_sel=sel("<body>Before<!-- SECRET COMMENT -->After</body>"),
                xpath="//body",
            )
            == "Before\nAfter"
        )

    def test_script_content_excluded(self):
        assert (
            get_xpath_text(
                parsel_sel=sel("<body>Text<script>var x = 42;</script>More</body>"),
                xpath="//body",
            )
            == "Text\nMore"
        )

    def test_style_content_excluded(self):
        assert (
            get_xpath_text(
                parsel_sel=sel("<body>Text<style>.a{color:red}</style>More</body>"),
                xpath="//body",
            )
            == "Text\nMore"
        )

    def test_noscript_excluded(self):
        assert (
            get_xpath_text(
                parsel_sel=sel("<article>hi<noscript>NS</noscript>bye</article>"),
                xpath="//article",
            )
            == "hi\nbye"
        )

    # -- misc --------------------------------------------------------------- #
    def test_attribute_selection(self):
        html = '<a href="http://x.com">link</a>'
        assert get_xpath_text(parsel_sel=sel(html), xpath="//a/@href") == "http://x.com"

    def test_emoji_preserved(self):
        assert (
            get_xpath_text(parsel_sel=sel("<body>hi \U0001f600 end</body>"), xpath="//body")
            == "hi \U0001f600 end"
        )

    def test_malformed_html_tolerated(self):
        result = get_xpath_text(parsel_sel=sel("<div><p>Hi</div>"), xpath="//div")
        assert result == "Hi"

    def test_pre_whitespace_preserved(self):
        result = get_xpath_text(
            parsel_sel=sel("<pre>a\n    b</pre>"), xpath="//pre"
        )
        assert result == "a\n    b"


class TestGetResultsRowText:
    def test_multiple_rows(self):
        rows = get_results_row_text(
            parsel_sel=sel("<ul><li>Uno   dos</li><li>Tres</li></ul>"), xpath="//li"
        )
        assert rows == ["Uno dos", "Tres"]

    def test_whitespace_only_row_is_empty_string(self):
        rows = get_results_row_text(
            parsel_sel=sel("<ul><li>  </li><li>x</li></ul>"), xpath="//li"
        )
        assert rows == ["", "x"]

    def test_empty_match_returns_empty_list(self):
        assert get_results_row_text(parsel_sel=sel("<p>no lists</p>"), xpath="//li") == []

    def test_order_preserved(self):
        rows = get_results_row_text(
            parsel_sel=sel("<ul><li>1</li><li>2</li><li>3</li></ul>"), xpath="//li"
        )
        assert rows == ["1", "2", "3"]

    def test_row_with_nested_elements(self):
        rows = get_results_row_text(
            parsel_sel=sel("<ul><li>A<span>B</span></li></ul>"), xpath="//li"
        )
        assert rows == ["A\nB"]

    def test_mojibake_fixed_by_default(self):
        rows = get_results_row_text(
            parsel_sel=sel("<ul><li>" + mojibake("café") + "</li></ul>"), xpath="//li"
        )
        assert rows == ["café"]

    def test_mojibake_fix_false(self):
        rows = get_results_row_text(
            parsel_sel=sel("<ul><li>" + mojibake("café") + "</li></ul>"),
            xpath="//li",
            fix_mojibake=False,
        )
        assert rows == [mojibake("café")]


class TestGetBs4SoupText:
    def test_extracts_text_with_order(self):
        assert get_bs4_soup_text(bs4_soup=soup("<div>A<span>B</span>C</div>")) == "A\nB\nC"

    def test_fixes_mojibake_by_default(self):
        result = get_bs4_soup_text(bs4_soup=soup("<div>" + mojibake("café") + "</div>"))
        assert result == "café"

    def test_honours_fix_mojibake_false(self):
        raw = mojibake("café")
        assert get_bs4_soup_text(bs4_soup=soup("<div>" + raw + "</div>"), fix_mojibake=False) == raw

    def test_comment_excluded(self):
        assert (
            get_bs4_soup_text(bs4_soup=soup("<div>Before<!-- c -->After</div>"))
            == "Before\nAfter"
        )

    def test_script_excluded(self):
        assert (
            get_bs4_soup_text(
                bs4_soup=soup("<div>Text<script>var x = 1;</script>More</div>")
            )
            == "Text\nMore"
        )


class TestGetSelectorText:
    HTML = (
        '<div class="card"><h2>First</h2><div class="body">'
        "<p>Hello <b>world</b>.<script>var x = 1;</script></p><p>Second.</p></div></div>"
        '<div class="card"><h2>Second</h2><div class="body"><p>More.</p></div></div>'
    )

    def test_css_elements(self):
        selection = sel(self.HTML).css("div.body")
        assert get_selector_text(parsel_sel=selection) == "Hello\nworld\n.\nSecond.\nMore."
        assert (
            get_selector_text(parsel_sel=selection, guess_layout=True)
            == "Hello world.\n\nSecond.\n\nMore."
        )

    @pytest.mark.parametrize("guess_layout", [False, True])
    def test_same_as_get_xpath_text_on_the_selection(self, guess_layout):
        s = sel(self.HTML)
        for selection in (s.css("div.body"), s.css("div.card").css("p"), s.xpath("//h2")):
            assert get_selector_text(
                parsel_sel=selection, guess_layout=guess_layout
            ) == get_xpath_text(parsel_sel=selection, xpath=".", guess_layout=guess_layout)

    def test_single_selector_and_generator(self):
        s = sel(self.HTML)
        assert get_selector_text(parsel_sel=s.css("h2")[0]) == "First"
        assert get_selector_text(parsel_sel=(x for x in s.css("h2"))) == "First\nSecond"

    def test_chained_selection_does_not_repeat_elements(self):
        html = '<div class="a"><p>X</p><div class="a"><p>Y</p></div></div>'
        selection = sel(html).css("div.a").css("p")
        assert get_selector_text(parsel_sel=selection) == "X\nY"
        assert get_selector_text(parsel_sel=selection, guess_layout=True) == "X\n\nY"

    def test_text_selection_one_piece_per_line(self):
        selection = sel("<p>Hello <b>world</b>.</p>").css("p ::text")
        assert get_selector_text(parsel_sel=selection) == "Hello\nworld\n."
        assert get_selector_text(parsel_sel=selection, guess_layout=True) == "Hello\nworld\n."

    def test_pre_text_selection_is_collapsed(self):
        selection = sel("<pre>a\n    b</pre>").css("pre::text")
        assert get_selector_text(parsel_sel=selection) == "a b"

    def test_json_looking_values(self):
        s = sel('<p>42</p><p>true</p><p>null</p><a data-n="42">x</a>')
        assert get_selector_text(parsel_sel=s.css("p::text")) == "42\ntrue\nnull"
        assert get_selector_text(parsel_sel=s.css("p::text")[1]) == "true"
        assert get_selector_text(parsel_sel=s.css("a::attr(data-n)")) == "42"

    def test_attribute_and_empty_selections(self):
        s = sel('<a href="/one">1</a><a href="/two">2</a>')
        assert get_selector_text(parsel_sel=s.css("a::attr(href)")) == "/one\n/two"
        assert get_selector_text(parsel_sel=s.css("table")) == ""

    def test_mojibake(self):
        selection = sel("<p>" + mojibake("café") + "</p>").css("p")
        assert get_selector_text(parsel_sel=selection) == "café"
        assert get_selector_text(parsel_sel=selection, fix_mojibake=False) == mojibake("café")

    @pytest.mark.parametrize("guess_layout", [False, True])
    @pytest.mark.parametrize(
        ("fixture", "tag"),
        [
            ("news.html", "article"),
            ("product.html", "main"),
            ("data_table.html", "table"),
            ("messy.html", "body"),
        ],
    )
    def test_css_on_fixtures_matches_xpath(self, fixture, tag, guess_layout):
        s = sel(load_fixture(fixture))
        assert get_selector_text(
            parsel_sel=s.css(tag), guess_layout=guess_layout
        ) == get_xpath_text(parsel_sel=s, xpath=f"//{tag}", guess_layout=guess_layout)


class TestGetCssText:
    HTML = (
        '<div class="body"><p>Hello <b>world</b>.</p><p>Bye.</p></div>'
        '<a href="/one">1</a><a href="/two">2</a>'
    )

    def test_elements(self):
        s = sel(self.HTML)
        assert get_css_text(parsel_sel=s, css="div.body") == "Hello\nworld\n.\nBye."
        assert (
            get_css_text(parsel_sel=s, css="div.body", guess_layout=True)
            == "Hello world.\n\nBye."
        )

    def test_text_pseudo_element_gets_layout(self):
        s = sel(self.HTML)
        assert get_css_text(parsel_sel=s, css="div.body ::text") == "Hello\nworld\n.\nBye."
        assert (
            get_css_text(parsel_sel=s, css="div.body ::text", guess_layout=True)
            == "Hello world.\n\nBye."
        )

    def test_text_pseudo_element_keeps_script_text(self):
        s = sel("<div><p>a<script>var x = 1;</script></p></div>")
        assert get_css_text(parsel_sel=s, css="div ::text") == "a\nvar x = 1;"
        assert get_css_text(parsel_sel=s, css="div") == "a"

    def test_attr_pseudo_element(self):
        assert get_css_text(parsel_sel=sel(self.HTML), css="a::attr(href)") == "/one\n/two"

    def test_json_looking_text(self):
        s = sel("<p>42</p><p>true</p><p>null</p>")
        assert get_css_text(parsel_sel=s, css="p::text") == "42\ntrue\nnull"
        assert get_css_text(parsel_sel=s, css="p::text", guess_layout=True) == "42\n\ntrue\n\nnull"

    def test_selector_list_and_response_like_object(self):
        cards = sel('<div class="c"><h2>First</h2></div><div class="c"><h2>Second</h2></div>')
        assert get_css_text(parsel_sel=cards.css("div.c"), css="h2") == "First\nSecond"

        class Response:
            def __init__(self, html):
                self.selector = sel(html)

            def xpath(self, query):
                return self.selector.xpath(query)

        response = Response("<p><b>Hello</b> world</p>")
        assert get_css_text(parsel_sel=response, css="p ::text", guess_layout=True) == "Hello world"

    def test_empty_match_and_invalid_css(self):
        assert get_css_text(parsel_sel=sel(self.HTML), css="table") == ""
        with pytest.raises(SyntaxError):
            get_css_text(parsel_sel=sel(self.HTML), css="div[")

    def test_mojibake(self):
        s = sel("<p>" + mojibake("café") + "</p>")
        assert get_css_text(parsel_sel=s, css="p") == "café"
        assert get_css_text(parsel_sel=s, css="p", fix_mojibake=False) == mojibake("café")

    @pytest.mark.parametrize("guess_layout", [False, True])
    @pytest.mark.parametrize(
        ("fixture", "tag"),
        [
            ("news.html", "article"),
            ("product.html", "main"),
            ("data_table.html", "table"),
            ("messy.html", "body"),
        ],
    )
    def test_fixtures_match_xpath(self, fixture, tag, guess_layout):
        s = sel(load_fixture(fixture))
        assert get_css_text(
            parsel_sel=s, css=tag, guess_layout=guess_layout
        ) == get_xpath_text(parsel_sel=s, xpath=f"//{tag}", guess_layout=guess_layout)
