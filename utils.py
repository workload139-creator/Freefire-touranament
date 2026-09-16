# utils.py

import os
import random
import hashlib
import smtplib
import logging

from email.message import EmailMessage
from datetime import datetime, timedelta


# -------------------------
# LOGGING
# -------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# -------------------------
# OTP GENERATOR
# -------------------------

def generate_otp():
    """6 digit OTP generate करें."""
    return str(random.randint(100000, 999999))


# -------------------------
# OTP HASH
# -------------------------

def hash_otp(otp):
    """OTP को hash करें."""
    return hashlib.sha256(
        otp.encode("utf-8")
    ).hexdigest()


def verify_otp(otp, otp_hash):
    """OTP सही है या नहीं check करें."""
    if not otp_hash:
        return False

    return hash_otp(otp) == otp_hash


# -------------------------
# OTP EXPIRY
# -------------------------

def otp_expiry(minutes=10):
    """OTP expiry time बनाएं."""
    return datetime.utcnow() + timedelta(minutes=minutes)


def is_otp_expired(expiry_time):
    """Check करें कि OTP expire हुआ या नहीं."""
    if not expiry_time:
        return True

    return datetime.utcnow() > expiry_time


# -------------------------
# EMAIL OTP
# -------------------------

def send_email_otp(email, otp):
    """
    Email पर OTP भेजें.

    SMTP settings Render Environment Variables
    से ली जाएंगी.
    """

    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = os.getenv("SMTP_PORT")
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM")

    # SMTP configuration missing
    if not all([
        smtp_host,
        smtp_port,
        smtp_username,
        smtp_password,
        smtp_from
    ]):
        logger.error(
            "SMTP configuration is incomplete."
        )
        return False

    try:
        smtp_port = int(smtp_port)

        message = EmailMessage()

        message["Subject"] = "FF Tournament - Email Verification OTP"
        message["From"] = smtp_from
        message["To"] = email

        message.set_content(
            f"""
FF Tournament

Your email verification OTP is:

{otp}

This OTP will expire in 10 minutes.

If you did not create an account, you can ignore this email.

Independent community tournament platform.
"""
        )

        with smtplib.SMTP(
            smtp_host,
            smtp_port,
            timeout=20
        ) as server:

            server.starttls()

            server.login(
                smtp_username,
                smtp_password
            )

            server.send_message(message)

        logger.info(
            "Email OTP sent successfully."
        )

        return True

    except Exception as e:
        logger.exception(
            "Failed to send email OTP: %s",
            e
        )
        return False


# -------------------------
# PHONE OTP
# -------------------------

def send_phone_otp(phone, otp):
    """
    Phone OTP भेजने के लिए placeholder.

    वास्तविक SMS provider जोड़ने के बाद
    यह function SMS भेजेगा.
    """

    sms_api_url = os.getenv("SMS_API_URL")
    sms_api_key = os.getenv("SMS_API_KEY")

    if not sms_api_url or not sms_api_key:
        logger.warning(
            "SMS provider is not configured."
        )
        return False

    # अभी वास्तविक SMS API call नहीं की जा रही।
    logger.warning(
        "SMS provider configuration found, "
        "but provider integration is not implemented yet."
    )

    return False


# -------------------------
# SEND BOTH OTPs
# -------------------------

def create_otps():
    """
    Email और phone दोनों के लिए
    अलग OTP generate करें.
    """

    email_otp = generate_otp()
    phone_otp = generate_otp()

    return email_otp, phone_otp


# -------------------------
# BASIC VALIDATION
# -------------------------

def clean_text(value):
    """Input text को safely clean करें."""
    if value is None:
        return ""

    return str(value).strip()


def normalize_email(email):
    """Email को lowercase करें."""
    return clean_text(email).lower()


def normalize_phone(phone):
    """Phone में केवल digits रखें."""
    return "".join(
        character
        for character in clean_text(phone)
        if character.isdigit()
    )


def validate_email(email):
    """Basic email validation."""
    email = normalize_email(email)

    if not email:
        return False

    if "@" not in email:
        return False

    if "." not in email.split("@")[-1]:
        return False

    return True


def validate_phone(phone):
    """Basic Indian phone validation."""
    phone = normalize_phone(phone)

    return (
        len(phone) == 10
        and phone[0] in "6789"
  )
