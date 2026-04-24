import structlog

from app.services.email_provider import send_email
from app.tasks.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_welcome_email(self, email: str, full_name: str) -> None:
    html = f"""
    <h1>Welcome, {full_name}!</h1>
    <p>Your account has been created successfully.</p>
    """

    try:
        send_email(
            to_email=email,
            subject="Welcome to Scalable User Service",
            html=html,
        )
        logger.info("send_welcome_email", email=email)
    except Exception as exc:
        logger.error("send_welcome_email_failed", email=email, error=str(exc))
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_verification_email(self, email: str, otp: str) -> None:
    html = f"""
    <h1>Verify your email</h1>
    <p>Your verification OTP is:</p>
    <h2>{otp}</h2>
    <p>This OTP will expire in 15 minutes.</p>
    """

    try:
        send_email(
            to_email=email,
            subject="Verify your email",
            html=html,
        )
        logger.info("send_verification_email", email=email)
    except Exception as exc:
        logger.error("send_verification_email_failed", email=email, error=str(exc))
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_password_reset_email(self, email: str, otp: str) -> None:
    html = f"""
    <h1>Reset your password</h1>
    <p>Your password reset OTP is:</p>
    <h2>{otp}</h2>
    <p>This OTP will expire in 15 minutes.</p>
    """

    try:
        send_email(
            to_email=email,
            subject="Reset your password",
            html=html,
        )
        logger.info("send_password_reset_email", email=email)
    except Exception as exc:
        logger.error("send_password_reset_email_failed", email=email, error=str(exc))
        raise self.retry(exc=exc)
