# Supabase Password Reset - Fixed Implementation

## Masalah yang Diperbaiki

### ❌ **Sebelumnya:**
```python
# Method yang salah - tidak ada di Supabase Python SDK
supabase.auth.admin.reset_password_for_email(email)
```

### ✅ **Sekarang:**
```python
# Method yang benar dengan redirect URL
supabase.auth.reset_password_for_email(
    email,
    options={
        "redirect_to": "https://ambp-latest.onrender.com/auth/recovery"
    }
)
```

---

## Perubahan yang Dilakukan

### 1. Fixed forgot_password.py

**File**: `app/routes/forgot_password.py`

**Perubahan:**
- ✅ Gunakan `supabase.auth.reset_password_for_email()` (bukan `admin.reset_password_for_email()`)
- ✅ Tambahkan `options={"redirect_to": ...}` untuk set redirect URL
- ✅ Ambil APP_URL dari environment variable
- ✅ Log redirect URL untuk debugging

**Kode:**
```python
# Get app URL from config
app_url = os.getenv("APP_URL", "http://localhost:8000")
redirect_to = f"{app_url}/auth/recovery"

# Use correct Supabase method with redirect URL
supabase.auth.reset_password_for_email(
    email,
    options={
        "redirect_to": redirect_to
    }
)

logging.info(f"Password reset email sent to {email} with redirect to {redirect_to}")
```

---

### 2. Fixed auth.py

**File**: `app/routes/auth.py`

**Perubahan:**
- ✅ Handle `access_token` parameter dari Supabase redirect
- ✅ Handle `token` dan `type=recovery` parameter
- ✅ Support 2 cara reset password:
  - Via `access_token` (recommended)
  - Via `verify_otp()` dengan token
- ✅ Create new Supabase client dengan access token untuk update password
- ✅ Better error handling

**Kode:**
```python
# If we have access_token, use it to update password
if access_token:
    # Create a new supabase client with the access token
    user_supabase = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)
    
    # Set the session with access token
    user_supabase.auth.set_session(access_token, access_token)
    
    # Update password
    response = user_supabase.auth.update_user({"password": password})
```

---

### 3. Fixed Templates

**Files**: 
- `app/templates/templates_desktop/forgot_password/reset.html`
- `app/templates/templates_mobile/forgot_password/reset.html`

**Perubahan:**
- ✅ Form action ke `/auth/reset-password` (bukan `/forgot-password/reset/{token}`)
- ✅ Tambahkan hidden fields untuk `access_token`, `token`, `type`
- ✅ Support kedua cara reset password

**Kode:**
```html
<form method="POST" action="/auth/reset-password">
    {% if access_token %}
    <input type="hidden" name="access_token" value="{{ access_token }}">
    {% endif %}
    {% if token %}
    <input type="hidden" name="token" value="{{ token }}">
    {% endif %}
    {% if type %}
    <input type="hidden" name="type" value="{{ type }}">
    {% endif %}
    <!-- password fields -->
</form>
```

---

## Flow yang Benar

### Complete Password Reset Flow:

```
1. User request reset di /forgot-password/
   ↓
2. System call: supabase.auth.reset_password_for_email(email, options={"redirect_to": "..."})
   ↓
3. Supabase send recovery email
   ↓
4. Email contains link:
   https://dkcpkodcibiffdqupoou.supabase.co/auth/v1/verify?token=...&type=recovery&redirect_to=https://ambp-latest.onrender.com/auth/recovery
   ↓
5. User click link
   ↓
6. Supabase verify token & redirect to:
   https://ambp-latest.onrender.com/auth/recovery?access_token=...&refresh_token=...&type=recovery
   ↓
7. Our app handle /auth/recovery endpoint
   ↓
8. Show reset password form with access_token
   ↓
9. User submit new password
   ↓
10. POST /auth/reset-password with access_token
   ↓
11. Create new Supabase client with access_token
   ↓
12. Call user_supabase.auth.update_user({"password": password})
   ↓
13. Password updated successfully
   ↓
14. Redirect to /forgot-password/success
   ↓
15. User login with new password
```

---

## Environment Variables

**Required:**
```bash
APP_URL=https://ambp-latest.onrender.com
```

**Untuk local development:**
```bash
APP_URL=http://localhost:8000
```

**Di Render.com:**
```
Environment → Add Environment Variable
Key: APP_URL
Value: https://ambp-latest.onrender.com
```

---

## Supabase Configuration

### 1. Email Provider
```
Project Settings → Email
Provider: Supabase (default) atau Custom SMTP
```

### 2. Recovery Email Template
```
Authentication → Email Templates → Recovery
Redirect URL: {{ .ConfirmationURL }}
(Supabase akan otomatis append redirect_to dari code)
```

### 3. Site URL
```
Project Settings → General
Site URL: https://ambp-latest.onrender.com
```

### 4. Redirect URLs
```
Authentication → URL Configuration
Add: https://ambp-latest.onrender.com/auth/recovery
```

---

## Testing

### Test 1: Request Password Reset
```bash
1. Go to /forgot-password/
2. Enter email: m.hafidz@tog.co.id
3. Click "Send Reset Link"
4. Should redirect to /forgot-password/check-email
5. Check application logs for:
   "Password reset email sent to m.hafidz@tog.co.id with redirect to https://ambp-latest.onrender.com/auth/recovery"
```

### Test 2: Check Email
```bash
1. Open email inbox
2. Look for email from Supabase
3. Subject: "Reset your password"
4. Click "Reset Password" link
```

### Test 3: Reset Password
```bash
1. Should redirect to /auth/recovery?access_token=...&refresh_token=...
2. Should show reset password form
3. Enter new password
4. Confirm password
5. Click "Reset Password"
6. Should redirect to /forgot-password/success
7. Login with new password
```

### Test 4: Check Logs
```bash
# Application logs should show:
INFO:root:Password reset email sent to m.hafidz@tog.co.id with redirect to https://ambp-latest.onrender.com/auth/recovery
INFO:root:Password reset completed for user <user_id>

# Supabase logs should show:
Email sent to m.hafidz@tog.co.id - Status: sent
```

---

## Troubleshooting

### Issue: Email tidak terkirim
**Check:**
1. Application logs untuk error message
2. Supabase logs di Project Settings → Email → Logs
3. Email provider configuration

**Solution:**
- Pastikan `supabase.auth.reset_password_for_email()` dipanggil
- Pastikan email provider dikonfigurasi
- Check rate limit (4 emails/jam untuk Supabase default)

### Issue: Email terkirim tapi link tidak bekerja
**Check:**
1. Redirect URL di email
2. APP_URL environment variable
3. Supabase redirect URLs configuration

**Solution:**
- Pastikan APP_URL set dengan benar
- Pastikan redirect URL ditambahkan di Supabase
- Check application logs untuk redirect URL yang digunakan

### Issue: Reset password form tidak muncul
**Check:**
1. URL parameters: access_token, token, type
2. /auth/recovery endpoint
3. Template path

**Solution:**
- Pastikan /auth/recovery endpoint handle access_token
- Pastikan template reset.html ada
- Check application logs untuk error

### Issue: Password tidak terupdate
**Check:**
1. access_token valid
2. Password validation (min 6 chars)
3. Supabase user exists

**Solution:**
- Check application logs untuk error message
- Pastikan access_token dikirim ke /auth/reset-password
- Pastikan password memenuhi requirements

---

## Key Differences

### Old Implementation (Wrong):
```python
# ❌ Method tidak ada
supabase.auth.admin.reset_password_for_email(email)

# ❌ Tidak ada redirect URL
# ❌ Email link redirect ke default URL
# ❌ Tidak handle access_token
```

### New Implementation (Correct):
```python
# ✅ Method yang benar
supabase.auth.reset_password_for_email(
    email,
    options={"redirect_to": redirect_to}
)

# ✅ Redirect URL dari environment variable
# ✅ Email link redirect ke custom URL
# ✅ Handle access_token dengan benar
# ✅ Create new client dengan access_token
# ✅ Update password dengan user context
```

---

## Files Modified

### Updated:
- ✅ `app/routes/forgot_password.py` - Fixed reset_password_for_email method
- ✅ `app/routes/auth.py` - Handle access_token properly
- ✅ `app/templates/templates_desktop/forgot_password/reset.html` - Fixed form action
- ✅ `app/templates/templates_mobile/forgot_password/reset.html` - Fixed form action

### No Changes:
- ✅ `app/middleware/session_auth.py` - Already correct
- ✅ `app/main.py` - Already correct
- ✅ Other templates - Already correct

---

## Commit Message

```
fix: correct Supabase password reset implementation

- Use supabase.auth.reset_password_for_email() instead of admin method
- Add redirect_to option with APP_URL environment variable
- Handle access_token parameter in /auth/recovery endpoint
- Create new Supabase client with access_token for password update
- Update templates to use /auth/reset-password endpoint
- Add hidden fields for access_token, token, and type
- Support both access_token and verify_otp methods
- Improve error handling and logging
- Add APP_URL to environment variables
- Fix form action in desktop and mobile templates

Breaking changes:
- Requires APP_URL environment variable
- Form action changed from /forgot-password/reset/{token} to /auth/reset-password
```

---

Sekarang email akan terkirim dengan benar! 🎉
