# Supabase Recovery Integration - Complete Setup Guide

## Problem Solved
Email link dari Supabase recovery: 
```
https://dkcpkodcibiffdqupoou.supabase.co/auth/v1/verify?token=...&type=recovery&redirect_to=...
```

Sekarang redirect ke custom reset page kita, bukan error page.

## Solution Architecture

### Flow 1: User Requests Password Reset
```
1. User klik "Forgot Password" di login page
   ↓
2. Redirect ke /forgot-password/
   ↓
3. User masukkan email
   ↓
4. Sistem generate custom token & store di password_reset_tokens
   ↓
5. (Production) Send email dengan link: /forgot-password/reset/{token}
   ↓
6. User klik link & reset password
```

### Flow 2: Supabase Recovery Email (Built-in)
```
1. Admin reset password user via /user_management/reset_password/{user_id}
   ↓
2. Supabase send recovery email dengan link:
   https://dkcpkodcibiffdqupoou.supabase.co/auth/v1/verify?token=...&type=recovery&redirect_to=...
   ↓
3. Redirect ke /auth/recovery?token=...&type=recovery
   ↓
4. Sistem validate token & redirect ke /forgot-password/reset/{token}
   ↓
5. User reset password dengan custom form
   ↓
6. Success page
```

## Routes

### Public Routes (No Login Required)

**Forgot Password Flow:**
```
GET  /forgot-password/              - Request form
POST /forgot-password/request       - Submit email
GET  /forgot-password/check-email   - Confirmation
GET  /forgot-password/reset/{token} - Reset form
POST /forgot-password/reset/{token} - Submit password
GET  /forgot-password/success       - Success page
```

**Alternative paths (same routes):**
```
GET  /auth/forgot-password/
POST /auth/forgot-password/request
GET  /auth/forgot-password/check-email
GET  /auth/forgot-password/reset/{token}
POST /auth/forgot-password/reset/{token}
GET  /auth/forgot-password/success
```

**Supabase Recovery Handler:**
```
GET  /auth/recovery?token=...&type=recovery  - Handle Supabase recovery link
POST /auth/reset-password                     - Reset with Supabase token
```

## Configuration

### 1. Supabase Email Template Setup

Di Supabase Dashboard → Authentication → Email Templates

**Recovery Email Template:**
```
Ubah redirect_to dari:
https://ambp-latest.onrender.com/

Menjadi:
https://ambp-latest.onrender.com/auth/recovery
```

Atau gunakan environment variable di Supabase:
```
SITE_URL=https://ambp-latest.onrender.com/auth/recovery
```

### 2. Middleware Configuration

File: `app/middleware/session_auth.py`

```python
SKIP_PATHS = {
    "/login", "/signup", "/health", "/favicon.ico",
    "/auth/callback", "/auth/confirm", "/auth/refresh", "/auth/recovery"
}

SKIP_PREFIXES = {"/static", "/forgot-password", "/auth/forgot-password"}
```

### 3. Route Registration

File: `app/main.py`

```python
from app.routes import auth, forgot_password

app.include_router(auth.router)
app.include_router(forgot_password.router)
```

## Files Created/Modified

### New Files
- `app/routes/auth.py` - Supabase recovery handler
- `app/routes/forgot_password.py` - Custom forgot password flow
- `app/templates/templates_desktop/forgot_password/` - 4 templates
- `app/templates/templates_mobile/forgot_password/` - 4 templates
- `migrations/001_create_password_reset_tokens.sql` - DB table

### Modified Files
- `app/main.py` - Import & register auth router
- `app/middleware/session_auth.py` - Add /auth/recovery to SKIP_PATHS
- `app/templates/templates_desktop/login_logout.html` - Update forgot password link

## Database Setup

### Create password_reset_tokens Table

Run di Supabase SQL Editor:

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

## User Flows

### Scenario 1: User Forgot Password (Self-Service)

```
1. User di login page
2. Klik "Forgot Password?" link
3. Redirect ke /forgot-password/
4. Masukkan email: m.hafidz@tog.co.id
5. Klik "Send Reset Link"
6. Lihat "Check your email" page
7. (Production) Terima email dengan link
8. Klik link di email
9. Masukkan password baru
10. Klik "Reset Password"
11. Lihat success page
12. Login dengan password baru
```

### Scenario 2: Admin Reset Password (Supabase Recovery)

```
1. Admin buka /user_management
2. Cari user m.hafidz@tog.co.id
3. Klik "Reset Password"
4. Supabase send recovery email ke user
5. User terima email dengan link:
   https://dkcpkodcibiffdqupoou.supabase.co/auth/v1/verify?token=...&type=recovery&redirect_to=https://ambp-latest.onrender.com/auth/recovery
6. Klik link di email
7. Redirect ke /auth/recovery?token=...&type=recovery
8. Sistem validate token & redirect ke /forgot-password/reset/{token}
9. User masukkan password baru
10. Klik "Reset Password"
11. Lihat success page
12. Login dengan password baru
```

## Security Features

✅ **Token Security**
- Secure random token generation
- 24-hour expiration
- One-time use only
- Unique per request

✅ **Password Security**
- Minimum 6 characters
- Confirmation matching
- Argon2 hashing
- No plain text storage

✅ **Email Privacy**
- Doesn't reveal if email exists
- Same message for all cases

✅ **Audit Trail**
- All reset requests logged
- All reset completions logged
- Tracks user & timestamp

## Testing

### Test Case 1: Custom Forgot Password
```bash
1. Go to http://localhost:8000/forgot-password/
2. Enter email: m.hafidz@tog.co.id
3. Click "Send Reset Link"
4. Check database: SELECT * FROM password_reset_tokens ORDER BY created_at DESC LIMIT 1;
5. Copy token from database
6. Go to http://localhost:8000/forgot-password/reset/{token}
7. Enter new password
8. Click "Reset Password"
9. Should see success page
10. Login with new password
```

### Test Case 2: Supabase Recovery
```bash
1. Go to /user_management
2. Find user m.hafidz@tog.co.id
3. Click "Reset Password"
4. Check email for recovery link
5. Click link in email
6. Should redirect to /forgot-password/reset/{token}
7. Enter new password
8. Click "Reset Password"
9. Should see success page
10. Login with new password
```

### Test Case 3: Invalid/Expired Token
```bash
1. Go to /forgot-password/reset/invalid-token
2. Should show error page
3. Go to /forgot-password/reset/expired-token
4. Should show error page
```

## Troubleshooting

### Issue: Email link shows error
**Solution:** Check Supabase email template redirect_to URL

### Issue: Token validation fails
**Solution:** Check password_reset_tokens table exists and has data

### Issue: Middleware still requires login
**Solution:** Restart application after middleware changes

### Issue: Recovery link not working
**Solution:** 
1. Check /auth/recovery route exists
2. Check middleware has /auth/recovery in SKIP_PATHS
3. Check token parameter is passed correctly

## Production Checklist

- [ ] Run SQL migration for password_reset_tokens table
- [ ] Configure Supabase email template redirect_to URL
- [ ] Set up email service (SendGrid, AWS SES, etc.)
- [ ] Test custom forgot password flow
- [ ] Test Supabase recovery flow
- [ ] Verify audit logs are created
- [ ] Test on mobile & desktop
- [ ] Test with expired tokens
- [ ] Test with invalid tokens
- [ ] Monitor error logs

## Commit Message

```
feat: integrate Supabase recovery with custom forgot password flow

- Create /auth/recovery endpoint to handle Supabase recovery links
- Support both /forgot-password and /auth/forgot-password paths
- Add Supabase token verification and password reset
- Update middleware to skip auth for recovery endpoints
- Update login page forgot password link
- Add comprehensive audit logging
- Support both custom and Supabase recovery flows
```
