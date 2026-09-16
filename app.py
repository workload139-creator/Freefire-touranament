import os
import secrets
import hashlib
import smtplib

from datetime import datetime, timedelta
from email.message import EmailMessage

import psycopg2

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    abort
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)


# =========================================================
# APP
# =========================================================

app = Flask(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY")

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH")

app.secret_key = SECRET_KEY

# =========================================================
# SMTP
# =========================================================

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USERNAME or "")

# =========================================================
# SMS
# =========================================================

SMS_API_URL = os.getenv("SMS_API_URL")
SMS_API_KEY = os.getenv("SMS_API_KEY")


# =========================================================
# DATABASE
# =========================================================

def get_db():
    return psycopg2.connect(DATABASE_URL)


# =========================================================
# OTP
# =========================================================

def generate_otp():
    return f"{secrets.randbelow(1000000):06d}"


def hash_otp(otp):
    return hashlib.sha256(
        otp.encode("utf-8")
    ).hexdigest()


def otp_expired(expires_at):
    if not expires_at:
        return True

    return datetime.utcnow() > expires_at


# =========================================================
# EMAIL OTP
# =========================================================

def send_email_otp(email, otp):

    print("================================")
    print("EMAIL OTP REQUEST")
    print("To:", email)
    print("================================")

    if not SMTP_HOST:
        print("ERROR: SMTP_HOST missing")
        return False

    if not SMTP_USERNAME:
        print("ERROR: SMTP_USERNAME missing")
        return False

    if not SMTP_PASSWORD:
        print("ERROR: SMTP_PASSWORD missing")
        return False

    if not SMTP_FROM:
        print("ERROR: SMTP_FROM missing")
        return False

    try:

        msg = EmailMessage()

        msg["Subject"] = "FF Tournament - Verification OTP"
        msg["From"] = SMTP_FROM
        msg["To"] = email

        msg.set_content(
            f"""
FF TOURNAMENT

Your verification OTP is:

{otp}

This OTP will expire in 10 minutes.

If you did not create this account,
please ignore this email.

Independent community tournament platform.
"""
        )

        with smtplib.SMTP(
            SMTP_HOST,
            SMTP_PORT,
            timeout=30
        ) as server:

            server.ehlo()
            server.starttls()
            server.ehlo()

            server.login(
                SMTP_USERNAME,
                SMTP_PASSWORD
            )

            server.send_message(msg)

        print("EMAIL OTP SENT SUCCESSFULLY")

        return True

    except Exception as e:

        print("EMAIL OTP ERROR:", repr(e))

        return False


# =========================================================
# PHONE OTP
# =========================================================

def send_phone_otp(phone, otp):

    print("================================")
    print("PHONE OTP REQUEST")
    print("Phone:", phone)
    print("================================")

    if not SMS_API_URL or not SMS_API_KEY:

        print(
            "SMS provider is not configured."
        )

        return False

    # -----------------------------------------------------
    # Yahan selected SMS provider ka API integration
    # add kiya jayega.
    # -----------------------------------------------------

    print(
        "SMS provider configured, "
        "but provider-specific API code is required."
    )

    return False


# =========================================================
# SEND BOTH OTP
# =========================================================

def create_and_send_otps(player_id):

    phone_otp = generate_otp()
    email_otp = generate_otp()

    expires_at = datetime.utcnow() + timedelta(
        minutes=10
    )

    conn = get_db()
    cur = conn.cursor()

    try:

        cur.execute(
            """
            SELECT phone, email
            FROM users
            WHERE id = %s
            """,
            (player_id,)
        )

        user = cur.fetchone()

        if not user:
            return False, "Account नहीं मिला।"

        phone = user[0]
        email = user[1]

        cur.execute(
            """
            UPDATE users
            SET
                phone_otp_hash = %s,
                phone_otp_expires = %s,
                email_otp_hash = %s,
                email_otp_expires = %s
            WHERE id = %s
            """,
            (
                hash_otp(phone_otp),
                expires_at,
                hash_otp(email_otp),
                expires_at,
                player_id
            )
        )

        conn.commit()

    except Exception as e:

        conn.rollback()

        print("OTP DATABASE ERROR:", repr(e))

        return False, "OTP database error."

    finally:

        cur.close()
        conn.close()


    # =====================================================
    # SEND EMAIL
    # =====================================================

    email_sent = send_email_otp(
        email,
        email_otp
    )


    # =====================================================
    # SEND PHONE
    # =====================================================

    phone_sent = send_phone_otp(
        phone,
        phone_otp
    )


    # =====================================================
    # RESULT
    # =====================================================

    if email_sent and phone_sent:

        return True, (
            "Phone और Email दोनों पर OTP भेज दिया गया।"
        )

    if email_sent:

        return True, (
            "Email OTP भेज दिया गया। "
            "Phone SMS provider अभी configured नहीं है।"
        )

    if phone_sent:

        return True, (
            "Phone OTP भेज दिया गया। "
            "Email OTP नहीं भेजा जा सका।"
        )

    return False, (
        "OTP भेजा नहीं जा सका। "
        "Render SMTP/SMS settings check करें।"
    )


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

def init_db():

    conn = get_db()
    cur = conn.cursor()

    try:

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tournaments (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                mode TEXT NOT NULL,
                entry INTEGER NOT NULL DEFAULT 0,
                prize TEXT NOT NULL DEFAULT '',
                date TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL
                    DEFAULT 'Registration Open',
                room_id TEXT,
                room_password TEXT
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                player_name TEXT NOT NULL,
                ff_uid TEXT NOT NULL UNIQUE,
                phone TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,

                phone_verified BOOLEAN
                    NOT NULL DEFAULT FALSE,

                email_verified BOOLEAN
                    NOT NULL DEFAULT FALSE,

                account_status TEXT
                    NOT NULL DEFAULT 'Active',

                phone_otp_hash TEXT,
                phone_otp_expires TIMESTAMP,

                email_otp_hash TEXT,
                email_otp_expires TIMESTAMP,

                created_at TIMESTAMP
                    NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS registrations (
                id SERIAL PRIMARY KEY,

                tournament_id INTEGER NOT NULL
                    REFERENCES tournaments(id)
                    ON DELETE CASCADE,

                player_name TEXT NOT NULL,
                team_name TEXT NOT NULL,
                uid TEXT NOT NULL,

                payment_ref TEXT NOT NULL,

                payment_status TEXT
                    NOT NULL DEFAULT 'Pending',

                room_token TEXT,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE SET NULL,

                joined_at TIMESTAMP
                    NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Safe migrations

        cur.execute(
            """
            ALTER TABLE registrations
            ADD COLUMN IF NOT EXISTS user_id INTEGER
            """
        )

        cur.execute(
            """
            ALTER TABLE registrations
            ADD COLUMN IF NOT EXISTS room_token TEXT
            """
        )

        cur.execute(
            """
            ALTER TABLE registrations
            ADD COLUMN IF NOT EXISTS payment_status TEXT
                DEFAULT 'Pending'
            """
        )

        cur.execute(
            """
            ALTER TABLE registrations
            ADD COLUMN IF NOT EXISTS joined_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP
            """
        )

        cur.execute(
            """
            UPDATE registrations
            SET payment_status = 'Pending'
            WHERE payment_status IS NULL
            """
        )

        cur.execute(
            """
            UPDATE registrations
            SET joined_at = CURRENT_TIMESTAMP
            WHERE joined_at IS NULL
            """
        )

        conn.commit()

    except Exception:

        conn.rollback()
        raise

    finally:

        cur.close()
        conn.close()


init_db()


# =========================================================
# PLAYER REGISTER
# =========================================================

@app.route(
    "/player/register",
    methods=["GET", "POST"]
)
def player_register():

    if request.method == "GET":

        return render_template(
            "player_register.html"
        )

    player_name = request.form.get(
        "player_name",
        ""
    ).strip()

    ff_uid = request.form.get(
        "ff_uid",
        ""
    ).strip()

    phone = request.form.get(
        "phone",
        ""
    ).strip()

    email = request.form.get(
        "email",
        ""
    ).strip().lower()

    password = request.form.get(
        "password",
        ""
    )

    # Validation

    if not player_name:
        return render_template(
            "player_register.html",
            error="Player Name required hai."
        )

    if not ff_uid:
        return render_template(
            "player_register.html",
            error="Free Fire UID required hai."
        )

    if not phone:
        return render_template(
            "player_register.html",
            error="Phone number required hai."
        )

    if not email:
        return render_template(
            "player_register.html",
            error="Email required hai."
        )

    if len(password) < 8:
        return render_template(
            "player_register.html",
            error="Password कम से कम 8 characters का होना चाहिए."
        )

    conn = get_db()
    cur = conn.cursor()

    try:

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

        if cur.fetchone():

            return render_template(
                "player_register.html",
                error=(
                    "FF UID, Phone या Email "
                    "पहले से registered है."
                )
            )

        password_hash = generate_password_hash(
            password
        )

        cur.execute(
            """
            INSERT INTO users
            (
                player_name,
                ff_uid,
                phone,
                email,
                password_hash
            )
            VALUES
            (
                %s,%s,%s,%s,%s
            )
            RETURNING id
            """,
            (
                player_name,
                ff_uid,
                phone,
                email,
                password_hash
            )
        )

        player_id = cur.fetchone()[0]

        conn.commit()

    except Exception as e:

        conn.rollback()

        print(
            "REGISTER ERROR:",
            repr(e)
        )

        return render_template(
            "player_register.html",
            error="Registration failed."
        )

    finally:

        cur.close()
        conn.close()


    session["verify_player_id"] = player_id

    success, message = create_and_send_otps(
        player_id
    )

    if not success:

        return render_template(
            "player_register.html",
            error=message
        )

    return redirect(
        url_for("verify_account")
    )


# =========================================================
# VERIFY ACCOUNT
# =========================================================

@app.route(
    "/player/verify",
    methods=["GET", "POST"]
)
def verify_account():

    player_id = session.get(
        "verify_player_id"
    )

    if not player_id:

        return redirect(
            url_for("player_register")
        )

    conn = get_db()
    cur = conn.cursor()

    try:

        cur.execute(
            """
            SELECT
                phone_otp_hash,
                phone_otp_expires,
                email_otp_hash,
                email_otp_expires,
                phone_verified,
                email_verified
            FROM users
            WHERE id = %s
            """,
            (player_id,)
        )

        user = cur.fetchone()

    finally:

        cur.close()
        conn.close()

    if not user:

        return redirect(
            url_for("player_register")
        )

    if request.method == "GET":

        return render_template(
            "verify_account.html"
        )

    phone_otp = request.form.get(
        "phone_otp",
        ""
    ).strip()

    email_otp = request.form.get(
        "email_otp",
        ""
    ).strip()

    phone_hash = user[0]
    phone_expires = user[1]

    email_hash = user[2]
    email_expires = user[3]

    phone_verified = user[4]
    email_verified = user[5]

    # =====================================================
    # PHONE
    # =====================================================

    if not phone_verified:

        if not phone_otp:

            return render_template(
                "verify_account.html",
                error="Phone OTP required hai."
            )

        if len(phone_otp) != 6 or not phone_otp.isdigit():

            return render_template(
                "verify_account.html",
                error="Phone OTP 6 digit hona chahiye."
            )

        if otp_expired(phone_expires):

            return render_template(
                "verify_account.html",
                error="Phone OTP expire ho gaya. Resend OTP karein."
            )

        if hash_otp(phone_otp) != phone_hash:

            return render_template(
                "verify_account.html",
                error="Phone OTP गलत है."
            )


    # =====================================================
    # EMAIL
    # =====================================================

    if not email_verified:

        if not email_otp:

            return render_template(
                "verify_account.html",
                error="Email OTP required hai."
            )

        if len(email_otp) != 6 or not email_otp.isdigit():

            return render_template(
                "verify_account.html",
                error="Email OTP 6 digit hona chahiye."
            )

        if otp_expired(email_expires):

            return render_template(
                "verify_account.html",
                error="Email OTP expire ho गया. Resend OTP karein."
            )

        if hash_otp(email_otp) != email_hash:

            return render_template(
                "verify_account.html",
                error="Email OTP गलत है."
            )


    # =====================================================
    # VERIFY
    # =====================================================

    conn = get_db()
    cur = conn.cursor()

    try:

        cur.execute(
            """
            UPDATE users
            SET
                phone_verified = TRUE,
                email_verified = TRUE,
                phone_otp_hash = NULL,
                phone_otp_expires = NULL,
                email_otp_hash = NULL,
                email_otp_expires = NULL
            WHERE id = %s
            """,
            (player_id,)
        )

        conn.commit()

    except Exception:

        conn.rollback()
        raise

    finally:

        cur.close()
        conn.close()

    session.pop(
        "verify_player_id",
        None
    )

    session["player_id"] = player_id

    return redirect(
        url_for("player_dashboard")
    )


# =========================================================
# RESEND OTP
# =========================================================

@app.route(
    "/player/resend-otp",
    methods=["POST"]
)
def resend_otp():

    player_id = session.get(
        "verify_player_id"
    )

    if not player_id:

        return redirect(
            url_for("player_register")
        )

    success, message = create_and_send_otps(
        player_id
    )

    if success:

        return render_template(
            "verify_account.html",
            message=message
        )

    return render_template(
        "verify_account.html",
        error=message
    )


# =========================================================
# PLAYER LOGIN
# =========================================================

@app.route(
    "/player/login",
    methods=["GET", "POST"]
)
def player_login():

    if request.method == "GET":

        return render_template(
            "player_login.html"
        )

    login_value = request.form.get(
        "login",
        ""
    ).strip()

    password = request.form.get(
        "password",
        ""
    )

    conn = get_db()
    cur = conn.cursor()

    try:

        cur.execute(
            """
            SELECT
                id,
                password_hash,
                phone_verified,
                email_verified,
                account_status
            FROM users
            WHERE LOWER(email) = LOWER(%s)
               OR ff_uid = %s
               OR phone = %s
            LIMIT 1
            """,
            (
                login_value,
                login_value,
                login_value
            )
        )

        user = cur.fetchone()

    finally:

        cur.close()
        conn.close()

    if not user:

        return render_template(
            "player_login.html",
            error="Account नहीं मिला."
        )

    if not check_password_hash(
        user[1],
        password
    ):

        return render_template(
            "player_login.html",
            error="Password गलत है."
        )

    if user[4] != "Active":

        return render_template(
            "player_login.html",
            error="Account active नहीं है."
        )

    if not user[2] or not user[3]:

        session["verify_player_id"] = user[0]

        return redirect(
            url_for("verify_account")
        )

    session["player_id"] = user[0]

    return redirect(
        url_for("player_dashboard")
    )


# =========================================================
# PLAYER DASHBOARD
# =========================================================

@app.route("/player/dashboard")
def player_dashboard():

    player_id = session.get(
        "player_id"
    )

    if not player_id:

        return redirect(
            url_for("player_login")
        )

    conn = get_db()
    cur = conn.cursor()

    try:

        cur.execute(
            """
            SELECT
                id,
                player_name,
                ff_uid,
                phone,
                email,
                phone_verified,
                email_verified,
                account_status,
                created_at
            FROM users
            WHERE id = %s
            """,
            (player_id,)
        )

        player = cur.fetchone()

        cur.execute(
            """
            SELECT
                r.id,
                r.tournament_id,
                r.player_name,
                r.team_name,
                r.uid,
                r.payment_ref,
                r.payment_status,
                t.name,
                t.mode,
                t.entry,
                t.prize,
                t.date,
                t.status,
                t.room_id,
                t.room_password
            FROM registrations r
            JOIN tournaments t
                ON r.tournament_id = t.id
            WHERE r.user_id = %s
            ORDER BY r.id DESC
            """,
            (player_id,)
        )

        registrations = cur.fetchall()

    finally:

        cur.close()
        conn.close()

    if not player:

        session.pop(
            "player_id",
            None
        )

        return redirect(
            url_for("player_login")
        )

    return render_template(
        "player_dashboard.html",
        player=player,
        registrations=registrations
    )


# =========================================================
# PLAYER LOGOUT
# =========================================================

@app.route("/player/logout")
def player_logout():

    session.pop(
        "player_id",
        None
    )

    session.pop(
        "verify_player_id",
        None
    )

    return redirect(
        url_for("index")
    )


# =========================================================
# PROFILE
# =========================================================

@app.route("/player/profile")
def player_profile():

    player_id = session.get(
        "player_id"
    )

    if not player_id:

        return redirect(
            url_for("player_login")
        )

    conn = get_db()
    cur = conn.cursor()

    try:

        cur.execute(
            """
            SELECT
                id,
                player_name,
                ff_uid,
                phone,
                email,
                phone_verified,
                email_verified,
                account_status,
                created_at
            FROM users
            WHERE id = %s
            """,
            (player_id,)
        )

        player = cur.fetchone()

    finally:

        cur.close()
        conn.close()

    if not player:

        return redirect(
            url_for("player_login")
        )

    return render_template(
        "profile.html",
        player=player
    )


# =========================================================
# TOURNAMENT DETAILS
# =========================================================

@app.route("/tournament/<int:id>")
def tournament(id):

    conn = get_db()
    cur = conn.cursor()

    try:

        cur.execute(
            """
            SELECT
                id,
                name,
                mode,
                entry,
                prize,
                date,
                status,
                room_id,
                room_password
            FROM tournaments
            WHERE id = %s
            """,
            (id,)
        )

        tournament_data = cur.fetchone()

    finally:

        cur.close()
        conn.close()

    if not tournament_data:

        abort(404)

    return render_template(
        "tournament.html",
        tournament=tournament_data
    )


# =========================================================
# HOME
# =========================================================

@app.route("/")
def index():

    conn = get_db()
    cur = conn.cursor()

    try:

        cur.execute(
            """
            SELECT
                id,
                name,
                mode,
                entry,
                prize,
                date,
                status
            FROM tournaments
            ORDER BY id DESC
            """
        )

        tournaments = cur.fetchall()

    finally:

        cur.close()
        conn.close()

    return render_template(
        "index.html",
        tournaments=tournaments
    )


# =========================================================
# ADMIN LOGIN
# =========================================================

@app.route(
    "/admin",
    methods=["GET", "POST"]
)
def admin():

    if session.get("admin"):

        return redirect(
            url_for("admin_panel")
        )

    if request.method == "GET":

        return render_template(
            "admin.html"
        )

    username = request.form.get(
        "username",
        ""
    ).strip()

    password = request.form.get(
        "password",
        ""
    )

    if username != ADMIN_USERNAME:

        return render_template(
            "admin.html",
            error="Invalid login."
        )

    if not ADMIN_PASSWORD_HASH:

        return render_template(
            "admin.html",
            error="Admin password hash configured नहीं है."
        )

    if not check_password_hash(
        ADMIN_PASSWORD_HASH,
        password
    ):

        return render_template(
            "admin.html",
            error="Invalid login."
        )

    session["admin"] = True

    return redirect(
        url_for("admin_panel")
    )


# =========================================================
# ADMIN PANEL
# =========================================================

@app.route("/admin/panel")
def admin_panel():

    if not session.get("admin"):

        return redirect(
            url_for("admin")
        )

    conn = get_db()
    cur = conn.cursor()

    try:

        cur.execute(
            """
            SELECT
                id,
                name,
                mode,
                entry,
                prize,
                date,
                status,
                room_id,
                room_password
            FROM tournaments
            ORDER BY id DESC
            """
        )

        tournaments = cur.fetchall()

        cur.execute(
            """
            SELECT
                r.id,
                r.player_name,
                r.team_name,
                r.uid,
                r.payment_ref,
                r.payment_status,
                r.user_id,
                t.name,
                t.date
            FROM registrations r
            JOIN tournaments t
                ON r.tournament_id = t.id
            ORDER BY r.id DESC
            """
        )

        registrations = cur.fetchall()

        cur.execute(
            """
            SELECT
                id,
                player_name,
                ff_uid,
                phone,
                email,
                phone_verified,
                email_verified,
                account_status,
                created_at
            FROM users
            ORDER BY id DESC
            """
        )

        players = cur.fetchall()

    finally:

        cur.close()
        conn.close()

    return render_template(
        "admin.html",
        tournaments=tournaments,
        registrations=registrations,
        players=players
    )


# =========================================================
# ADMIN VERIFY PAYMENT
# =========================================================

@app.route(
    "/admin/verify/<int:registration_id>",
    methods=["POST"]
)
def admin_verify(registration_id):

    if not session.get("admin"):

        return redirect(
            url_for("admin")
        )

    conn = get_db()
    cur = conn.cursor()

    try:

        cur.execute(
            """
            UPDATE registrations
            SET payment_status = 'Verified'
            WHERE id = %s
            """,
            (registration_id,)
        )

        conn.commit()

    finally:

        cur.close()
        conn.close()

    return redirect(
        url_for("admin_panel")
    )


# =========================================================
# ADMIN REJECT
# =========================================================

@app.route(
    "/admin/reject/<int:registration_id>",
    methods=["POST"]
)
def admin_reject(registration_id):

    if not session.get("admin"):

        return redirect(
            url_for("admin")
        )

    conn = get_db()
    cur = conn.cursor()

    try:

        cur.execute(
            """
            UPDATE registrations
            SET payment_status = 'Rejected'
            WHERE id = %s
            """,
            (registration_id,)
        )

        conn.commit()

    finally:

        cur.close()
        conn.close()

    return redirect(
        url_for("admin_panel")
    )


# =========================================================
# ADMIN ADD TOURNAMENT
# =========================================================

@app.route(
    "/admin/add",
    methods=["POST"]
)
def admin_add():

    if not session.get("admin"):

        return redirect(
            url_for("admin")
        )

    name = request.form.get(
        "name",
        ""
    ).strip()

    mode = request.form.get(
        "mode",
        "BR"
    ).strip()

    entry = request.form.get(
        "entry",
        "0"
    ).strip()

    prize = request.form.get(
        "prize",
        ""
    ).strip()

    date = request.form.get(
        "date",
        ""
    ).strip()

    try:
        entry = int(entry)
    except ValueError:
        entry = 0

    conn = get_db()
    cur = conn.cursor()

    try:

        cur.execute(
            """
            INSERT INTO tournaments
            (
                name,
                mode,
                entry,
                prize,
                date
            )
            VALUES
            (
                %s,%s,%s,%s,%s
            )
            """,
            (
                name,
                mode,
                entry,
                prize,
                date
            )
        )

        conn.commit()

    finally:

        cur.close()
        conn.close()

    return redirect(
        url_for("admin_panel")
    )


# =========================================================
# ADMIN ROOM
# =========================================================

@app.route(
    "/admin/room/<int:tournament_id>",
    methods=["POST"]
)
def admin_room(tournament_id):

    if not session.get("admin"):

        return redirect(
            url_for("admin")
        )

    room_id = request.form.get(
        "room_id",
        ""
    ).strip()

    room_password = request.form.get(
        "room_password",
        ""
    ).strip()

    conn = get_db()
    cur = conn.cursor()

    try:

        cur.execute(
            """
            UPDATE tournaments
            SET
                room_id = %s,
                room_password = %s
            WHERE id = %s
            """,
            (
                room_id,
                room_password,
                tournament_id
            )
        )

        conn.commit()

    finally:

        cur.close()
        conn.close()

    return redirect(
        url_for("admin_panel")
    )


# =========================================================
# CLOSE ROOM
# =========================================================

@app.route(
    "/admin/close-room/<int:tournament_id>",
    methods=["POST"]
)
def admin_close_room(tournament_id):

    if not session.get("admin"):

        return redirect(
            url_for("admin")
        )

    conn = get_db()
    cur = conn.cursor()

    try:

        cur.execute(
            """
            UPDATE tournaments
            SET
                room_id = NULL,
                room_password = NULL
            WHERE id = %s
            """,
            (tournament_id,)
        )

        conn.commit()

    finally:

        cur.close()
        conn.close()

    return redirect(
        url_for("admin_panel")
    )


# =========================================================
# DELETE TOURNAMENT
# =========================================================

@app.route(
    "/admin/delete/<int:id>",
    methods=["POST"]
)
def admin_delete(id):

    if not session.get("admin"):

        return redirect(
            url_for("admin")
        )

    conn = get_db()
    cur = conn.cursor()

    try:

        cur.execute(
            """
            DELETE FROM tournaments
            WHERE id = %s
            """,
            (id,)
        )

        conn.commit()

    finally:

        cur.close()
        conn.close()

    return redirect(
        url_for("admin_panel")
    )


# =========================================================
# ADMIN LOGOUT
# =========================================================

@app.route("/admin/logout")
def admin_logout():

    session.pop(
        "admin",
        None
    )

    return redirect(
        url_for("index")
    )


# =========================================================
# HEALTH
# =========================================================

@app.route("/health")
def health():

    try:

        conn = get_db()
        cur = conn.cursor()

        cur.execute("SELECT 1")

        cur.fetchone()

        cur.close()
        conn.close()

        return {
            "status": "ok",
            "database": "connected"
        }

    except Exception as e:

        return {
            "status": "error",
            "database": "disconnected",
            "error": str(e)
        }, 500


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.getenv("PORT", "5000")
        ),
        debug=False
    )
