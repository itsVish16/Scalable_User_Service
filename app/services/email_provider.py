import logging

import resend

from app.config import settings

logger = logging.getLogger(__name__)

resend.api_key = settings.resend_api_key


def send_email(to_email: str, subject: str, html: str) -> dict | None:
    try:
        response = resend.Emails.send(
            {
                "from": settings.email_from,
                "to": [to_email],
                "subject": subject,
                "html": html,
            }
        )
        return response
    except Exception as e:
        logger.error("Failed to send email to %s: %s", to_email, e)
        raise
