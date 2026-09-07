"""Fixed Infomaniak endpoints; SMTP attempts are never retried automatically."""

import email.policy
import imaplib
import smtplib
import ssl
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import formatdate, parseaddr
from html.parser import HTMLParser

from fastapi import HTTPException


class MailText(HTMLParser):
    """Extract display text only; never render HTML or fetch remote email assets."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "head"}:
            self.hidden.append(tag)
        elif not self.hidden and tag in {"p", "br", "div", "li", "tr", "h1", "h2"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.hidden and tag == self.hidden[-1]:
            self.hidden.pop()

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def message_text(parsed):
    part = parsed.get_body(preferencelist=("plain", "html")) if parsed.is_multipart() else parsed
    if part is None or part.get_content_type() not in {"text/plain", "text/html"}:
        return ""
    try:
        content = part.get_content()
    except (LookupError, UnicodeError):
        content = (part.get_payload(decode=True) or b"").decode("utf-8", errors="replace")
    if part.get_content_type() == "text/html":
        parser = MailText()
        parser.feed(content)
        return "".join(parser.parts).strip()
    return content


class InfomaniakMail:
    def mailbox(self, credentials):
        mailbox = imaplib.IMAP4_SSL(
            "mail.infomaniak.com", port=993, ssl_context=ssl.create_default_context(), timeout=20
        )
        try:
            mailbox.login(credentials["email"], credentials["password"])
            if mailbox.select("INBOX", readonly=True)[0] != "OK":
                raise imaplib.IMAP4.error("Mailbox unavailable")
            return mailbox
        except Exception:
            mailbox.shutdown()
            raise

    def verify(self, credentials):
        try:
            mailbox = self.mailbox(credentials)
            mailbox.logout()
        except (OSError, imaplib.IMAP4.error):
            raise HTTPException(409, "infomaniak_connection_failed") from None

    def read(self, credentials, query=""):
        try:
            mailbox = self.mailbox(credentials)
            try:
                if query:
                    escaped = query.replace("\\", "\\\\").replace('"', '\\"')
                    status, found = mailbox.uid(
                        "search", "UTF-8", "TEXT", ('"' + escaped + '"').encode("utf-8")
                    )
                else:
                    status, found = mailbox.uid("search", None, "ALL")
                if status != "OK":
                    raise imaplib.IMAP4.error("Search unavailable")
                messages = []
                for identifier in (found[0] or b"").split()[-20:][::-1]:
                    # PEEK and read-only selection never mark the customer's mail as read.
                    status, rows = mailbox.uid("fetch", identifier, "(BODY.PEEK[]<0.65536>)")
                    if status != "OK":
                        continue
                    raw = next((row[1] for row in rows if isinstance(row, tuple)), b"")
                    parsed = BytesParser(policy=email.policy.default).parsebytes(raw)
                    text = message_text(parsed)
                    name, address = parseaddr(str(parsed.get("From", "")))
                    messages.append(
                        {
                            "id": identifier.decode("ascii"),
                            "subject": str(parsed.get("Subject", "")),
                            "sender": name,
                            "sender_address": address,
                            "received_at": str(parsed.get("Date", "")),
                            "preview": str(text)[:8000],
                            "url": "https://mail.infomaniak.com/",
                            "truncated": len(raw) >= 65536,
                            "message_id": str(parsed.get("Message-ID", "")),
                        }
                    )
                return {"messages": messages}
            finally:
                mailbox.logout()
        except (OSError, imaplib.IMAP4.error, ValueError):
            raise HTTPException(502, "infomaniak_read_failed") from None

    def send(self, credentials, message, files, correlation_id):
        outgoing = EmailMessage()
        outgoing["From"] = credentials["email"]
        outgoing["To"] = ", ".join(message["to"])
        if message["cc"]:
            outgoing["Cc"] = ", ".join(message["cc"])
        outgoing["Subject"] = message["subject"]
        outgoing["Date"] = formatdate(localtime=False)
        outgoing["Message-ID"] = f"<{correlation_id}@alpendata.ch>"
        outgoing["X-Alpendata-Message-Id"] = correlation_id
        outgoing.set_content(message["body"])
        for filename, media_type, content in files:
            maintype, subtype = media_type.split("/", 1)
            outgoing.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)
        admitted = False
        try:
            with smtplib.SMTP("mail.infomaniak.com", 587, timeout=20) as smtp:
                smtp.ehlo()
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
                smtp.login(credentials["email"], credentials["password"])
                admitted = True
                refused = smtp.send_message(
                    outgoing,
                    from_addr=credentials["email"],
                    to_addrs=message["to"] + message["cc"] + message["bcc"],
                )
                if refused:
                    # Some recipients may have received it. Never resend the group.
                    raise HTTPException(502, "email_send_unknown")
        except smtplib.SMTPAuthenticationError:
            raise HTTPException(409, "infomaniak_connection_failed") from None
        except smtplib.SMTPRecipientsRefused:
            raise HTTPException(409, "email_send_rejected") from None
        except (smtplib.SMTPException, OSError):
            raise HTTPException(
                502 if admitted else 409, "email_send_unknown" if admitted else "infomaniak_connection_failed"
            ) from None
