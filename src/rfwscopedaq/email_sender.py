"""A module for managing email actions"""
from email.message import EmailMessage
import smtplib
from typing import List


# Structured this way for easy feature additions regarding types of email, etc.
# pylint: disable=too-few-public-methods
class EmailSender:
    """A class for sending emails."""
    def __init__(self, subject: str, fromaddr: str, toaddrs: List[str], smtp_server: str = 'localhost'):
        """Construct an instance with information on who to email.

        "Args:
            subject: The subject line of the email.
            fromaddr: The email address of the sender.
            toaddrs: A list of email addresses to send.
            smtp_server: The SMTP server to use.
        """
        self.subject = subject
        self.fromaddr = fromaddr
        self.toaddrs = toaddrs
        if isinstance(toaddrs, str):
            self.toaddrs = [toaddrs]
        self.smtp_server = smtp_server

    def send_txt_email(self, body: str):
        """Send a plain text email without attachments.

        Args:
            body: The plain text email body.
        """
        msg = EmailMessage()
        msg['Subject'] = self.subject
        msg['From'] = self.fromaddr
        msg['To'] = ",".join(self.toaddrs)
        msg.set_content(body)

        with smtplib.SMTP(self.smtp_server) as server:
            server.send_message(msg)
