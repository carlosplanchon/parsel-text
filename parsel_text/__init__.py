"""parsel_text: extract text from XPath queries on parsel Selectors.

The extractor walks lxml text nodes natively (no BeautifulSoup): it fixes
mojibake with ftfy, drops <script>/<style>/<noscript>/comment text, preserves
whitespace inside <pre>/<textarea>, and never duplicates text when an XPath
matches nested elements. With guess_layout it joins the text the way a browser
lays it out.
"""

from collections.abc import Iterable
from typing import Any, Protocol

import ftfy
from parsel import Selector, SelectorList, css2xpath

# Tags whose text content is not real page content and is dropped. <template> and
# <noscript> hold inert markup; <script>/<style> hold code.
_EXCLUDE_TAGS = frozenset({"script", "style", "noscript", "template"})

# Tags where whitespace is significant and must be preserved verbatim.
_PREFORMATTED_TAGS = frozenset({"pre", "textarea"})

_LINE_BREAK_TAGS = frozenset({
    "address", "article", "aside", "body", "caption", "center", "dd", "details",
    "dialog", "div", "dt", "fieldset", "figcaption", "footer", "form", "header",
    "hgroup", "hr", "html", "legend", "li", "main", "nav", "search", "section",
    "summary", "table", "tbody", "tfoot", "thead", "tr",
})

_BLANK_LINE_TAGS = frozenset({
    "blockquote", "dl", "figure", "h1", "h2", "h3", "h4", "h5", "h6", "menu",
    "ol", "p", "pre", "title", "ul",
})

_SPACED_TAGS = frozenset({"button", "option", "select", "td", "th"})


class SupportsXPath(Protocol):
    """A parsel Selector, a SelectorList or a Scrapy response."""

    def xpath(self, query: str, /) -> Any: ...


def _collapse_whitespace(text: str) -> str:
    """Collapse every run of whitespace into a single space and strip the ends."""
    return " ".join(text.split())


def _ancestor_tags(text_node) -> set:
    """Return the tag names of an lxml text node's ancestors.

    lxml exposes two kinds of text node: an element's ``.text`` (``is_tail`` is
    False -- it lives *inside* the element) and its ``.tail`` (``is_tail`` is True
    -- the text that *follows* the element, which really belongs to the element's
    parent). For a tail node we therefore start one level up; otherwise text that
    merely follows a <script>/<noscript> would be wrongly dropped.
    """
    parent = text_node.getparent()
    if parent is None:
        return set()
    start = parent.getparent() if getattr(text_node, "is_tail", False) else parent
    tags = set()
    node = start
    while node is not None:
        tag = node.tag
        if isinstance(tag, str):  # skips comments/PIs, whose .tag is a callable
            tags.add(tag)
        node = node.getparent()
    return tags


def _clean(raw: str, excluded: bool, preformatted: bool) -> str:
    """Cleaned contribution of a raw text node given its ancestor flags."""
    if excluded:
        return ""
    text = raw if preformatted else _collapse_whitespace(raw)
    return text if text.strip() != "" else ""


def _clean_text_node(text_node) -> str:
    """One lxml text node -> its cleaned contribution, or "" if it is dropped."""
    tags = _ancestor_tags(text_node)
    return _clean(
        str(text_node),
        bool(tags & _EXCLUDE_TAGS),
        bool(tags & _PREFORMATTED_TAGS),
    )


def _iter_text_parts(element) -> list[str]:
    """All descendant text of an lxml element, in document order, cleaned.

    The exclusion/preformatted status contributed by *element*'s own ancestors
    is the same for every text node in the subtree, so it is computed once;
    each text node then only walks up to *element* rather than all the way to
    the document root (which would repeat that shared ancestor chain per node).
    """
    above_excluded = above_preformatted = False
    node = element.getparent()
    while node is not None:
        tag = node.tag
        if isinstance(tag, str):
            if tag in _EXCLUDE_TAGS:
                above_excluded = True
            if tag in _PREFORMATTED_TAGS:
                above_preformatted = True
        node = node.getparent()

    parts: list[str] = []
    for text_node in element.xpath(".//text()"):
        parent = text_node.getparent()
        if parent is None:
            excluded = preformatted = False
        else:
            excluded, preformatted = above_excluded, above_preformatted
            # A tail node belongs to its parent, so start one level up.
            node = (
                parent.getparent()
                if getattr(text_node, "is_tail", False)
                else parent
            )
            while node is not None:
                tag = node.tag
                if isinstance(tag, str):
                    if tag in _EXCLUDE_TAGS:
                        excluded = True
                    if tag in _PREFORMATTED_TAGS:
                        preformatted = True
                if node is element:
                    break
                node = node.getparent()

        part = _clean(str(text_node), excluded, preformatted)
        if part != "":
            parts.append(part)
    return parts


def _outermost(elements: list) -> list:
    """Keep only elements that are not nested inside another element in the list.

    XPath node-sets already de-duplicate individual nodes, but a query like
    ``//div`` returns an ancestor *and* its descendants; extracting each subtree
    would repeat the descendants' text once per level. Keeping only the outermost
    matches (whose subtrees already cover the inner ones) removes the duplication.
    """
    matched = {id(el) for el in elements}
    return [
        el
        for el in elements
        if not any(id(anc) in matched for anc in el.iterancestors())
    ]


def _string_part(root: str) -> str:
    """Clean a string XPath result (a text node or an attribute value)."""
    if getattr(root, "getparent", None) is not None:
        # A smart string (text node / attribute) that knows its parent: honour
        # the exclusion and preformatted rules just like an element's text.
        return _clean_text_node(root)
    return _collapse_whitespace(root)


def _scalar_text(value) -> str:
    """An XPath scalar result (number, boolean, string) as parsel renders it."""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def _extract(sel_results: SelectorList) -> list[str]:
    """Text parts for a whole SelectorList, in document order, de-duplicated."""
    elements = [s.root for s in sel_results if hasattr(s.root, "tag")]
    keep = {id(el) for el in _outermost(elements)}

    parts: list[str] = []
    for s in sel_results:
        root = s.root
        if not hasattr(root, "tag"):
            part = _string_part(root if isinstance(root, str) else _scalar_text(root))
            if part != "":
                parts.append(part)
        elif id(root) in keep:
            parts.extend(_iter_text_parts(root))
    return parts


def _local_name(tag: str) -> str:
    """Tag name without its namespace, lowercased."""
    return tag.rpartition("}")[2].lower()


def _smart_results(parsel_sel: SupportsXPath, xpath: str) -> list:
    """XPath results as lxml objects, with text nodes that still know their parent."""
    results = parsel_sel.xpath(xpath)
    if not any(isinstance(s.root, str) for s in results):
        return [s.root for s in results]

    selectors: list[Any]
    if isinstance(parsel_sel, Selector):
        selectors = [parsel_sel]
    elif isinstance(parsel_sel, list):
        selectors = list(parsel_sel)
    else:
        selectors = [getattr(parsel_sel, "selector", parsel_sel)]

    smart: list = []
    for s in selectors:
        root: Any = getattr(s, "root", None)
        if getattr(s, "type", None) in ("html", "xml") and hasattr(root, "xpath"):
            found = root.xpath(xpath, namespaces=dict(s.namespaces), smart_strings=True)
            smart.extend(found if isinstance(found, list) else [found])
        else:
            smart.extend(x.root for x in s.xpath(xpath))
    return smart


def _is_flow_node(value) -> bool:
    """True for elements and text nodes; False for attributes and scalars."""
    if isinstance(value, str):
        getparent = getattr(value, "getparent", None)
        return (
            getattr(value, "is_attribute", True) is False
            and getparent is not None
            and getparent() is not None
        )
    return isinstance(getattr(value, "tag", None), str)


def _walk(root):
    """Yield (event, node, is_tail, text) for *root*'s subtree in document order."""
    yield "start", root, False, ""
    if root.text:
        yield "text", root, False, root.text
    stack = [(root, iter(root))]
    while stack:
        element, children = stack[-1]
        child = next(children, None)
        if child is None:
            stack.pop()
            yield "end", element, False, ""
            if stack and element.tail:
                yield "text", element, True, element.tail
        elif isinstance(child.tag, str):
            yield "start", child, False, ""
            if child.text:
                yield "text", child, False, child.text
            stack.append((child, iter(child)))
        elif child.tail:
            yield "text", child, True, child.tail


def _common_ancestor(elements: list):
    """Deepest element containing all of *elements*, or None if there is none."""
    common: list | None = None
    for el in elements:
        chain = [el, *el.iterancestors()][::-1]
        if common is None:
            common = chain
            continue
        size = 0
        for a, b in zip(common, chain):
            if a is not b:
                break
            size += 1
        common = common[:size]
        if not common:
            return None
    return common[-1] if common else None


def _ancestor_state(element) -> tuple[int, int]:
    """Excluded and preformatted tags enclosing *element* (itself not counted)."""
    excluded = preformatted = 0
    for anc in element.iterancestors():
        if isinstance(anc.tag, str):
            excluded += anc.tag in _EXCLUDE_TAGS
            preformatted += _local_name(anc.tag) in _PREFORMATTED_TAGS
    return excluded, preformatted


def _lone_text(node) -> str:
    """Layout of a single text node: collapsed, or verbatim inside <pre>."""
    owner = node.getparent()
    holder = owner.getparent() if node.is_tail else owner
    if holder is None or not (
        _local_name(holder.tag) in _PREFORMATTED_TAGS or _ancestor_state(holder)[1]
    ):
        return _collapse_whitespace(node)
    text = str(node)
    if holder is owner and _local_name(owner.tag) in _PREFORMATTED_TAGS:
        text = text.removeprefix("\n")
    text = text.strip("\n")
    return text if text.strip() else ""


def _layout_render(nodes: list) -> str:
    """Elements and text nodes joined the way a browser lays them out."""
    if len(nodes) == 1 and isinstance(nodes[0], str):
        return _lone_text(nodes[0])

    elements = _outermost([n for n in nodes if not isinstance(n, str)])
    texts: list[Any] = [n for n in nodes if isinstance(n, str)]
    covering = {id(el): el for el in elements}
    picked: dict = {}
    anchors = list(elements)
    for node in texts:
        owner = node.getparent()
        picked[(id(owner), node.is_tail)] = owner
        holder = owner.getparent() if node.is_tail else owner
        anchors.append(owner if holder is None else holder)

    root = _common_ancestor(anchors)
    if root is None:
        return "\n".join(filter(None, (_layout_render([n]) for n in nodes)))

    excluded, preformatted = _ancestor_state(root)
    covered = breaks = brs = 0
    space = False
    out: list[str] = []

    def emit(text: str) -> None:
        nonlocal breaks, brs, space
        if out:
            lines = min(max(breaks, brs), 2)
            if lines:
                trailing = len(out[-1]) - len(out[-1].rstrip("\n"))
                out.append("\n" * max(lines - trailing, 0))
            elif space:
                out.append(" ")
        out.append(text)
        breaks = brs = 0
        space = False

    for event, node, is_tail, text in _walk(root):
        if event == "text":
            if (id(node), is_tail) not in picked and (not covered or excluded):
                space = space or (bool(text) and not excluded)
                continue
            if preformatted:
                if not is_tail and _local_name(node.tag) in _PREFORMATTED_TAGS:
                    text = text.removeprefix("\n")
                if text:
                    emit(text)
                continue
            if text[:1].isspace():
                space = True
            if text.strip():
                emit(" ".join(text.split()))
                space = text[-1].isspace()
            continue

        if node.tag in _EXCLUDE_TAGS:
            excluded += 1 if event == "start" else -1
            continue
        if excluded:
            continue
        step = 1 if event == "start" else -1
        if id(node) in covering:
            covered += step
        name = _local_name(node.tag)
        if name in _PREFORMATTED_TAGS:
            preformatted += step
        if name == "br":
            brs += event == "start"
        elif name in _BLANK_LINE_TAGS:
            breaks = max(breaks, 2)
        elif name in _LINE_BREAK_TAGS:
            breaks = max(breaks, 1)
        elif name in _SPACED_TAGS:
            space = True

    result = "".join(out).strip("\n")
    return result if result.strip() else ""


def _layout_text(results: list) -> str:
    """Lay out XPath results: nodes flow as text, other values go one per line."""
    chunks: list[str] = []
    nodes: list = []
    for value in results:
        if _is_flow_node(value):
            nodes.append(value)
        elif not hasattr(value, "tag"):
            if nodes:
                chunks.append(_layout_render(nodes))
                nodes = []
            chunks.append(_collapse_whitespace(_scalar_text(value)))
    if nodes:
        chunks.append(_layout_render(nodes))
    return "\n".join(chunk for chunk in chunks if chunk)


def get_xpath_text(
    parsel_sel: SupportsXPath,
    xpath: str,
    fix_mojibake: bool = True,
    guess_layout: bool = False,
) -> str:
    """Extract all text matched by *xpath* on *parsel_sel* as a single string.

    Text nodes are joined with newlines, in document order. With *guess_layout*
    they are joined the way a browser lays them out instead: inline tags keep the
    original spacing, block tags start new lines and table cells get a space.
    When *fix_mojibake* is True (default) the result is run through
    ``ftfy.fix_encoding``, which fixes mojibake and leaves everything else as is.
    """
    if guess_layout:
        text = _layout_text(_smart_results(parsel_sel, xpath))
    else:
        text = "\n".join(_extract(parsel_sel.xpath(xpath)))
    return ftfy.fix_encoding(text) if fix_mojibake else text


def get_css_text(
    parsel_sel: SupportsXPath,
    css: str,
    fix_mojibake: bool = True,
    guess_layout: bool = False,
) -> str:
    """Like :func:`get_xpath_text`, but with a CSS selector instead of an XPath.

    The CSS is translated with ``parsel.css2xpath``, so ``::text`` and
    ``::attr()`` work, also with *guess_layout*.
    """
    return get_xpath_text(
        parsel_sel=parsel_sel,
        xpath=css2xpath(css),
        fix_mojibake=fix_mojibake,
        guess_layout=guess_layout,
    )


def get_results_row_text(
    parsel_sel: SupportsXPath,
    xpath: str,
    fix_mojibake: bool = True,
    guess_layout: bool = False,
) -> list[str]:
    """Like :func:`get_xpath_text` but one string per matched node.

    Each match keeps its own full subtree (no cross-match de-duplication): N
    matches produce N rows, in document order.
    """
    rows: list[str] = []
    if guess_layout:
        rows = [_layout_text([value]) for value in _smart_results(parsel_sel, xpath)]
    else:
        for s in parsel_sel.xpath(xpath):
            root = s.root
            if not hasattr(root, "tag"):
                part = _string_part(root if isinstance(root, str) else _scalar_text(root))
                parts = [part] if part != "" else []
            else:
                parts = _iter_text_parts(root)
            rows.append("\n".join(parts))
    return [ftfy.fix_encoding(row) if fix_mojibake else row for row in rows]


def get_selector_text(
    parsel_sel: Selector | Iterable[Selector],
    fix_mojibake: bool = True,
    guess_layout: bool = False,
) -> str:
    """Extract the text of a selection already made (CSS, XPath or chained).

    Elements follow the same rules as :func:`get_xpath_text`. Text and attribute
    selections (``::text``, ``::attr()``) come one per line, without layout.
    """
    selection: SelectorList[Selector] = SelectorList()
    seen: set[int] = set()
    for s in [parsel_sel] if isinstance(parsel_sel, Selector) else parsel_sel:
        # A chained selection can match the same element twice.
        if hasattr(s.root, "tag"):
            if id(s.root) in seen:
                continue
            seen.add(id(s.root))
        selection.append(s)
    if guess_layout:
        text = _layout_text([s.root for s in selection])
    else:
        text = "\n".join(_extract(selection))
    return ftfy.fix_encoding(text) if fix_mojibake else text


def get_bs4_soup_text(
    bs4_soup,
    fix_mojibake: bool = True,
    guess_layout: bool = False,
) -> str:
    """Extract text from a BeautifulSoup object.

    Kept for backwards compatibility. The library no longer depends on
    BeautifulSoup: the soup is re-serialised and run through the native
    extractor, so the caller just needs a value whose ``str()`` is HTML.
    """
    root = Selector(text=str(bs4_soup)).root
    if guess_layout:
        text = _layout_render([root])
    else:
        text = "\n".join(_iter_text_parts(root))
    return ftfy.fix_encoding(text) if fix_mojibake else text


def remove_trailing_chars(text: str) -> str:
    """Collapse all runs of whitespace into single spaces and strip the ends.

    Kept for backwards compatibility. Despite the historical name, this collapses
    *all* internal whitespace, not only trailing whitespace.
    """
    return _collapse_whitespace(text)
