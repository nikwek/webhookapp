# app/routes/two_factor.py
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, current_app)
from flask_security import (login_required, current_user, utils as fs_utils)
import pyotp, secrets, json
from app import db
from passlib.totp import TOTP

bp = Blueprint("two_factor", __name__, url_prefix="/auth")

# helper – create & persist new secret
def _generate_totp_secret(user):
    # Generate a new secret and store as Passlib TOTP JSON
    secret = pyotp.random_base32()
    totp_json = TOTP(secret).to_json()
    user.tf_totp_secret = totp_json
    user.tf_primary_method = "authenticator"

    current_app.logger.info(f"Generated new TOTP secret for {user.email}")
    return secret


# -------------------- 1.  SETUP  --------------------------------------
@bp.route("/setup-2fa", methods=["GET", "POST"])
@login_required
def setup_2fa():
    if request.method == "POST":
        # user clicked “Continue” on first step
        secret = _generate_totp_secret(current_user)
        recovery = [secrets.token_hex(4) for _ in range(10)]
        current_user.tf_recovery_codes = json.dumps(recovery)
        db.session.commit()
        return redirect(url_for(".verify_2fa"))
    return render_template("2fa/setup.html")


# -------------------- 2.  VERIFY DURING SETUP -------------------------
@bp.route("/verify-2fa", methods=["GET", "POST"])
@login_required
def verify_2fa():
    secret_json = current_user.tf_totp_secret
    if not secret_json:
        flash("Set up 2FA first.", "error")
        return redirect(url_for(".setup_2fa"))

    try:
        data = json.loads(secret_json)
        secret = data.get("key") or data.get("secret")
    except (ValueError, KeyError):
        flash("Invalid TOTP secret format. Please reset 2FA and try again.", "error")
        return redirect(url_for(".setup_2fa"))

    totp = pyotp.TOTP(secret)
    qr_url = pyotp.totp.TOTP(secret).provisioning_uri(
        name=current_user.email, issuer_name="WebhookApp"
    )

    if request.method == "POST":
        code = request.form.get("code", "")
        if totp.verify(code, valid_window=1):
            flash("Two-factor authentication enabled!", "success")
            return redirect(url_for("dashboard.dashboard"))
        flash("Invalid code, try again.", "error")

    return render_template("2fa/verify.html", qr_url=qr_url, secret=secret)


# -------------------- 3.  DISABLE  ------------------------------------
@bp.route("/disable-2fa", methods=["POST"])
@login_required
def disable_2fa():
    current_user.tf_primary_method = None
    current_user.tf_totp_secret = None
    current_user.tf_recovery_codes = None
    db.session.commit()
    flash("Two-factor authentication disabled.", "success")
    return redirect(url_for("dashboard.dashboard"))


# -------------------- 4.  RECOVERY CODES ------------------------------
@bp.route("/recovery-2fa")
@login_required
def recovery_codes():
    codes = json.loads(current_user.tf_recovery_codes or "[]")
    return render_template("2fa/recovery.html", codes=codes)


# -------------------- 5.  LOST DEVICE  -------------------------------
@bp.route("/reset-2fa", methods=["GET", "POST"])
@login_required
def reset_2fa():
    if request.method == "POST":
        # Very simple: just wipe 2FA, force user to set it up again
        current_user.tf_primary_method = None
        current_user.tf_totp_secret = None
        current_user.tf_recovery_codes = None
        db.session.commit()
        flash("2FA has been reset. Set it up again next login.", "info")
        return redirect(url_for(".setup_2fa"))
    return render_template("2fa/reset.html")