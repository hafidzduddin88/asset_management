# SendGrid Email Setup Guide

## Overview
Sistem sekarang bisa send password reset emails via SendGrid.

## Setup Steps

### 1. Create SendGrid Account
1. Go to https://sendgrid.com
2. Sign up for free account
3. Verify email

### 2. Get API Key
1. Login to SendGrid Dashboard
2. Go to Settings → API Keys
3. Create New API Key
4. Copy the key (save it safely)

### 3. Verify Sender Email
1. Go to Settings → Sender Authentication
2. Verify your domain or single sender email
3. Use verified email as SENDGRID_FROM_EMAIL

### 4. Set Environment Variables

Add to `.env` file:
```bash
SENDGRID_API_KEY=SG.xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
SENDGRID_FROM_EMAIL=noreply@yourcompany.com
APP_URL=https://ambp-latest.onrender.com
```

Or set in Render.com:
1. Go to Dashboard → Your Service
2. Environment → Add Environment Variable
3. Add:
   - Key: `SENDGRID_API_KEY`
   - Value: `SG.xxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
4. Add:
   - Key: `SENDGRID_FROM_EMAIL`
   - Value: `noreply@yourcompany.com`
5. Add:
   - Key: `APP_URL`
   - Value: `https://ambp-latest.onrender.com`

### 5. Install Package
```bash
pip install sendgrid==7.0.0
```

Or update requirements.txt (already done):
```
sendgrid==7.0.0
```

### 6. Restart Application
```bash
# Local
uvicorn app.main:app --reload

# Render.com
# Auto-redeploy after pushing changes
```

## Files Created/Modified

### New Files
- `app/utils/email_service.py` - Email sending utility

### Modified Files
- `requirements.txt` - Added sendgrid package
- `app/routes/forgot_password.py` - Added email sending calls

## Email Templates

### Password Reset Email
- Subject: "Password Reset Request - AMBP"
- Contains: Reset link, expiration info, security notice
- Format: HTML + Plain text

### Password Reset Confirmation Email
- Subject: "Password Reset Successful - AMBP"
- Contains: Login link, security tip
- Format: HTML + Plain text

## Testing

### Local Testing (Without SendGrid)
If SENDGRID_API_KEY not set:
- System logs: "Email sending disabled - would send to..."
- No actual email sent
- Good for development

### Production Testing (With SendGrid)
1. Set SENDGRID_API_KEY environment variable
2. Request password reset
3. Check email inbox
4. Click link in email
5. Reset password
6. Check confirmation email

### Test Email Sending
```python
from app.utils.email_service import get_email_service

email_service = get_email_service()
email_service.send_password_reset_email(
    to_email="test@example.com",
    user_name="Test User",
    reset_token="test-token-123"
)
```

## Troubleshooting

### Issue: "SENDGRID_API_KEY not set"
**Solution:** 
1. Check .env file has SENDGRID_API_KEY
2. Check Render.com environment variables
3. Restart application

### Issue: "Invalid API Key"
**Solution:**
1. Verify API key is correct
2. Check key hasn't been revoked
3. Generate new key in SendGrid dashboard

### Issue: "Email not sent"
**Solution:**
1. Check sender email is verified in SendGrid
2. Check recipient email is valid
3. Check SendGrid account has email credits
4. Check logs for error messages

### Issue: "Email goes to spam"
**Solution:**
1. Setup SPF/DKIM records (SendGrid provides)
2. Use verified domain email
3. Add unsubscribe link (optional)
4. Check email content for spam triggers

## Email Flow

### Password Reset Request
```
1. User submit email at /forgot-password/
   ↓
2. System generate token
   ↓
3. System send email via SendGrid
   ↓
4. User receive email with reset link
   ↓
5. User click link
   ↓
6. User reset password
```

### Password Reset Confirmation
```
1. User submit new password
   ↓
2. System update password
   ↓
3. System send confirmation email
   ↓
4. User receive confirmation
```

## Security Notes

✅ API key stored in environment variables (not in code)
✅ Email addresses validated before sending
✅ Reset links expire after 24 hours
✅ One-time use tokens
✅ Audit logging for all reset attempts
✅ HTML + Plain text emails for compatibility

## Cost

SendGrid Free Plan:
- 100 emails/day
- Unlimited contacts
- Basic features

Perfect for small to medium deployments!

## Alternative Email Services

If not using SendGrid:
- **AWS SES** - AWS ecosystem
- **Mailgun** - Developer friendly
- **Postmark** - Transactional emails
- **Brevo (Sendinblue)** - Free tier available

## Commit Message

```
feat: add SendGrid email integration for password reset

- Create email_service.py utility for sending emails
- Add password reset email template (HTML + plain text)
- Add password reset confirmation email template
- Send email after password reset request
- Send confirmation email after successful reset
- Add SENDGRID_API_KEY and SENDGRID_FROM_EMAIL env vars
- Add sendgrid package to requirements.txt
- Graceful fallback when API key not set (logs instead)
```
