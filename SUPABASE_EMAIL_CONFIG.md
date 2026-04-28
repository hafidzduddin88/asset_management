# Supabase Email Configuration Guide

## Overview
Menggunakan Supabase built-in email service untuk send password reset emails.

## Setup Steps

### 1. Configure Supabase Email Settings

Di Supabase Dashboard:
1. Go to **Project Settings** → **Email**
2. Choose email provider:
   - **Supabase (Default)** - Free, limited to 4 emails/hour
   - **Custom SMTP** - Your own email server
   - **SendGrid** - Third-party service

### 2. Configure Recovery Email Template

Di Supabase Dashboard:
1. Go to **Authentication** → **Email Templates**
2. Click **Recovery** template
3. Update **Redirect URL** to:
   ```
   https://ambp-latest.onrender.com/auth/recovery
   ```

### 3. Test Email Configuration

Di Supabase Dashboard:
1. Go to **Authentication** → **Users**
2. Find a test user
3. Click **...** → **Reset Password**
4. Check email for recovery link

### 4. Customize Email Template (Optional)

Di Supabase Dashboard:
1. Go to **Authentication** → **Email Templates**
2. Click **Recovery** template
3. Edit HTML/text content
4. Add your branding, logo, etc.

## Email Template Variables

Available variables in Supabase email templates:
- `{{ .ConfirmationURL }}` - Password reset link
- `{{ .Email }}` - User email
- `{{ .SiteURL }}` - Your site URL
- `{{ .Data.* }}` - Custom data

## Password Reset Flow

```
1. User request reset at /forgot-password/
   ↓
2. System call supabase.auth.admin.reset_password_for_email(email)
   ↓
3. Supabase send recovery email
   ↓
4. Email contains link: https://ambp-latest.onrender.com/auth/recovery?token=...&type=recovery
   ↓
5. User click link
   ↓
6. Redirect to /auth/recovery endpoint
   ↓
7. Show reset password form
   ↓
8. User submit new password
   ↓
9. System verify token & update password
   ↓
10. Success page
```

## Configuration Files

### Middleware (app/middleware/session_auth.py)
```python
SKIP_PATHS = {
    "/login", "/signup", "/health", "/favicon.ico",
    "/auth/callback", "/auth/confirm", "/auth/refresh", "/auth/recovery"
}

SKIP_PREFIXES = {"/static", "/forgot-password", "/auth/forgot-password"}
```

### Routes (app/routes/forgot_password.py)
```python
# Request password reset
supabase.auth.admin.reset_password_for_email(email)

# Log the request
supabase.table("user_management_logs").insert({...}).execute()
```

### Routes (app/routes/auth.py)
```python
# Handle recovery link
supabase.auth.verify_otp({
    "token": token,
    "type": "recovery"
})

# Update password
supabase.auth.admin.update_user_by_id(user_id, {"password": password})
```

## Email Providers

### Supabase (Default)
- **Pros**: Free, no setup needed, included
- **Cons**: Limited to 4 emails/hour
- **Best for**: Development, small deployments

### Custom SMTP
- **Pros**: Full control, unlimited emails
- **Cons**: Need to configure SMTP server
- **Best for**: Production with high volume

### SendGrid
- **Pros**: Reliable, good deliverability
- **Cons**: Requires SendGrid account
- **Best for**: Production deployments

## Testing

### Test 1: Request Password Reset
```bash
1. Go to http://localhost:8000/forgot-password/
2. Enter email: m.hafidz@tog.co.id
3. Click "Send Reset Link"
4. Check email inbox
5. Should receive recovery email
```

### Test 2: Click Recovery Link
```bash
1. Open email
2. Click "Reset Password" link
3. Should redirect to /auth/recovery?token=...&type=recovery
4. Should show reset password form
```

### Test 3: Reset Password
```bash
1. Enter new password
2. Confirm password
3. Click "Reset Password"
4. Should see success page
5. Login with new password
```

### Test 4: Invalid Token
```bash
1. Go to /auth/recovery?token=invalid&type=recovery
2. Should show error
3. Should redirect to /forgot-password/
```

## Troubleshooting

### Issue: Email not received
**Solution:**
1. Check Supabase email settings configured
2. Check recovery template redirect URL
3. Check email provider settings
4. Check spam folder

### Issue: "Invalid recovery request"
**Solution:**
1. Check token parameter is passed
2. Check type=recovery parameter
3. Check URL format is correct

### Issue: "Failed to verify token"
**Solution:**
1. Check token is valid
2. Check token hasn't expired (24 hours)
3. Check token hasn't been used already

### Issue: "Email link is invalid or has expired"
**Solution:**
1. Token expired - request new reset
2. Token already used - request new reset
3. Check Supabase email settings

## Production Checklist

- [ ] Configure Supabase email provider
- [ ] Update recovery email template redirect URL
- [ ] Test password reset flow
- [ ] Test with real email
- [ ] Check email deliverability
- [ ] Monitor error logs
- [ ] Test on mobile & desktop
- [ ] Test with expired tokens
- [ ] Verify audit logs created

## Environment Variables

No additional environment variables needed!

Supabase handles everything via:
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`

Already configured in `.env`

## Files Modified

### Updated
- `app/routes/forgot_password.py` - Use Supabase recovery email
- `app/routes/auth.py` - Handle recovery tokens
- `requirements.txt` - Removed SendGrid

### No Changes Needed
- `app/middleware/session_auth.py` - Already configured
- `app/main.py` - Already configured
- Templates - Already created

## Commit Message

```
feat: integrate Supabase email service for password reset

- Use Supabase built-in recovery email instead of custom tokens
- Call supabase.auth.admin.reset_password_for_email()
- Handle recovery tokens in /auth/recovery endpoint
- Verify OTP and update password
- Add audit logging for password reset
- Remove SendGrid dependency
- Simplify email configuration (no API keys needed)
```

## Next Steps

1. Verify Supabase email settings in dashboard
2. Update recovery email template redirect URL
3. Test password reset flow
4. Deploy to production
5. Monitor email delivery

Done! 🎉
