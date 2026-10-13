import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from pathlib import Path
from typing import Union

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def sanitize_filename(name: str) -> str:
    """Creates a filesystem and header-safe filename."""
    return "".join(c if (c.isalnum() or c in ("-", "_")) else "_" for c in name)


def send_certificate_email(
    recipient_name: str,
    recipient_email: str,
    course_name: str,
    pdf_content: Union[bytes, str, Path],
    issue_date: str | None = None,
    raise_on_error: bool = False,
) -> bool:
    """
    Dispatches a personalized email with the generated certificate PDF attached
    using Python's built-in smtplib.

    Supports standard SMTP, SendGrid (smtp.sendgrid.net), and Gmail (smtp.gmail.com).

    :param recipient_name: Full name of the certificate recipient.
    :param recipient_email: Destination email address.
    :param course_name: Name of the course or credential.
    :param pdf_content: PDF binary data as bytes, or a local file path.
    :param issue_date: Date certificate was issued (for template interpolation).
    :param raise_on_error: If True, re-raises any caught SMTP/network exception.
    :return: True if sent successfully, False if disabled or failed.
    """
    if not settings.email_enabled:
        logger.debug(
            "Email dispatch disabled in settings, skipping delivery",
            recipient=recipient_email,
            course_name=course_name,
        )
        return False

    if not recipient_email or "@" not in recipient_email:
        logger.warning(
            "Invalid recipient email address for dispatch",
            recipient=recipient_email,
            course_name=course_name,
        )
        if raise_on_error:
            raise ValueError(f"Invalid email address: {recipient_email}")
        return False

    # 1. Resolve PDF bytes
    if isinstance(pdf_content, (str, Path)):
        pdf_path = Path(pdf_content)
        if not pdf_path.is_file():
            logger.error(
                "PDF certificate file not found for email dispatch",
                file_path=str(pdf_path),
                recipient=recipient_email,
            )
            if raise_on_error:
                raise FileNotFoundError(f"PDF file not found: {pdf_path}")
            return False
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
    elif isinstance(pdf_content, (bytes, bytearray)):
        pdf_bytes = bytes(pdf_content)
    else:
        logger.error(
            "Unsupported pdf_content type",
            type=type(pdf_content).__name__,
            recipient=recipient_email,
        )
        if raise_on_error:
            raise TypeError("pdf_content must be bytes or a valid file path")
        return False

    display_date = issue_date or formatdate(localtime=True)
    sender_header = (
        f"{settings.email_from_name} <{settings.email_from}>"
        if settings.email_from_name
        else settings.email_from
    )

    # 2. Build MIME Email Message
    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"Your Certificate of Completion: {course_name}"
    msg["From"] = sender_header
    msg["To"] = recipient_email
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()

    # Alternate body (Plain Text + Rich HTML)
    body_container = MIMEMultipart("alternative")

    plain_text = (
        f"Dear {recipient_name},\n\n"
        f"Congratulations on successfully completing {course_name}!\n\n"
        f"Your official Certificate of Completion (issued on {display_date}) "
        f"is attached to this email as a PDF document.\n\n"
        f"Best regards,\n"
        f"{settings.email_from_name or 'CertifyFlow Team'}\n"
    )
    body_container.attach(MIMEText(plain_text, "plain", "utf-8"))

    html_text = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
          background-color: #f8fafc;
          color: #1e293b;
          margin: 0;
          padding: 24px;
        }}
        .card {{
          max-width: 580px;
          margin: 0 auto;
          background: #ffffff;
          border-radius: 12px;
          border: 1px solid #e2e8f0;
          overflow: hidden;
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
        }}
        .header {{
          background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
          color: #ffffff;
          padding: 28px 24px;
          text-align: center;
        }}
        .header h1 {{
          margin: 0;
          font-size: 22px;
          font-weight: 700;
        }}
        .content {{
          padding: 28px 24px;
          line-height: 1.6;
          font-size: 15px;
        }}
        .badge {{
          display: inline-block;
          background-color: #eef2ff;
          color: #4f46e5;
          padding: 6px 14px;
          border-radius: 9999px;
          font-weight: 600;
          font-size: 14px;
          margin: 8px 0;
        }}
        .footer {{
          border-top: 1px solid #e2e8f0;
          padding: 16px 24px;
          font-size: 12px;
          color: #94a3b8;
          text-align: center;
        }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="header">
          <h1>Certificate of Completion</h1>
        </div>
        <div class="content">
          <p>Dear <strong>{recipient_name}</strong>,</p>
          <p>Congratulations! You have successfully earned your certificate for:</p>
          <div style="text-align: center;">
            <div class="badge">{course_name}</div>
          </div>
          <p>Your official credential issued on <strong>{display_date}</strong> has been generated and is attached to this email as a PDF.</p>
          <p>Keep this document for your personal records or professional portfolio.</p>
          <p style="margin-top: 24px;">Warm regards,<br><strong>{settings.email_from_name or 'CertifyFlow Team'}</strong></p>
        </div>
        <div class="footer">
          This is an automated notification from CertifyFlow Bulk Certificate Generator.
        </div>
      </div>
    </body>
    </html>
    """
    body_container.attach(MIMEText(html_text, "html", "utf-8"))
    msg.attach(body_container)

    # 3. Attach PDF Certificate
    safe_course = sanitize_filename(course_name)
    attachment_filename = f"{safe_course}_Certificate.pdf"
    attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
    attachment.add_header(
        "Content-Disposition",
        "attachment",
        filename=attachment_filename,
    )
    msg.attach(attachment)

    # 4. Connect to SMTP server and dispatch
    try:
        logger.info(
            "Connecting to SMTP server for dispatch",
            host=settings.smtp_host,
            port=settings.smtp_port,
            use_ssl=settings.smtp_use_ssl,
            use_tls=settings.smtp_use_tls,
            recipient=recipient_email,
        )

        smtp_cls = smtplib.SMTP_SSL if settings.smtp_use_ssl else smtplib.SMTP
        with smtp_cls(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            if not settings.smtp_use_ssl and settings.smtp_use_tls:
                server.starttls()

            if settings.smtp_user and settings.smtp_password:
                server.login(settings.smtp_user, settings.smtp_password)

            server.send_message(msg)

        logger.info(
            "Successfully dispatched certificate email",
            recipient=recipient_email,
            course_name=course_name,
            attachment=attachment_filename,
        )
        return True

    except Exception as exc:
        logger.error(
            "Failed to send certificate email",
            recipient=recipient_email,
            host=settings.smtp_host,
            port=settings.smtp_port,
            error=str(exc),
        )
        if raise_on_error:
            raise
        return False
