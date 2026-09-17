"""Rendering attacker-controlled email so a person can read it safely.

This is the one place in the system where untrusted content is deliberately shown to a
human, which makes it the one place where getting sanitisation wrong matters. A reviewer
deciding a bank-change review has to see what the message actually said, including the part
the sender tried to hide, and none of it may execute in their browser.

Three things happen here, in order:

1. Everything is sanitised to a small allowlist. Scripts, styles, frames, forms, event
   handlers and any non-http URL are removed rather than escaped, because an escaped
   payload is still a payload once something later unescapes it.
2. Content the sender hid is found and marked, not deleted. Deleting it would hide the
   evidence; marking it is what turns a hidden instruction into the most visible thing on
   the page.
3. The result is returned as a fragment for a sandboxed frame. It carries no scripts, so a
   strict policy on the frame costs nothing and catches anything this module missed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Tags a person needs to read an invoice. Everything else is dropped.
ALLOWED_TAGS: frozenset[str] = frozenset(
    {
        "p",
        "br",
        "div",
        "span",
        "strong",
        "b",
        "em",
        "i",
        "u",
        "ul",
        "ol",
        "li",
        "table",
        "thead",
        "tbody",
        "tr",
        "td",
        "th",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "blockquote",
        "pre",
        "code",
        "hr",
    }
)

#: No `style`, deliberately: the hiding tricks live there, and they are reported instead.
ALLOWED_ATTRIBUTES: dict[str, set[str]] = {"*": set()}

#: Patterns that mean "the recipient was not meant to see this".
_HIDDEN_STYLE = re.compile(
    r"display\s*:\s*none"
    r"|visibility\s*:\s*hidden"
    r"|font-size\s*:\s*0"
    r"|opacity\s*:\s*0(?!\.[1-9])"
    r"|(?:color|colour)\s*:\s*(?:#fff(?:fff)?\b|white\b)"
    r"|text-indent\s*:\s*-\d{4,}",
    re.IGNORECASE,
)

_COMMENT = re.compile(r"<!--(.*?)-->", re.DOTALL)
_HIDDEN_ATTR = re.compile(r"\bhidden\b", re.IGNORECASE)


@dataclass
class HiddenPassage:
    """Something the sender tried to keep out of sight."""

    technique: str
    text: str


@dataclass
class SafeRender:
    """A message rendered for a human, with what was hidden called out."""

    html: str
    hidden: list[HiddenPassage] = field(default_factory=list)

    @property
    def has_hidden_content(self) -> bool:
        return bool(self.hidden)


def _describe(style: str) -> str:
    """Name the trick, in words a reviewer can act on."""
    lowered = style.lower()
    if "display" in lowered and "none" in lowered:
        return "hidden with display:none"
    if "visibility" in lowered:
        return "hidden with visibility:hidden"
    if "font-size" in lowered:
        return "shrunk to zero size"
    if "opacity" in lowered:
        return "made fully transparent"
    if "indent" in lowered:
        return "pushed off the page"
    return "coloured to match the background"


def find_hidden(html: str) -> list[HiddenPassage]:
    """Find passages the sender concealed, before anything is stripped.

    Runs on the raw message on purpose. Sanitising first would remove the `style`
    attributes that are the evidence, and the reviewer would never learn the message had a
    hidden half.
    """
    found: list[HiddenPassage] = []

    for match in re.finditer(
        r"<(\w+)([^>]*\bstyle\s*=\s*[\"'][^\"']*[\"'][^>]*)>(.*?)</\1>", html, re.DOTALL | re.I
    ):
        attributes, inner = match.group(2), match.group(3)
        if _HIDDEN_STYLE.search(attributes):
            text = strip_tags(inner).strip()
            if text:
                style = re.search(r"style\s*=\s*[\"']([^\"']*)[\"']", attributes, re.I)
                found.append(HiddenPassage(_describe(style.group(1) if style else ""), text))

    for match in re.finditer(r"<(\w+)([^>]*\bhidden\b[^>]*)>(.*?)</\1>", html, re.DOTALL | re.I):
        text = strip_tags(match.group(3)).strip()
        if text and _HIDDEN_ATTR.search(match.group(2)):
            found.append(HiddenPassage("marked hidden", text))

    for match in _COMMENT.finditer(html):
        text = match.group(1).strip()
        if text:
            found.append(HiddenPassage("inside an HTML comment", text))

    return found


def strip_tags(html: str) -> str:
    """Plain text, for comparison and for the hidden-passage summaries."""
    without_tags = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", without_tags).strip()


def sanitize(html: str) -> str:
    """Reduce the message to an allowlist of harmless tags.

    Uses a vetted sanitiser when one is installed rather than a regular expression, because
    hand-rolled HTML filtering is a well-trodden way to ship an XSS hole. The fallback
    strips every tag, which is safe but plain.
    """
    try:
        import nh3

        return nh3.clean(
            html,
            tags=set(ALLOWED_TAGS),
            attributes={k: set(v) for k, v in ALLOWED_ATTRIBUTES.items()},
            link_rel="noopener noreferrer",
        )
    except ImportError:
        # No sanitiser available: show text only. Degrading to plain is acceptable;
        # degrading to unsanitised markup would not be.
        return strip_tags(html)


def render_email(html: str) -> SafeRender:
    """Sanitise a message and report what the sender hid inside it."""
    hidden = find_hidden(html)
    return SafeRender(html=sanitize(html), hidden=hidden)
