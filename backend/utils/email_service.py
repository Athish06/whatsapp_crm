"""
Email service for sending OTPs and password reset emails.
"""
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from config import settings

logger = logging.getLogger(__name__)

GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587


def send_otp_email(recipient_email: str, otp: str, purpose: str = "verification") -> bool:
    """
    Send OTP email for verification or password reset.
    
    Args:
        recipient_email: Email address to send OTP to
        otp: 6-digit OTP code
        purpose: "verification" for signup or "reset" for password reset
        
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        if not settings.google_app_password or not settings.sender_email:
            logger.error("Email credentials not configured")
            return False
        
        subject = "WhatsApp CRM - Your Verification Code" if purpose == "verification" else "WhatsApp CRM - Password Reset Code"
        
        # Create email message
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = settings.sender_email
        message["To"] = recipient_email
        
        # Plain text version
        text_content = f"""
Hello,

Your OTP code for WhatsApp CRM is: {otp}

This code will expire in 10 minutes.

If you didn't request this code, please ignore this email.

Best regards,
WhatsApp CRM Team
        """
        
        # HTML version
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #121212;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #121212; padding: 20px;">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="background-color: #1C1C1C; border: 1px solid #2E2E2E; border-radius: 10px;">
                    <!-- Header -->
                    <tr>
                        <td style="background: linear-gradient(135deg, #3ECF8E 0%, #2BA56D 100%); padding: 30px; border-radius: 10px 10px 0 0;">
                            <h1 style="color: #121212; margin: 0; font-size: 28px; text-align: center; font-weight: bold;">
                                WhatsApp CRM
                            </h1>
                            <p style="color: #121212; margin: 10px 0 0 0; text-align: center; font-size: 14px; opacity: 0.9;">
                                {"Email Verification" if purpose == "verification" else "Password Reset"}
                            </p>
                        </td>
                    </tr>
                    
                    <!-- Body -->
                    <tr>
                        <td style="padding: 40px 30px;">
                            <p style="color: #FFFFFF; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                Hello,
                            </p>
                            
                            <p style="color: #CCCCCC; font-size: 16px; line-height: 1.6; margin: 0 0 30px 0;">
                                {"Use the verification code below to complete your registration:" if purpose == "verification" else "Use the code below to reset your password:"}
                            </p>
                            
                            <!-- OTP Box -->
                            <table width="100%" cellpadding="0" cellspacing="0" style="margin: 30px 0;">
                                <tr>
                                    <td align="center" style="background: linear-gradient(135deg, #3ECF8E 0%, #2BA56D 100%); padding: 30px; border-radius: 10px;">
                                        <div style="font-size: 48px; font-weight: bold; letter-spacing: 10px; color: #121212; font-family: 'Courier New', monospace;">
                                            {otp}
                                        </div>
                                    </td>
                                </tr>
                            </table>
                            
                            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #2E2E2E; border-left: 4px solid #3ECF8E; margin: 20px 0; border-radius: 5px;">
                                <tr>
                                    <td style="padding: 20px;">
                                        <p style="color: #CCCCCC; font-size: 14px; margin: 0;">
                                            ⏱️ This code will <strong style="color: #3ECF8E;">expire in 10 minutes</strong>
                                        </p>
                                        <p style="color: #CCCCCC; font-size: 14px; margin: 10px 0 0 0;">
                                            🔒 For your security, never share this code with anyone
                                        </p>
                                    </td>
                                </tr>
                            </table>
                            
                            <p style="color: #999999; font-size: 14px; line-height: 1.6; margin: 30px 0 0 0;">
                                If you didn't request this code, please ignore this email or contact support if you have concerns.
                            </p>
                        </td>
                    </tr>
                    
                    <!-- Footer -->
                    <tr>
                        <td style="background-color: #2E2E2E; padding: 20px 30px; border-radius: 0 0 10px 10px; border-top: 1px solid #3E3E3E;">
                            <p style="color: #999999; font-size: 14px; margin: 0; text-align: center;">
                                Best regards,<br>
                                <strong style="color: #3ECF8E;">WhatsApp CRM Team</strong>
                            </p>
                            <p style="color: #666666; font-size: 12px; margin: 10px 0 0 0; text-align: center;">
                                © {datetime.now().year} WhatsApp CRM. All rights reserved.
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
        """
        
        # Attach both versions
        part1 = MIMEText(text_content, "plain")
        part2 = MIMEText(html_content, "html")
        message.attach(part1)
        message.attach(part2)
        
        # Send email
        with smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT) as server:
            server.starttls()
            server.login(settings.sender_email, settings.google_app_password)
            server.sendmail(settings.sender_email, recipient_email, message.as_string())
        
        logger.info(f"OTP email sent successfully to {recipient_email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send OTP email: {str(e)}")
        return False


def send_password_changed_email(recipient_email: str, full_name: str) -> bool:
    """
    Send confirmation email after password change.
    
    Args:
        recipient_email: Email address
        full_name: User's full name
        
    Returns:
        bool: True if email sent successfully
    """
    try:
        if not settings.google_app_password or not settings.sender_email:
            logger.error("Email credentials not configured")
            return False
        
        subject = "WhatsApp CRM - Password Changed Successfully"
        
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = settings.sender_email
        message["To"] = recipient_email
        
        # Plain text
        text_content = f"""
Hello {full_name},

Your WhatsApp CRM account password has been changed successfully.

Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

If you didn't make this change, please contact support immediately.

Best regards,
WhatsApp CRM Team
        """
        
        # HTML version
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #121212;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #121212; padding: 20px;">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="background-color: #1C1C1C; border: 1px solid #2E2E2E; border-radius: 10px;">
                    <tr>
                        <td style="background: linear-gradient(135deg, #3ECF8E 0%, #2BA56D 100%); padding: 30px; border-radius: 10px 10px 0 0;">
                            <h1 style="color: #121212; margin: 0; font-size: 28px; text-align: center; font-weight: bold;">
                                Password Changed
                            </h1>
                        </td>
                    </tr>
                    
                    <tr>
                        <td style="padding: 40px 30px;">
                            <p style="color: #FFFFFF; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                Hello {full_name},
                            </p>
                            
                            <p style="color: #CCCCCC; font-size: 16px; line-height: 1.6; margin: 0 0 30px 0;">
                                Your WhatsApp CRM account password has been changed successfully.
                            </p>
                            
                            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #2E2E2E; border-left: 4px solid #3ECF8E; margin: 20px 0; border-radius: 5px;">
                                <tr>
                                    <td style="padding: 20px;">
                                        <p style="color: #CCCCCC; font-size: 14px; margin: 0;">
                                            ⏰ Time: <strong>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</strong>
                                        </p>
                                        <p style="color: #CCCCCC; font-size: 14px; margin: 10px 0 0 0;">
                                            ✅ Status: <strong style="color: #3ECF8E;">Successfully Updated</strong>
                                        </p>
                                    </td>
                                </tr>
                            </table>
                            
                            <p style="color: #FF6B6B; font-size: 14px; line-height: 1.6; margin: 30px 0 0 0;">
                                ⚠️ If you didn't make this change, please contact support immediately.
                            </p>
                        </td>
                    </tr>
                    
                    <tr>
                        <td style="background-color: #2E2E2E; padding: 20px 30px; border-radius: 0 0 10px 10px; border-top: 1px solid #3E3E3E;">
                            <p style="color: #999999; font-size: 14px; margin: 0; text-align: center;">
                                Best regards,<br>
                                <strong style="color: #3ECF8E;">WhatsApp CRM Team</strong>
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
        """
        
        part1 = MIMEText(text_content, "plain")
        part2 = MIMEText(html_content, "html")
        message.attach(part1)
        message.attach(part2)
        
        with smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT) as server:
            server.starttls()
            server.login(settings.sender_email, settings.google_app_password)
            server.sendmail(settings.sender_email, recipient_email, message.as_string())
        
        logger.info(f"Password change confirmation sent to {recipient_email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send password change email: {str(e)}")
        return False
