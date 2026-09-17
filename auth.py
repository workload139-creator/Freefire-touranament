# auth.py

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

@auth.route(
    "/player/register",
    methods=["GET", "POST"]
)
def player_register():

    if request.method == "GET":
        return render_template(
            "player_register.html"
        )

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
    # VALIDATION
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
    # DATABASE
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
        # EMAIL OTP
        # -------------------------------------------------

        email_otp = generate_otp()

        email_otp_hash = hash_otp(
            email_otp
        )

        email_expiry = otp_expiry(
            10
        )

        # Phone verification अभी implemented नहीं है.
        # इसलिए phone_verified = FALSE रहेगा.

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
                NULL,
                NULL,
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
    # VERIFICATION SESSION
    # -----------------------------------------------------

    session["verification_user_id"] = user_id

    session["verification_email"] = email

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
# VERIFY ACCOUNT
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

    # -----------------------------------------------------
    # GET
    # -----------------------------------------------------

    if request.method == "GET":

        return render_template(
            "verify_account.html",
            email=session.get(
                "verification_email"
            )
        )

    # -----------------------------------------------------
    # POST
    # -----------------------------------------------------

    email_otp = clean_text(
        request.form.get(
            "email_otp"
        )
    )

    if not email_otp:

        flash(
            "Enter the Email OTP you received.",
            "error"
        )

        return redirect(
            url_for("auth.verify_account")
        )

    conn = get_db()

    try:

        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                id,
                email,
                email_otp_hash,
                email_otp_expires,
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
        # CHECK EMAIL OTP
        # -------------------------------------------------

        if user["email_verified"]:

            flash(
                "Email is already verified.",
                "success"
            )

            return redirect(
                url_for("auth.player_login")
            )

        if is_otp_expired(
            user["email_otp_expires"]
        ):

            flash(
                "Email OTP has expired. Please request a new OTP.",
                "error"
            )

            return redirect(
                url_for("auth.verify_account")
            )

        if not verify_otp(
            email_otp,
            user["email_otp_hash"]
        ):

            flash(
                "Email OTP is incorrect.",
                "error"
            )

            return redirect(
                url_for("auth.verify_account")
            )

        # -------------------------------------------------
        # EMAIL VERIFIED
        # -------------------------------------------------

        cur.execute(
            """
            UPDATE users
            SET
                email_verified = TRUE,
                account_status = 'Active'
            WHERE id = %s
            """,
            (user_id,)
        )

        conn.commit()

    except Exception:

        conn.rollback()

        raise

    finally:

        conn.close()

    # -----------------------------------------------------
    # CLEAR VERIFICATION SESSION
    # -----------------------------------------------------

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


# =========================================================
# RESEND EMAIL OTP
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

        if user["email_verified"]:

            flash(
                "Email is already verified.",
                "success"
            )

            return redirect(
                url_for("auth.player_login")
            )

        # -------------------------------------------------
        # NEW EMAIL OTP
        # -------------------------------------------------

        email_otp = generate_otp()

        email_hash = hash_otp(
            email_otp
        )

        expiry = otp_expiry(
            10
        )

        cur.execute(
            """
            UPDATE users
            SET
                email_otp_hash = %s,
                email_otp_expires = %s
            WHERE id = %s
            """,
            (
                email_hash,
                expiry,
                user_id
            )
        )

        conn.commit()

    except Exception:

        conn.rollback()

        raise

    finally:

        conn.close()

    # -----------------------------------------------------
    # SEND EMAIL
    # -----------------------------------------------------

    email_sent = send_email_otp(
        user["email"],
        email_otp
    )

    if email_sent:

        flash(
            "A new OTP has been sent to your email.",
            "success"
        )

    else:

        flash(
            "OTP could not be sent. Check SMTP settings in Render.",
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

    login_phone = normalize_phone(
        login_value
    )

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
                login_phone,
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

    # -----------------------------------------------------
    # PASSWORD
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # ACCOUNT STATUS
    # -----------------------------------------------------

    if user["account_status"] != "Active":

        flash(
            "Please verify your email before login.",
            "error"
        )

        session["verification_user_id"] = user["id"]

        session["verification_email"] = user["email"]

        return redirect(
            url_for("auth.verify_account")
        )

    # -----------------------------------------------------
    # LOGIN
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
