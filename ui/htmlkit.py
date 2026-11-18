"""Small HTML pieces for the chat. Every piece of text goes through `esc` first.

The pieces are built as one line with no blank lines, because the markdown parser would
treat indented or blank-line-separated HTML as code. Text from documents or from the model
is never trusted: it is escaped here, so it can show as text but never act as markup.
"""

import html

from ui import format as fmt

EXAMPLES = [
    "What are the support hours?",
    "Which customer case studies are in the documents?",
    "Is the ISO 27001 certificate current?",
]


def esc(value: object) -> str:
    """Escape text for placing between tags. Also stops markdown maths ($) and :emoji: codes."""
    text = html.escape("" if value is None else str(value), quote=True)
    text = text.replace("$", "&#36;").replace(":", "&#58;")
    return text.replace("\r", "").replace("\n", "<br>")


def esc_attr(value: object) -> str:
    return esc(value).replace("<br>", " ")


def user_bubble(text: str) -> str:
    return (
        '<div class="msg-user">'
        f'<div class="bubble-user">{esc(text)}</div>'
        '<div class="avatar avatar-user">\U0001f9d1</div>'
        "</div>"
    )


def _chips(sources: list[dict]) -> str:
    if not sources:
        return ""
    count = len(sources)
    parts = [f'<span class="based">Based on {count} passage{"s" if count != 1 else ""}</span>']
    for source in sources:
        quote = (source.get("quote") or "")[:220]
        parts.append(
            f'<span class="src-chip" title="{esc_attr(quote)}">'
            f"\U0001f4c4 {esc(fmt.doc_label(source))}</span>"
        )
    return '<div class="chips">' + "".join(parts) + "</div>"


def _card(kind: str, inner: str) -> str:
    return (
        '<div class="msg-ai"><div class="avatar avatar-ai">\U0001f6e1️</div>'
        f'<div class="card-answer {kind}">{inner}</div></div>'
    )


def assistant_message(status: str, text: str, sources: list[dict], redacted: bool = False) -> str:
    if status == "no_answer":
        return _card(
            "notice-info",
            '<div class="ans-head">I could not find this in the documents available to you.</div>'
            '<div class="ans-para">Try naming the document or topic, or ask about one specific '
            "fact.</div>",
        )
    if status == "error":
        return _card(
            "notice-warn",
            '<div class="ans-head">I could not answer this time.</div>'
            '<div class="ans-para">Please try again in a moment.</div>',
        )
    headline, bullets, other = fmt.split_answer(text)
    inner = f'<div class="ans-head">{esc(headline)}</div>'
    inner += "".join(f'<div class="ans-para">{esc(line)}</div>' for line in other)
    if bullets:
        inner += '<ul class="ans-list">' + "".join(f"<li>{esc(b)}</li>" for b in bullets) + "</ul>"
    if redacted:
        inner += (
            '<div class="ans-para muted">'
            "A source for this answer is no longer available to you.</div>"
        )
    return _card("", inner + _chips(sources))
