#!/usr/bin/env python3
"""Debug script to check reCAPTCHA configuration"""

import os
from app import create_app

app = create_app()

with app.app_context():
    print("=== reCAPTCHA Configuration Debug ===")
    print(f"RECAPTCHA_SITE_KEY: {app.config.get('RECAPTCHA_SITE_KEY', 'NOT SET')}")
    print(f"RECAPTCHA_SECRET_KEY: {'SET' if app.config.get('RECAPTCHA_SECRET_KEY') else 'NOT SET'}")
    print(f"RECAPTCHA_ENABLED: {app.config.get('RECAPTCHA_ENABLED', False)}")
    print(f"Environment RECAPTCHA_SITE_KEY: {'SET' if os.environ.get('RECAPTCHA_SITE_KEY') else 'NOT SET'}")
    print(f"Environment RECAPTCHA_SECRET_KEY: {'SET' if os.environ.get('RECAPTCHA_SECRET_KEY') else 'NOT SET'}")
