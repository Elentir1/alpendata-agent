"""Text extraction only, inside the networkless execution sandbox."""

import base64
from html.parser import HTMLParser


class PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden, self.parts = 0, []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "svg", "noscript", "template"):
            self.hidden += 1
        if not self.hidden and tag in (
            "p",
            "div",
            "li",
            "h1",
            "h2",
            "h3",
            "tr",
            "br",
            "section",
        ):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "svg", "noscript", "template"):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def analyze(request):
    raw = base64.b64decode(request["content_base64"], validate=True)
    if len(raw) > 1024 * 1024:
        raise ValueError("Page too large")
    text = raw.decode("utf-8", errors="replace")
    if request["media_type"] == "text/html":
        parser = PageText()
        parser.feed(text)
        text = "".join(parser.parts)
    lines = [" ".join(line.split()) for line in text.replace("\x00", "").splitlines()]
    text = "\n".join(line for line in lines if line)
    return {"text": text[:60000], "partial": len(text) > 60000}
