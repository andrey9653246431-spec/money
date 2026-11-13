from __future__ import annotations

import smtplib
from email.message import EmailMessage

try:
    from .config import Config
except ImportError:  # Direct execution
    from config import Config


def send_email(
    config: Config, subject: str, text: str, filename: str | None = None, content: str | None = None
) -> bool:
    """Отправка списка покупок на email. Работает только при заданных SMTP_*."""
    if not config.email_configured:
        return False
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config.smtp_from
    message["To"] = config.smtp_to
    message.set_content(text)
    if filename and content is not None:
        message.add_attachment(
            content.encode("utf-8"),
            maintype="text",
            subtype="plain",
            filename=filename,
        )
    with smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=30) as smtp:
        smtp.login(config.smtp_user, config.smtp_pass)
        smtp.send_message(message)
    return True
