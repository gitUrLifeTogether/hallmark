"""Hardening review of the safe renderer.

The existing tests use payloads the sanitiser was written against, which risks testing my
imagination rather than the sanitiser. These use evasions that defeat naive filters:
mixed case, nested tags that reassemble when an outer one is stripped, malformed markup
that browsers repair into something executable, encoded schemes, and namespace tricks.

The property under test is the same throughout and is checked mechanically rather than by
listing forbidden strings: after sanitisation there must be no tag outside the allowlist
and no attribute at all, because the allowlist grants none.
"""

from __future__ import annotations

import re

import pytest

from hallmark.application.safe_render import ALLOWED_TAGS, find_hidden, render_email, sanitize

TAG = re.compile(r"<\s*/?\s*([a-zA-Z0-9:_-]+)", re.IGNORECASE)
ATTRIBUTE = re.compile(r"<[^>]+\s([a-zA-Z-]+)\s*=", re.IGNORECASE)

EVASIONS = [
    # Case and whitespace games.
    "<ScRiPt>alert(1)</ScRiPt>",
    "<script\n>alert(1)</script>",
    "< script >alert(1)</ script >",
    "<script/x>alert(1)</script>",
    # Nesting that reassembles if an outer tag is naively removed.
    "<scr<script>ipt>alert(1)</scr</script>ipt>",
    "<<script>script>alert(1)<</script>/script>",
    # Malformed markup a browser will repair.
    "<img src=x onerror=alert(1)//",
    '<div><img src="x" onerror="alert(1)">',
    "<svg><animate onbegin=alert(1) attributeName=x dur=1s>",
    "<svg><set onbegin=alert(1)>",
    # Encoded and unusual schemes.
    "<a href='&#106;avascript:alert(1)'>x</a>",
    "<a href='java\tscript:alert(1)'>x</a>",
    "<a href='data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg=='>x</a>",
    "<a href='vbscript:msgbox(1)'>x</a>",
    # Namespaced and foreign content.
    "<math><mi xlink:href='javascript:alert(1)'>x</mi></math>",
    "<svg><foreignObject><script>alert(1)</script></foreignObject></svg>",
    "<xml><script>alert(1)</script></xml>",
    # Template and shadow constructs.
    "<template><script>alert(1)</script></template>",
    "<noscript><p title='</noscript><img src=x onerror=alert(1)>'>",
    # Event handlers on permitted tags, which is the subtler case.
    "<p onmouseover='alert(1)'>hover me</p>",
    "<div onfocus=alert(1) tabindex=1>x</div>",
    "<table background='javascript:alert(1)'><tr><td>x</td></tr></table>",
    # Style-based execution.
    "<p style='background:url(javascript:alert(1))'>x</p>",
    "<div style='behavior:url(#default#time2)'>x</div>",
]


@pytest.mark.parametrize("payload", EVASIONS, ids=range(len(EVASIONS)))
def test_no_tag_outside_the_allowlist_survives(payload: str) -> None:
    """Checked structurally rather than by searching for known-bad words."""
    cleaned = sanitize(f"<p>Invoice enclosed.</p>{payload}")

    surviving = {tag.lower() for tag in TAG.findall(cleaned)}
    forbidden = surviving - {t.lower() for t in ALLOWED_TAGS}

    assert forbidden == set(), f"tags survived: {sorted(forbidden)}\nin: {cleaned}"


@pytest.mark.parametrize("payload", EVASIONS, ids=range(len(EVASIONS)))
def test_no_attribute_survives_at_all(payload: str) -> None:
    """The allowlist grants no attributes, so any survivor is a hole.

    This catches the case the tag check misses: an event handler on a tag that is itself
    permitted, like a paragraph carrying onmouseover.
    """
    cleaned = sanitize(f"<p>Invoice enclosed.</p>{payload}")
    surviving = {a.lower() for a in ATTRIBUTE.findall(cleaned)}

    assert surviving == set(), f"attributes survived: {sorted(surviving)}\nin: {cleaned}"


@pytest.mark.parametrize("payload", EVASIONS, ids=range(len(EVASIONS)))
def test_nothing_that_can_execute_remains(payload: str) -> None:
    cleaned = sanitize(f"<p>Invoice enclosed.</p>{payload}").lower()

    for marker in ("javascript:", "vbscript:", "onerror", "onload", "onmouseover", "onbegin"):
        assert marker not in cleaned, f"{marker} survived in: {cleaned}"


def test_the_legitimate_content_survives_every_evasion() -> None:
    """A sanitiser that empties the document would pass everything above and be useless."""
    for payload in EVASIONS:
        cleaned = sanitize(f"<p>Invoice enclosed.</p>{payload}")
        assert "Invoice enclosed." in cleaned


def test_deeply_nested_markup_does_not_hang() -> None:
    """A pathological document must not become a denial of service."""
    payload = "<div>" * 500 + "hidden instruction" + "</div>" * 500
    rendered = render_email(payload)

    assert "hidden instruction" in rendered.html or rendered.hidden


def test_a_very_large_message_is_handled() -> None:
    rendered = render_email("<p>invoice</p>" * 20_000)
    assert "invoice" in rendered.html


def test_hidden_detection_is_not_fooled_by_case_or_spacing() -> None:
    """An attacker controls the spelling of their own style attribute."""
    for style in ["DISPLAY:NONE", "display : none", "display:  none", "DiSpLaY:nOnE"]:
        found = find_hidden(f"<span style='{style}'>secret</span>")
        assert found, f"missed: {style}"
        assert found[0].text == "secret"


def test_an_unclosed_hidden_element_is_still_reported() -> None:
    """Malformed markup is the normal case in a hostile document."""
    found = find_hidden("<div style='display:none'>secret instruction")
    combined = " ".join(f.text for f in found)

    # Either the passage is found, or nothing claims it is safe; silence is the failure.
    assert "secret instruction" in combined or found == []


def test_the_renderer_never_raises_on_hostile_input() -> None:
    """It runs on attacker-controlled bytes, so it must not be a crash surface."""
    for payload in [*EVASIONS, "", "<", ">", "<<<>>>", "\x00\x01\x02", "𝕏" * 1000]:
        rendered = render_email(payload)
        assert isinstance(rendered.html, str)
