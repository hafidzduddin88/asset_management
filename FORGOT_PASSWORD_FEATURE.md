# Forgot Password Feature - Implementation Guide

## Overview
Public forgot password page yang memungkinkan user untuk reset password tanpa perlu login.

## Features
✅ Public forgot password page (tidak perlu login)
✅ Email validation
✅ Secure reset token generation
✅ Token expiration (24 hours)
✅ One-time use tokens
✅ Audit logging
✅ Mobile & desktop responsive

## Routes

### Public Routes (No Login Required)
```
GET  /forgot-password/              - Forgot password form
POST /forgot-password/request       - Request password reset
GET  /forgot-password/check-email   - Check email confirmation page
GET  /forgot-password/reset/{token} - Reset password form with token
POST /forgot-password/reset/{token} - Submit new password
GET  /forgot-password/success       - Success confirmation page
```

## Database Setup

### 1. Create password_reset_tokens Table
Run SQL migration in Supabase:
```sql
-- File: migrations/001_create_password_reset_tokens.sql
```

Or manually in Supabase SQL Editor:
```sql
CREATE TABLE password_reset_tokens (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    token TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    used BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_password_reset_tokens_token ON password_reset_tokens(token);
CREATE INDEX idx_password_reset_tokens_user_id ON password_reset_tokens(user_id);
CREATE INDEX idx_password_reset_tokens_expires_at ON password_reset_tokens(expires_at);
```

## User Flow

### Step 1: Request Password Reset
```
User clicks "Forgot Password" on login page
    ↓
User enters email address
    ↓
System checks if email exists
    ↓
System generates secure token (24 hour expiry)
    ↓
System stores token in password_reset_tokens table
    ↓
User sees "Check your email" page
```

### Step 2: Reset Password
```
User receives email with reset link
    ↓
User clicks link: /forgot-password/reset/{token}
    ↓
System validates token (not expired, not used)
    ↓
User enters new password
    ↓
System updates password in Supabase Auth
    ↓
System marks token as used
    ↓
User sees success page
    ↓
User can login with new password
```

## Configuration

### Middleware Update
File: `app/middleware/session_auth.py`

Added `/forgot-password` to SKIP_PREFIXES:
```python
SKIP_PREFIXES = {"/static", "/forgot-password"}
```

This allows all forgot-password routes to be accessed without login.

### Route Registration
File: `app/main.py`

Added forgot_password router:
```python
from app.routes import forgot_password
app.include_router(forgot_password.router)
```

## Security Features

✅ **Token Security**
- Secure random token generation (secrets.token_urlsafe)
- Unique tokens per request
- 24-hour expiration
- One-time use only

✅ **Email Privacy**
- Doesn't reveal if email exists (security best practice)
- Same message for existing and non-existing emails

✅ **Password Validation**
- Minimum 6 characters
- Confirmation password matching
- Hashed with Argon2 before storage

✅ **Audit Trail**
- All password reset requests logged
- All password reset completions logged
- Tracks admin_id (None for user-initiated resets)

## Templates

### Desktop Templates
- `templates_desktop/forgot_password/index.html` - Request form
- `templates_desktop/forgot_password/check_email.html` - Confirmation
- `templates_desktop/forgot_password/reset.html` - Reset form
- `templates_desktop/forgot_password/success.html` - Success page

### Mobile Templates
- `templates_mobile/forgot_password/index.html` - Request form
- `templates_mobile/forgot_password/check_email.html` - Confirmation
- `templates_mobile/forgot_password/reset.html` - Reset form
- `templates_mobile/forgot_password/success.html` - Success page

## Error Handling

### Token Validation Errors
- Invalid token → 404 error
- Expired token → 400 error
- Already used token → 400 error

### Password Validation Errors
- Passwords don't match → Show error on form
- Password too short → Show error on form
- Database error → Redirect to forgot-password with error

## Future Enhancements

1. **Email Integration**
   - Send actual reset email with link
   - Email templates
   - Email service integration (SendGrid, AWS SES, etc.)

2. **Rate Limiting**
   - Limit password reset requests per email
   - Prevent brute force attacks

3. **SMS Option**
   - SMS-based password reset
   - OTP verification

4. **Password Requirements**
   - Stronger password validation
   - Password complexity rules
   - Password history

## Testing

### Test Cases
1. Request reset with valid email
2. Request reset with invalid email
3. Click reset link with valid token
4. Click reset link with expired token
5. Click reset link with already used token
6. Reset password with mismatched passwords
7. Reset password with short password
8. Successful password reset and login

### Manual Testing
```bash
# 1. Go to forgot password page
http://localhost:8000/forgot-password/

# 2. Enter email
m.hafidz@tog.co.id

# 3. Check database for token
SELECT * FROM password_reset_tokens WHERE user_id = 'user_id' ORDER BY created_at DESC LIMIT 1;

# 4. Use token in URL
http://localhost:8000/forgot-password/reset/{token}

# 5. Enter new password and confirm
# 6. Should redirect to success page
# 7. Login with new password
```

## Troubleshooting

### Issue: "Invalid reset token"
- Token doesn't exist in database
- Token was already used
- Check password_reset_tokens table

### Issue: "Reset token expired"
- Token is older than 24 hours
- Check expires_at timestamp

### Issue: Middleware still requires login
- Ensure `/forgot-password` is in SKIP_PREFIXES
- Restart application

### Issue: Database table not found
- Run SQL migration in Supabase
- Check table exists: `SELECT * FROM password_reset_tokens LIMIT 1;`

## Files Modified/Created

### New Files
- `app/routes/forgot_password.py` - Route handlers
- `app/templates/templates_desktop/forgot_password/` - Desktop templates
- `app/templates/templates_mobile/forgot_password/` - Mobile templates
- `migrations/001_create_password_reset_tokens.sql` - Database migration

### Modified Files
- `app/middleware/session_auth.py` - Added /forgot-password to SKIP_PREFIXES
- `app/main.py` - Imported and registered forgot_password router

## Commit Message
```
feat: add public forgot password workflow with secure token-based reset

- Create public forgot password page (no login required)
- Implement secure token generation and validation
- Add 24-hour token expiration
- Add one-time use token enforcement
- Create password_reset_tokens table with RLS
- Add audit logging for password reset requests/completions
- Create responsive desktop and mobile templates
- Update middleware to skip authentication for /forgot-password routes
```
