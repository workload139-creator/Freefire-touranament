import os
import secrets
import hashlib
import smtplib

from email.message import EmailMessage
from datetime import datetime, timedelta

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
    check_password_hash,
    generate_password_hash
)


# =========================================================
# FLASK APP
# =========================================================

app = Flask(__name__)


# =========================================================
# ENVIRONMENT VARIABLES
# =========================================================

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY")

ADMIN_USERNAME = os.getenv(
    "ADMIN_USERNAME",
    "admin"
)

ADMIN_PASSWORD_HASH = os.getenv(
    "ADMIN_PASSWORD_HASH"
)


# =========================================================
# EMAIL SMTP
# =========================================================

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv(
    "SMTP_FROM",
    SMTP_USERNAME or ""
)


# =========================================================
# SMS PROVIDER
# =========================================================

SMS_API_URL = os.getenv("SMS_API_URL")
SMS_API_KEY = os.getenv("SMS_API_KEY")


# =========================================================
# REQUIRED ENV CHECK
# =========================================================

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL environment variable is missing"
    )

if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY environment variable is missing"
    )

app.secret_key = SECRET_KEY

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


# =========================================================
# DATABASE
# =========================================================

def get_db():
    return psycopg2.connect(DATABASE_URL)


# =========================================================
# OTP HELPERS
# =========================================================

def generate_otp():
    return f"{secrets.randbelow(1000000):06d}"


def hash_otp(otp):
    return hashlib.sha256(
        otp.encode()
    ).hexdigest()


def otp_expired(expires_at):

    if not expires_at:
        return True

    return datetime.utcnow() > expires_at


# =========================================================
# EMAIL OTP
# =========================================================

def send_email_otp(email, otp):

    if not all([
        SMTP_HOST,
        SMTP_USERNAME,
        SMTP_PASSWORD,
        SMTP_FROM
    ]):
        print("SMTP is not configured.")
        print("Email OTP:", otp)
        return False

    try:

        message = EmailMessage()

        message["Subject"] = (
            "FF Tournament Email Verification"
        )

        message["From"] = SMTP_FROM
        message["To"] = email

        message.set_content(
            f"""
FF Tournament

Your email verification OTP is:

{otp}

This OTP will expire in 10 minutes.

If you did not create this account,
you can ignore this email.
"""
        )

        with smtplib.SMTP(
            SMTP_HOST,
            SMTP_PORT
        ) as server:

            server.starttls()

            server.login(
                SMTP_USERNAME,
                SMTP_PASSWORD
            )

            server.send_message(message)

        return True

    except Exception as e:

        print("Email OTP error:", e)
        return False


# =========================================================
# PHONE OTP
# =========================================================

def send_phone_otp(phone, otp):

    """
    SMS provider integration placeholder.

    Real SMS provider API is intentionally not
    hard-coded here.

    Configure SMS_API_URL and SMS_API_KEY
    when an SMS provider is selected.
    """

    if not SMS_API_URL or not SMS_API_KEY:

        print("SMS provider is not configured.")
        print("Phone OTP:", otp)

        return False

    # Provider-specific API code can be added here.

    return False


# =========================================================
# PLAYER HELPERS
# =========================================================

def current_player_id():
    return session.get("player_id")


def player_required():

    player_id = current_player_id()

    if not player_id:

        return redirect(
            url_for("player_login")
        )

    return player_id


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

def init_db():

    conn = get_db()
    cur = conn.cursor()

    try:

        # =================================================
        # TOURNAMENTS
        # =================================================

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


        # =================================================
        # USERS
        # =================================================

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (

                id SERIAL PRIMARY KEY,

                player_name TEXT NOT NULL,

                ff_uid TEXT NOT NULL UNIQUE,

                phone TEXT NOT NULL UNIQUE,

                email TEXT NOT NULL UNIQUE,

                password_hash TEXT NOT NULL,

                phone_verified BOOLEAN NOT NULL
                    DEFAULT FALSE,

                email_verified BOOLEAN NOT NULL
                    DEFAULT FALSE,

                account_status TEXT NOT NULL
                    DEFAULT 'Active',

                phone_otp_hash TEXT,

                phone_otp_expires TIMESTAMP,

                email_otp_hash TEXT,

                email_otp_expires TIMESTAMP,

                created_at TIMESTAMP NOT NULL
                    DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


        # =================================================
        # REGISTRATIONS
        # =================================================

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

                payment_status TEXT NOT NULL
                    DEFAULT 'Pending',

                room_token TEXT,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE SET NULL,

                joined_at TIMESTAMP NOT NULL
                    DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


        # =================================================
        # SAFE MIGRATIONS
        # =================================================

        cur.execute(
            """
            ALTER TABLE tournaments
            ADD COLUMN IF NOT EXISTS room_id TEXT
            """
        )

        cur.execute(
            """
            ALTER TABLE tournaments
            ADD COLUMN IF NOT EXISTS room_password TEXT
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
            ADD COLUMN IF NOT EXISTS room_token TEXT
            """
        )

        cur.execute(
            """
            ALTER TABLE registrations
            ADD COLUMN IF NOT EXISTS user_id INTEGER
            REFERENCES users(id)
            ON DELETE SET NULL
            """
        )

        cur.execute(
            """
            ALTER TABLE registrations
            ADD COLUMN IF NOT EXISTS joined_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP
            """
        )


        # =================================================
        # FIX NULL VALUES
        # =================================================

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


        # =================================================
        # OLD REGISTRATION TOKENS
        # =================================================

        cur.execute(
            """
            SELECT id
            FROM registrations
            WHERE room_token IS NULL
            """
        )

        rows = cur.fetchall()

        for row in rows:

            token = secrets.token_urlsafe(32)

            cur.execute(
                """
                UPDATE registrations
                SET room_token = %s
                WHERE id = %s
                """,
                (
                    token,
                    row[0]
                )
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


    # =====================================================
    # VALIDATION
    # =====================================================

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
            error=(
                "Password कम से कम "
                "8 characters का होना चाहिए."
            )
        )


    conn = get_db()
    cur = conn.cursor()

    try:

        # =================================================
        # CHECK EXISTING ACCOUNT
        # =================================================

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

        existing = cur.fetchone()


        if existing:

            return render_template(
                "player_register.html",
                error=(
                    "FF UID, Phone या Email "
                    "पहले से registered है."
                )
            )


        # =================================================
        # PASSWORD HASH
        # =================================================

        password_hash = generate_password_hash(
            password
        )


        # =================================================
        # OTP
        # =================================================

        phone_otp = generate_otp()
        email_otp = generate_otp()

        now = datetime.utcnow()

        expires = now + timedelta(
            minutes=10
        )


        # =================================================
        # CREATE USER
        # =================================================

        cur.execute(
            """
            INSERT INTO users
            (
                player_name,
                ff_uid,
                phone,
                email,
                password_hash,
                phone_otp_hash,
                phone_otp_expires,
                email_otp_hash,
                email_otp_expires
            )
            VALUES
            (
                %s,%s,%s,%s,%s,
                %s,%s,%s,%s
            )
            RETURNING id
            """,
            (
                player_name,
                ff_uid,
                phone,
                email,
                password_hash,
                hash_otp(phone_otp),
                expires,
                hash_otp(email_otp),
                expires
            )
        )


        player_id = cur.fetchone()[0]

        conn.commit()

    except Exception:

        conn.rollback()

        raise

    finally:

        cur.close()
        conn.close()


    # =====================================================
    # SEND OTP
    # =====================================================

    send_email_otp(
        email,
        email_otp
    )

    send_phone_otp(
        phone,
        phone_otp
    )


    session["verify_player_id"] = player_id

    return redirect(
        url_for("verify_account")
    )


# =========================================================
# ACCOUNT VERIFICATION
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


        if not user:

            return redirect(
                url_for("player_register")
            )


        phone_hash = user[0]
        phone_expires = user[1]

        email_hash = user[2]
        email_expires = user[3]

        phone_verified = user[4]
        email_verified = user[5]


        # =================================================
        # PHONE VERIFY
        # =================================================

        if not phone_verified:

            if not phone_otp:

                return render_template(
                    "verify_account.html",
                    error=(
                        "Phone OTP required hai."
                    )
                )


            if otp_expired(phone_expires):

                return render_template(
                    "verify_account.html",
                    error=(
                        "Phone OTP expire ho gaya."
                    )
                )


            if hash_otp(phone_otp) != phone_hash:

                return render_template(
                    "verify_account.html",
                    error=(
                        "Phone OTP गलत है."
                    )
                )


            cur.execute(
                """
                UPDATE users
                SET
                    phone_verified = TRUE,
                    phone_otp_hash = NULL,
                    phone_otp_expires = NULL
                WHERE id = %s
                """,
                (player_id,)
            )


            phone_verified = True


        # =================================================
        # EMAIL VERIFY
        # =================================================

        if not email_verified:

            if not email_otp:

                return render_template(
                    "verify_account.html",
                    error=(
                        "Email OTP required hai."
                    )
                )


            if otp_expired(email_expires):

                return render_template(
                    "verify_account.html",
                    error=(
                        "Email OTP expire ho गया."
                    )
                )


            if hash_otp(email_otp) != email_hash:

                return render_template(
                    "verify_account.html",
                    error=(
                        "Email OTP गलत है."
                    )
                )


            cur.execute(
                """
                UPDATE users
                SET
                    email_verified = TRUE,
                    email_otp_hash = NULL,
                    email_otp_expires = NULL
                WHERE id = %s
                """,
                (player_id,)
            )


            email_verified = True


        conn.commit()

    except Exception:

        conn.rollback()

        raise

    finally:

        cur.close()
        conn.close()


    # =====================================================
    # BOTH VERIFIED
    # =====================================================

    if phone_verified and email_verified:

        session.pop(
            "verify_player_id",
            None
        )

        session["player_id"] = player_id

        return redirect(
            url_for("player_dashboard")
        )


    return render_template(
        "verify_account.html"
    )


# =========================================================
# PLAYER LOGIN
# =========================================================

@app.route(
    "/player/login",
    methods=["GET", "POST"]
)
def player_login():

    if session.get("player_id"):

        return redirect(
            url_for("player_dashboard")
        )


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

    player_id = current_player_id()


    if not player_id:

        return redirect(
            url_for("player_login")
        )


    conn = get_db()
    cur = conn.cursor()

    try:

        # =================================================
        # PLAYER
        # =================================================

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


        # =================================================
        # REGISTRATIONS
        # =================================================

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
# PLAYER PROFILE
# =========================================================

@app.route("/player/profile")
def player_profile():

    player_id = current_player_id()


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

        session.pop(
            "player_id",
            None
        )

        return redirect(
            url_for("player_login")
        )


    return render_template(
        "profile.html",
        player=player
    )


# =========================================================
# JOIN TOURNAMENT
# =========================================================

@app.route(
    "/join/<int:tournament_id>",
    methods=["GET", "POST"]
)
def join_tournament(tournament_id):

    player_id = current_player_id()


    if not player_id:

        return redirect(
            url_for("player_login")
        )


    conn = get_db()
    cur = conn.cursor()

    try:

        # =================================================
        # TOURNAMENT
        # =================================================

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
            WHERE id = %s
            """,
            (tournament_id,)
        )

        tournament_data = cur.fetchone()


        if not tournament_data:

            abort(404)


        if tournament_data[6] != "Registration Open":

            return render_template(
                "join_tournament.html",
                tournament=tournament_data,
                error=(
                    "Tournament registration बंद है."
                )
            )


        # =================================================
        # PLAYER
        # =================================================

        cur.execute(
            """
            SELECT
                id,
                player_name,
                ff_uid,
                phone_verified,
                email_verified,
                account_status
            FROM users
            WHERE id = %s
            """,
            (player_id,)
        )

        player = cur.fetchone()


        if not player:

            session.pop(
                "player_id",
                None
            )

            return redirect(
                url_for("player_login")
            )


        if player[5] != "Active":

            return render_template(
                "join_tournament.html",
                tournament=tournament_data,
                player=player,
                error="Account active नहीं है."
            )


        if not player[3] or not player[4]:

            session["verify_player_id"] = player_id

            return redirect(
                url_for("verify_account")
            )


        # =================================================
        # POST
        # =================================================

        if request.method == "POST":

            team_name = request.form.get(
                "team_name",
                ""
            ).strip()

            payment_ref = request.form.get(
                "payment_ref",
                ""
            ).strip()


            if not team_name:

                return render_template(
                    "join_tournament.html",
                    tournament=tournament_data,
                    player=player,
                    error=(
                        "Team Name required hai."
                    )
                )


            if not payment_ref:

                return render_template(
                    "join_tournament.html",
                    tournament=tournament_data,
                    player=player,
                    error=(
                        "Payment Reference / UTR required hai."
                    )
                )


            # =================================================
            # DUPLICATE CHECK
            # =================================================

            cur.execute(
                """
                SELECT id
                FROM registrations
                WHERE tournament_id = %s
                  AND user_id = %s
                LIMIT 1
                """,
                (
                    tournament_id,
                    player_id
                )
            )

            existing = cur.fetchone()


            if existing:

                return render_template(
                    "join_tournament.html",
                    tournament=tournament_data,
                    player=player,
                    error=(
                        "Aap is tournament me "
                        "already joined hain."
                    )
                )


            # =================================================
            # ROOM TOKEN
            # =================================================

            room_token = secrets.token_urlsafe(32)


            # =================================================
            # REGISTRATION
            # =================================================

            cur.execute(
                """
                INSERT INTO registrations
                (
                    tournament_id,
                    player_name,
                    team_name,
                    uid,
                    payment_ref,
                    payment_status,
                    room_token,
                    user_id
                )
                VALUES
                (
                    %s,%s,%s,%s,
                    %s,'Pending',%s,%s
                )
                RETURNING id
                """,
                (
                    tournament_id,
                    player[1],
                    team_name,
                    player[2],
                    payment_ref,
                    room_token,
                    player_id
                )
            )


            registration_id = cur.fetchone()[0]

            conn.commit()


            session["player_id"] = player_id
            session["registration_id"] = registration_id


            return redirect(
                url_for("my_registration")
            )


    finally:

        cur.close()
        conn.close()


    return render_template(
        "join_tournament.html",
        tournament=tournament_data,
        player=player
    )


# =========================================================
# OLD REGISTER ROUTE
# =========================================================

@app.route(
    "/register/<int:tournament_id>",
    methods=["GET", "POST"]
)
def old_register(tournament_id):

    if not current_player_id():

        return redirect(
            url_for(
                "player_login",
                next=url_for(
                    "join_tournament",
                    tournament_id=tournament_id
                )
            )
        )

    return redirect(
        url_for(
            "join_tournament",
            tournament_id=tournament_id
        )
    )


# =========================================================
# MY REGISTRATION
# =========================================================

@app.route("/my-registration")
def my_registration():

    player_id = current_player_id()


    # =====================================================
    # NEW ACCOUNT FLOW
    # =====================================================

    if player_id:

        conn = get_db()
        cur = conn.cursor()

        try:

            cur.execute(
                """
                SELECT
                    r.id,
                    r.player_name,
                    r.team_name,
                    r.uid,
                    r.payment_ref,
                    r.payment_status,
                    r.tournament_id,
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
                LIMIT 1
                """,
                (player_id,)
            )

            registration = cur.fetchone()

        finally:

            cur.close()
            conn.close()


        if not registration:

            return render_template(
                "my_registration.html",
                registration=None
            )


        return render_template(
            "my_registration.html",
            registration=registration
        )


    # =====================================================
    # OLD TOKEN FLOW
    # =====================================================

    token = request.args.get(
        "token",
        ""
    ).strip()


    if not token:

        return redirect(
            url_for("player_login")
        )


    conn = get_db()
    cur = conn.cursor()

    try:

        cur.execute(
            """
            SELECT
                r.id,
                r.player_name,
                r.team_name,
                r.uid,
                r.payment_ref,
                r.payment_status,
                r.tournament_id,
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
            WHERE r.room_token = %s
            LIMIT 1
            """,
            (token,)
        )

        registration = cur.fetchone()

    finally:

        cur.close()
        conn.close()


    if not registration:

        return render_template(
            "my_registration.html",
            registration=None,
            error=(
                "Registration नहीं मिली."
            )
        )


    return render_template(
        "my_registration.html",
        registration=registration
    )


# =========================================================
# LEADERBOARD
# =========================================================

@app.route("/leaderboard")
def leaderboard():

    conn = get_db()
    cur = conn.cursor()

    try:

        cur.execute(
            """
            SELECT
                player_name,
                team_name,
                uid
            FROM registrations
            WHERE payment_status = 'Verified'
            ORDER BY id ASC
            """
        )

        players = cur.fetchall()

    finally:

        cur.close()
        conn.close()


    return render_template(
        "leaderboard.html",
        players=players
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
            error=(
                "ADMIN_PASSWORD_HASH configured नहीं है."
            )
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
# ADMIN REQUIRED
# =========================================================

def admin_required():

    if not session.get("admin"):

        return redirect(
            url_for("admin")
        )

    return None


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

        # =================================================
        # TOURNAMENTS
        # =================================================

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


        # =================================================
        # REGISTRATIONS
        # =================================================

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


        # =================================================
        # PLAYERS
        # =================================================

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
# ADMIN PLAYER DETAILS
# =========================================================

@app.route(
    "/admin/player/<int:player_id>"
)
def admin_player(player_id):

    if not session.get("admin"):

        return redirect(
            url_for("admin")
        )


    conn = get_db()
    cur = conn.cursor()

    try:

        # =================================================
        # PLAYER
        # =================================================

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


        if not player:

            abort(404)


        # =================================================
        # REGISTRATION HISTORY
        # =================================================

        cur.execute(
            """
            SELECT
                r.id,
                t.name,
                r.team_name,
                r.uid,
                r.payment_ref,
                r.payment_status,
                t.date,
                t.status
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


    return render_template(
        "admin_player.html",
        player=player,
        registrations=registrations
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
                date,
                status
            )
            VALUES
            (
                %s,%s,%s,%s,%s,
                'Registration Open'
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

    except Exception:

        conn.rollback()

        raise

    finally:

        cur.close()
        conn.close()


    return redirect(
        url_for("admin_panel")
    )


# =========================================================
# ADMIN ADD ROOM
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

    except Exception:

        conn.rollback()

        raise

    finally:

        cur.close()
        conn.close()


    return redirect(
        url_for("admin_panel")
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

    except Exception:

        conn.rollback()

        raise

    finally:

        cur.close()
        conn.close()


    return redirect(
        url_for("admin_panel")
    )


# =========================================================
# ADMIN REJECT PAYMENT
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

    except Exception:

        conn.rollback()

        raise

    finally:

        cur.close()
        conn.close()


    return redirect(
        url_for("admin_panel")
    )


# =========================================================
# ROOM
# =========================================================

@app.route("/room")
def room():

    player_id = current_player_id()


    # =====================================================
    # ACCOUNT FLOW
    # =====================================================

    if player_id:

        conn = get_db()
        cur = conn.cursor()

        try:

            cur.execute(
                """
                SELECT
                    r.id,
                    r.player_name,
                    r.team_name,
                    r.uid,
                    r.payment_status,
                    t.name,
                    t.room_id,
                    t.room_password
                FROM registrations r
                JOIN tournaments t
                    ON r.tournament_id = t.id
                WHERE r.user_id = %s
                ORDER BY r.id DESC
                LIMIT 1
                """,
                (player_id,)
            )

            registration = cur.fetchone()

        finally:

            cur.close()
            conn.close()


        return render_template(
            "room.html",
            registration=registration
        )


    # =====================================================
    # OLD TOKEN FLOW
    # =====================================================

    token = request.args.get(
        "token",
        ""
    ).strip()


    if not token:

        return redirect(
            url_for("player_login")
        )


    conn = get_db()
    cur = conn.cursor()

    try:

        cur.execute(
            """
            SELECT
                r.id,
                r.player_name,
                r.team_name,
                r.uid,
                r.payment_status,
                t.name,
                t.room_id,
                t.room_password
            FROM registrations r
            JOIN tournaments t
                ON r.tournament_id = t.id
            WHERE r.room_token = %s
            LIMIT 1
            """,
            (token,)
        )

        registration = cur.fetchone()

    finally:

        cur.close()
        conn.close()


    return render_template(
        "room.html",
        registration=registration
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

    except Exception:

        conn.rollback()

        raise

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

    except Exception:

        conn.rollback()

        raise

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
# HEALTH CHECK
# =========================================================

@app.route("/health")
def health():

    try:

        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            "SELECT 1"
        )

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
