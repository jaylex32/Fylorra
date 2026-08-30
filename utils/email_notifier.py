"""Email Notifier - Sends email notifications for file system events"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional
import ssl

from core.branding import APP_NAME, APP_TAGLINE


class EmailNotifier:
    """Handles sending email notifications via SMTP"""

    def __init__(self, smtp_settings: dict):
        """
        Initialize email notifier with SMTP settings

        Args:
            smtp_settings: Dictionary containing:
                - smtp_server: SMTP server address
                - smtp_port: SMTP port (587 for TLS)
                - smtp_username: SMTP username/email
                - smtp_password: SMTP password
                - sender_email: Sender email address
        """
        self.smtp_server = smtp_settings.get("smtp_server", "")
        self.smtp_port = smtp_settings.get("smtp_port", 587)
        self.smtp_username = smtp_settings.get("smtp_username", "")
        self.smtp_password = smtp_settings.get("smtp_password", "")
        self.sender_email = smtp_settings.get("sender_email", "")
        self.enabled = all([self.smtp_server, self.smtp_username, self.smtp_password, self.sender_email])

    def send_notification(self, recipient: str, event_type: str, file_name: str,
                         file_path: str, monitor_path: str) -> bool:
        """
        Send email notification for a file system event

        Args:
            recipient: Email address to send to
            event_type: Type of event (created, modified, deleted, moved)
            file_name: Name of the file
            file_path: Full path to the file
            monitor_path: Path being monitored

        Returns:
            True if email sent successfully, False otherwise
        """
        if not self.enabled or not recipient:
            return False

        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"{APP_NAME} Alert: File {event_type.title()}"
            msg["From"] = self.sender_email
            msg["To"] = recipient

            # Event type emoji mapping
            emoji_map = {
                "created": "📁",
                "modified": "✏️",
                "deleted": "🗑️",
                "moved": "📦"
            }
            emoji = emoji_map.get(event_type, "📂")

            # Create HTML body
            html_body = f"""
            <html>
                <head>
                    <style>
                        body {{
                            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                            line-height: 1.6;
                            color: #333;
                        }}
                        .container {{
                            max-width: 600px;
                            margin: 0 auto;
                            padding: 20px;
                            background-color: #f9f9f9;
                            border-radius: 8px;
                        }}
                        .header {{
                            background-color: #2fa572;
                            color: white;
                            padding: 20px;
                            border-radius: 8px 8px 0 0;
                            text-align: center;
                        }}
                        .content {{
                            background-color: white;
                            padding: 20px;
                            border-radius: 0 0 8px 8px;
                        }}
                        .event-details {{
                            background-color: #f5f5f5;
                            padding: 15px;
                            border-left: 4px solid #2fa572;
                            margin: 15px 0;
                        }}
                        .detail-row {{
                            margin: 8px 0;
                        }}
                        .label {{
                            font-weight: bold;
                            color: #555;
                        }}
                        .footer {{
                            text-align: center;
                            margin-top: 20px;
                            font-size: 12px;
                            color: #888;
                        }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h1>{emoji} {APP_NAME} Alert</h1>
                        </div>
                        <div class="content">
                            <h2>File {event_type.title()}</h2>
                            <div class="event-details">
                                <div class="detail-row">
                                    <span class="label">Event Type:</span> {event_type.upper()}
                                </div>
                                <div class="detail-row">
                                    <span class="label">File Name:</span> {file_name}
                                </div>
                                <div class="detail-row">
                                    <span class="label">File Path:</span> {file_path}
                                </div>
                                <div class="detail-row">
                                    <span class="label">Monitored Folder:</span> {monitor_path}
                                </div>
                                <div class="detail-row">
                                    <span class="label">Time:</span> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                                </div>
                            </div>
                            <p>This is an automated notification from {APP_NAME}.</p>
                        </div>
                        <div class="footer">
                            <p>{APP_NAME} - {APP_TAGLINE.title()}</p>
                        </div>
                    </div>
                </body>
            </html>
            """

            # Create plain text alternative
            text_body = f"""
{APP_NAME} Alert

File {event_type.title()}

Event Type: {event_type.upper()}
File Name: {file_name}
File Path: {file_path}
Monitored Folder: {monitor_path}
Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

This is an automated notification from {APP_NAME}.

---
{APP_NAME} - {APP_TAGLINE.title()}
            """

            # Attach both parts
            part1 = MIMEText(text_body, "plain")
            part2 = MIMEText(html_body, "html")
            msg.attach(part1)
            msg.attach(part2)

            # Create secure SSL context
            context = ssl.create_default_context()

            # Send email using STARTTLS
            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10) as server:
                server.ehlo()  # Identify ourselves to the server
                server.starttls(context=context)  # Upgrade to secure connection
                server.ehlo()  # Re-identify ourselves over encrypted connection
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)

            return True

        except smtplib.SMTPAuthenticationError:
            print("Email notification failed: Invalid SMTP credentials")
            return False
        except smtplib.SMTPException as e:
            print(f"Email notification failed: SMTP error - {e}")
            return False
        except Exception as e:
            print(f"Email notification failed: {e}")
            return False

    def test_connection(self) -> tuple[bool, str]:
        """
        Test SMTP connection

        Returns:
            Tuple of (success: bool, message: str)
        """
        if not self.enabled:
            return False, "SMTP settings not configured"

        try:
            context = ssl.create_default_context()
            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(self.smtp_username, self.smtp_password)
            return True, "Connection successful"
        except smtplib.SMTPAuthenticationError:
            return False, "Authentication failed - check username/password"
        except smtplib.SMTPException as e:
            return False, f"SMTP error: {str(e)}"
        except Exception as e:
            return False, f"Connection failed: {str(e)}"
