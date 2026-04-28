# app/utils/email_service.py
import os
import logging
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content

logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        self.sendgrid_api_key = os.getenv("SENDGRID_API_KEY")
        self.from_email = os.getenv("SENDGRID_FROM_EMAIL", "noreply@ambp.com")
        self.app_url = os.getenv("APP_URL", "http://localhost:8000")
        
        if not self.sendgrid_api_key:
            logger.warning("SENDGRID_API_KEY not set - email sending disabled")
    
    def send_password_reset_email(self, to_email: str, user_name: str, reset_token: str) -> bool:
        """Send password reset email with link."""
        if not self.sendgrid_api_key:
            logger.warning(f"Email sending disabled - would send to {to_email}")
            return False
        
        try:
            reset_link = f"{self.app_url}/forgot-password/reset/{reset_token}"
            
            subject = "Password Reset Request - AMBP"
            
            html_content = f"""
            <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                        <h2 style="color: #2563eb;">Password Reset Request</h2>
                        
                        <p>Hi {user_name},</p>
                        
                        <p>We received a request to reset your password for your AMBP account. If you didn't make this request, you can ignore this email.</p>
                        
                        <p>To reset your password, click the button below:</p>
                        
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="{reset_link}" style="background-color: #2563eb; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                                Reset Password
                            </a>
                        </div>
                        
                        <p>Or copy and paste this link in your browser:</p>
                        <p style="word-break: break-all; background-color: #f3f4f6; padding: 10px; border-radius: 5px;">
                            {reset_link}
                        </p>
                        
                        <p style="color: #666; font-size: 14px;">
                            <strong>Note:</strong> This link will expire in 24 hours.
                        </p>
                        
                        <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 30px 0;">
                        
                        <p style="color: #666; font-size: 12px;">
                            If you have any questions, please contact support.<br>
                            <strong>AMBP - Asset Management Business Platform</strong>
                        </p>
                    </div>
                </body>
            </html>
            """
            
            text_content = f"""
Password Reset Request

Hi {user_name},

We received a request to reset your password for your AMBP account. If you didn't make this request, you can ignore this email.

To reset your password, visit this link:
{reset_link}

This link will expire in 24 hours.

If you have any questions, please contact support.

AMBP - Asset Management Business Platform
            """
            
            message = Mail(
                from_email=Email(self.from_email),
                to_emails=To(to_email),
                subject=subject,
                plain_text_content=Content("text/plain", text_content),
                html_content=Content("text/html", html_content)
            )
            
            sg = SendGridAPIClient(self.sendgrid_api_key)
            response = sg.send(message)
            
            if response.status_code in [200, 201, 202]:
                logger.info(f"Password reset email sent to {to_email}")
                return True
            else:
                logger.error(f"Failed to send email to {to_email}: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending password reset email to {to_email}: {str(e)}")
            return False
    
    def send_password_reset_confirmation_email(self, to_email: str, user_name: str) -> bool:
        """Send password reset confirmation email."""
        if not self.sendgrid_api_key:
            logger.warning(f"Email sending disabled - would send confirmation to {to_email}")
            return False
        
        try:
            subject = "Password Reset Successful - AMBP"
            
            html_content = f"""
            <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                        <h2 style="color: #16a34a;">Password Reset Successful</h2>
                        
                        <p>Hi {user_name},</p>
                        
                        <p>Your password has been successfully reset. You can now login to your AMBP account with your new password.</p>
                        
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="{self.app_url}/login" style="background-color: #16a34a; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                                Go to Login
                            </a>
                        </div>
                        
                        <p style="color: #666; font-size: 14px;">
                            <strong>Security Tip:</strong> If you didn't reset your password, please contact support immediately.
                        </p>
                        
                        <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 30px 0;">
                        
                        <p style="color: #666; font-size: 12px;">
                            If you have any questions, please contact support.<br>
                            <strong>AMBP - Asset Management Business Platform</strong>
                        </p>
                    </div>
                </body>
            </html>
            """
            
            text_content = f"""
Password Reset Successful

Hi {user_name},

Your password has been successfully reset. You can now login to your AMBP account with your new password.

Go to login: {self.app_url}/login

Security Tip: If you didn't reset your password, please contact support immediately.

If you have any questions, please contact support.

AMBP - Asset Management Business Platform
            """
            
            message = Mail(
                from_email=Email(self.from_email),
                to_emails=To(to_email),
                subject=subject,
                plain_text_content=Content("text/plain", text_content),
                html_content=Content("text/html", html_content)
            )
            
            sg = SendGridAPIClient(self.sendgrid_api_key)
            response = sg.send(message)
            
            if response.status_code in [200, 201, 202]:
                logger.info(f"Password reset confirmation email sent to {to_email}")
                return True
            else:
                logger.error(f"Failed to send confirmation email to {to_email}: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending confirmation email to {to_email}: {str(e)}")
            return False

# Singleton instance
email_service = EmailService()

def get_email_service() -> EmailService:
    return email_service
