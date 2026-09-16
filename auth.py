# auth.py

from datetime import datetime

from flask import (
    Blueprint,
    request,
    render_template,
    redirect,
    url_for,
    session,
    flash
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from database import get_db
from utils import (
    generate_otp,
    hash_otp,
    verify_otp,
    otp_expiry,
    is_otp_expired,
    send_email_otp,
    normalize_email,
    normalize_phone,
    validate_email,
    validate_phone,
    clean_text
)


# =========================================================
# AUTH BLUEPRINT
# =========================================================

auth = Blueprint(
    "auth",
    __name__
)


# =========================================================
# PLAYER REGISTER
# =========================================================

@auth.route("/player/register", methods=["GET", "POST"])
def player_register():

    if request.method == "GET":
        return render_template("player_register.html")

    player_name = clean_text(
        request.form.get("player_name")
    )

    ff_uid = clean_text(
        request.form.get("ff_uid")
    )

    phone = normalize_phone(
        request.form.get("phone")
    )

    email = normalize_email(
        request.form.get("email")
    )

    password = request.form.get(
        "password",
        ""
    )

    confirm_password = request.form.get(
        "confirm_password",
        ""
    )

    # -----------------------------------------------------
    # BASIC VALIDATION
    # -----------------------------------------------------

    if not player_name:
        flash(
            "Player name is required.",
            "error"
        )
        return redirect(
            url_for("auth.player_register")
        )

    if not ff_uid:
        flash(
            "Free Fire UID is required.",
            "error"
        )
        return redirect(
            url_for("auth.player_register")
        )

    if not validate_phone(phone):
        flash(
            "Enter a valid 10 digit Indian mobile number.",
            "error"
        )
        return redirect(
            url_for("auth.player_register")
        )

    if not validate_email(email):
        flash(
            "Enter a valid email address.",
            "error"
        )
        return redirect(
            url_for("auth.player_register")
        )

    if len(password) < 8:
        flash(
            "Password must be at least 8 characters.",
            "error"
        )
        return redirect(
            url_for("auth.player_register")
        )

    if password != confirm_password:
        flash(
            "Passwords do not match.",
            "error"
        )
        return redirect(
            url_for("auth.player_register")
        )

    # -----------------------------------------------------
    # DATABASE CHECK
    # -----------------------------------------------------

    conn = get_db()

    try:

        cur = conn.cursor()

        cur.execute(
            """
            SELECT id
            FROM users
            WHERE ff_uid = %s
               OR phone = %s
               OR email = %s
            LIMIT 1
            """,
            (
                ff_uid,
                phone,
                email
            )
        )

        existing_user = cur.fetchone()

        if existing_user:

            flash(
                "An account with this UID, phone or email already exists.",
                "error"
            )

            return redirect(
                url_for("auth.player_register")
            )

        # -------------------------------------------------
        # CREATE OTPs
        # -------------------------------------------------

        email_otp = generate_otp()
        phone_otp = generate_otp()

        email_otp_hash = hash_otp(
            email_otp
        )

        phone_otp_hash = hash_otp(
            phone_otp
        )

        email_expiry = otp_expiry(
            10
        )

        phone_expiry = otp_expiry(
            10
        )

        password_hash = generate_password_hash(
            password
        )

        # -------------------------------------------------
        # CREATE USER
        # -------------------------------------------------

        cur.execute(
            """
            INSERT INTO users (
                player_name,
                ff_uid,
                phone,
                email,
                password_hash,
                phone_verified,
                email_verified,
                account_status,
                phone_otp_hash,
                phone_otp_expires,
                email_otp_hash,
                email_otp_expires
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                FALSE,
                FALSE,
                'Pending Verification',
                %s,
                %s,
                %s,
                %s
            )
            RETURNING id
            """,
            (
                player_name,
                ff_uid,
                phone,
                email,
                password_hash,
                phone_otp_hash,
                phone_expiry,
                email_otp_hash,
                email_expiry
            )
        )

        user = cur.fetchone()

        user_id = user["id"]

        conn.commit()

    except Exception:

        conn.rollback()

        raise

    finally:

        conn.close()

    # -----------------------------------------------------
    # SEND EMAIL OTP
    # -----------------------------------------------------

    email_sent = send_email_otp(
        email,
        email_otp
    )

    # -----------------------------------------------------
    # SAVE USER ID IN SESSION
    # -----------------------------------------------------

    session["verification_user_id"] = user_id

    session["verification_email"] = email

    # Phone OTP अभी SMS provider के बिना
    # वास्तविक SMS पर नहीं जाएगा.

    if not email_sent:

        flash(
            "Account created, but email OTP could not be sent. Check SMTP settings in Render.",
            "error"
        )

    else:

        flash(
            "Account created. Check your email for the OTP.",
            "success"
        )

    return redirect(
        url_for("auth.verify_account")
    )


# =========================================================
# VERIFY ACCOUNT PAGE
# =========================================================

@auth.route(
    "/player/verify",
    methods=["GET", "POST"]
)
def verify_account():

    user_id = session.get(
        "verification_user_id"
    )

    if not user_id:

        flash(
            "Verification session expired. Please register again.",
            "error"
        )

        return redirect(
            url_for("auth.player_register")
        )

    if request.method == "GET":

        return render_template(
            "verify_account.html",
            email=session.get(
                "verification_email"
            )
        )

    email_otp = clean_text(
        request.form.get(
            "email_otp"
        )
    )

    phone_otp = clean_text(
        request.form.get(
            "phone_otp"
        )
    )

    conn = get_db()

    try:

        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                id,
                email,
                phone_otp_hash,
                phone_otp_expires,
                email_otp_hash,
                email_otp_expires,
                phone_verified,
                email_verified
            FROM users
            WHERE id = %s
            """,
            (user_id,)
        )

        user = cur.fetchone()

        if not user:

            flash(
                "Account not found.",
                "error"
            )

            return redirect(
                url_for("auth.player_register")
            )

        # -------------------------------------------------
        # EMAIL OTP
        # -------------------------------------------------

        email_valid = False

        if email_otp:

            if not is_otp_expired(
                user["email_otp_expires"]
            ):

                email_valid = verify_otp(
                    email_otp,
                    user["email_otp_hash"]
                )

        # -------------------------------------------------
        # PHONE OTP
        # -------------------------------------------------

        phone_valid = False

        if phone_otp:

            if not is_otp_expired(
                user["phone_otp_expires"]
            ):

                phone_valid = verify_otp(
                    phone_otp,
                    user["phone_otp_hash"]
                )

        # -------------------------------------------------
        # UPDATE VERIFICATION STATUS
        # -------------------------------------------------

        if email_valid:

            cur.execute(
                """
                UPDATE users
                SET email_verified = TRUE
                WHERE id = %s
                """,
                (user_id,)
            )

        if phone_valid:

            cur.execute(
                """
                UPDATE users
                SET phone_verified = TRUE
                WHERE id = %s
                """,
                (user_id,)
            )

        # -------------------------------------------------
        # GET UPDATED STATUS
        # -------------------------------------------------

        cur.execute(
            """
            SELECT
                email_verified,
                phone_verified
            FROM users
            WHERE id = %s
            """,
            (user_id,)
        )

        status = cur.fetchone()

        if (
            status["email_verified"]
            and status["phone_verified"]
        ):

            cur.execute(
                """
                UPDATE users
                SET account_status = 'Active'
                WHERE id = %s
                """,
                (user_id,)
            )

            conn.commit()

            session.pop(
                "verification_user_id",
                None
            )

            session.pop(
                "verification_email",
                None
            )

            flash(
                "Account verified successfully. You can now login.",
                "success"
            )

            return redirect(
                url_for("auth.player_login")
            )

        conn.commit()

        if email_otp and not email_valid:

            flash(
                "Email OTP is incorrect or expired.",
                "error"
            )

        if phone_otp and not phone_valid:

            flash(
                "Phone OTP is incorrect or expired.",
                "error"
            )

        if not email_otp and not phone_otp:

            flash(
                "Enter the OTP you received.",
                "error"
            )

    except Exception:

        conn.rollback()

        raise

    finally:

        conn.close()

    return redirect(
        url_for("auth.verify_account")
    )


# =========================================================
# RESEND OTP
# =========================================================

@auth.route(
    "/player/resend-otp",
    methods=["POST"]
)
def resend_otp():

    user_id = session.get(
        "verification_user_id"
    )

    if not user_id:

        flash(
            "Verification session expired.",
            "error"
        )

        return redirect(
            url_for("auth.player_register")
        )

    conn = get_db()

    try:

        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                id,
                email,
                phone
            FROM users
            WHERE id = %s
            """,
            (user_id,)
        )

        user = cur.fetchone()

        if not user:

            flash(
                "Account not found.",
                "error"
            )

            return redirect(
                url_for("auth.player_register")
            )

        email_otp = generate_otp()
        phone_otp = generate_otp()

        cur.execute(
            """
            UPDATE users
            SET
                email_otp_hash = %s,
                email_otp_expires = %s,
                phone_otp_hash = %s,
                phone_otp_expires = %s
            WHERE id = %s
            """,
            (
                hash_otp(email_otp),
                otp_expiry(10),
                hash_otp(phone_otp),
                otp_expiry(10),
                user_id
            )
        )

        conn.commit()

        email_sent = send_email_otp(
            user["email"],
            email_otp
        )

    except Exception:

        conn.rollback()

        raise

    finally:

        conn.close()

    if email_sent:

        flash(
            "A new OTP has been sent to your email.",
            "success"
        )

    else:

        flash(
            "OTP could not be sent. Check SMTP settings.",
            "error"
        )

    return redirect(
        url_for("auth.verify_account")
    )


# =========================================================
# PLAYER LOGIN
# =========================================================

@auth.route(
    "/player/login",
    methods=["GET", "POST"]
)
def player_login():

    if request.method == "GET":

        return render_template(
            "player_login.html"
        )

    login_value = clean_text(
        request.form.get(
            "login"
        )
    )

    password = request.form.get(
        "password",
        ""
    )

    if not login_value or not password:

        flash(
            "Enter your UID/email/phone and password.",
            "error"
        )

        return redirect(
            url_for("auth.player_login")
        )

    login_value_lower = login_value.lower()

    conn = get_db()

    try:

        cur = conn.cursor()

        cur.execute(
            """
            SELECT *
            FROM users
            WHERE
                ff_uid = %s
                OR phone = %s
                OR LOWER(email) = %s
            LIMIT 1
            """,
            (
                login_value,
                login_value,
                login_value_lower
            )
        )

        user = cur.fetchone()

    finally:

        conn.close()

    if not user:

        flash(
            "Invalid login details.",
            "error"
        )

        return redirect(
            url_for("auth.player_login")
        )

    if not check_password_hash(
        user["password_hash"],
        password
    ):

        flash(
            "Invalid login details.",
            "error"
        )

        return redirect(
            url_for("auth.player_login")
        )

    if user["account_status"] != "Active":

        flash(
            "Please verify your account before login.",
            "error"
        )

        session["verification_user_id"] = user["id"]

        session["verification_email"] = user["email"]

        return redirect(
            url_for("auth.verify_account")
        )

    # -----------------------------------------------------
    # LOGIN SESSION
    # -----------------------------------------------------

    session.clear()

    session["user_id"] = user["id"]

    session["player_name"] = user["player_name"]

    session["ff_uid"] = user["ff_uid"]

    return redirect(
        url_for("player_dashboard")
    )


# =========================================================
# PLAYER LOGOUT
# =========================================================

@auth.route(
    "/player/logout"
)
def player_logout():

    session.clear()

    flash(
        "You have been logged out.",
        "success"
    )

    return redirect(
        url_for("auth.player_login")
    )
