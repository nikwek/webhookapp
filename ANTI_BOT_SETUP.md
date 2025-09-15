# Anti-Bot Protection Setup

This document explains how to configure the comprehensive bot protection system for your Flask application.

## Features Implemented

1. **Email Verification** - Forces users to confirm their email before login
2. **reCAPTCHA Protection** - Prevents automated bot registrations
3. **Rate Limiting** - Limits registration attempts per IP address
4. **User Agent Detection** - Blocks obvious bot user agents
5. **Strong Password Requirements** - Enforces secure passwords

## Environment Variables Required

Add these to your `.env` file or environment:

```bash
# reCAPTCHA Configuration (Optional but recommended)
RECAPTCHA_SITE_KEY=your_recaptcha_site_key_here
RECAPTCHA_SECRET_KEY=your_recaptcha_secret_key_here

# Email Configuration (Required for email verification)
MAIL_SERVER=your_smtp_server
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=your_email_username
MAIL_PASSWORD=your_email_password
MAIL_DEFAULT_SENDER=your_sender_email@domain.com
```

## Getting reCAPTCHA Keys

1. Go to [Google reCAPTCHA Admin Console](https://www.google.com/recaptcha/admin)
2. Click "Create" to add a new site
3. Choose "reCAPTCHA v2" and "I'm not a robot" checkbox
4. Add your domain(s) (e.g., `yourdomain.com`, `localhost` for development)
5. Copy the Site Key and Secret Key to your environment variables

## Configuration Details

### Email Verification
- Users must verify their email within 5 days of registration
- Cannot login without email confirmation
- Configured in `config.py`:
  ```python
  SECURITY_CONFIRMABLE = True
  SECURITY_LOGIN_WITHOUT_CONFIRMATION = False
  SECURITY_CONFIRM_EMAIL_WITHIN = '5 days'
  ```

### Rate Limiting
- 3 registration attempts per minute per IP
- 10 registration attempts per hour per IP
- Configured in `app/routes/auth.py`

### reCAPTCHA
- Only shows if `RECAPTCHA_SITE_KEY` is configured
- Validates on server-side before user creation
- Falls back gracefully if not configured

### User Agent Detection
- Blocks requests with bot-like user agents
- Checks for: 'bot', 'crawler', 'spider', 'scraper'

## Testing

### Development Mode
For development, you can:
1. Skip reCAPTCHA by not setting the environment variables
2. Use localhost in your reCAPTCHA domain settings
3. Test rate limiting with multiple rapid requests

### Production Deployment
1. Set all environment variables
2. Configure your domain in reCAPTCHA settings
3. Test email delivery
4. Monitor registration attempts in logs

## Monitoring

The system logs:
- Rate limit violations
- reCAPTCHA failures
- Suspicious user agents
- Email confirmation attempts

Check your application logs for patterns of bot activity.

## Additional Security Recommendations

1. **Firewall Rules** - Block known bot IP ranges at the server level
2. **Honeypot Fields** - Add hidden form fields that bots might fill
3. **Time-based Validation** - Reject forms submitted too quickly
4. **IP Reputation** - Use services like Cloudflare for additional protection
5. **Account Monitoring** - Watch for patterns in fake accounts

## Troubleshooting

### reCAPTCHA Not Showing
- Check `RECAPTCHA_SITE_KEY` is set
- Verify domain is added to reCAPTCHA console
- Check browser console for JavaScript errors

### Email Verification Not Working
- Verify SMTP settings
- Check spam folder
- Test email configuration with a simple test

### Rate Limiting Too Strict
- Adjust limits in `app/routes/auth.py`
- Consider different limits for authenticated vs anonymous users

## Files Modified

- `config.py` - Added reCAPTCHA and email confirmation settings
- `app/__init__.py` - Integrated custom registration form
- `app/forms/custom_register_form.py` - Custom form with reCAPTCHA validation
- `app/routes/auth.py` - Rate limiting and bot detection
- `app/templates/security/register_user.html` - reCAPTCHA widget
- `app/templates/base.html` - reCAPTCHA script loading
- `requirements.txt` - Added Flask-ReCaptcha dependency
