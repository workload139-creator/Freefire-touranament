import os
import secrets

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

from werkzeug.security import check_password_hash


# =========================================================
# FLASK APP
# =========================================================

app = Flask(__name__)


# =========================================================
# ENVIRONMENT VARIABLES
# =========================================================

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY")

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH")


if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is missing")

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable is missing")


app.secret_key = SECRET_KEY


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_db():
    """
    PostgreSQL database connection.
    """

    return psycopg2.connect(DATABASE_URL)


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

def init_db():

    conn = get_db()
    cur = conn.cursor()

    try:

        # -------------------------------------------------
        # TOURNAMENTS TABLE
        # -------------------------------------------------

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tournaments (

                id SERIAL PRIMARY KEY,

                name TEXT NOT NULL,

                mode TEXT NOT NULL,

                entry INTEGER NOT NULL DEFAULT 0,

                prize TEXT NOT NULL DEFAULT '',

                date TEXT NOT NULL DEFAULT '',

                status TEXT NOT NULL DEFAULT 'Registration Open',

                room_id TEXT,

                room_password TEXT
            )
            """
        )


        # -------------------------------------------------
        # REGISTRATIONS TABLE
        # -------------------------------------------------

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

                room_token TEXT
            )
            """
        )


        # -------------------------------------------------
        # SAFE MIGRATION
        # -------------------------------------------------

        # Existing database me columns missing ho sakte hain.
        # Isliye ADD COLUMN IF NOT EXISTS use kar rahe hain.

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


        # -------------------------------------------------
        # FIX NULL PAYMENT STATUS
        # -------------------------------------------------

        cur.execute(
            """
            UPDATE registrations
            SET payment_status = 'Pending'
            WHERE payment_status IS NULL
            """
        )


        # -------------------------------------------------
        # GENERATE ROOM TOKENS
        # -------------------------------------------------

        cur.execute(
            """
            SELECT id
            FROM registrations
            WHERE room_token IS NULL
            """
        )

        rows = cur.fetchall()

        for row in rows:

            registration_id = row[0]

            token = secrets.token_urlsafe(32)

            cur.execute(
                """
                UPDATE registrations
                SET room_token = %s
                WHERE id = %s
                """,
                (token, registration_id)
            )


        conn.commit()

    except Exception:

        conn.rollback()
        raise

    finally:

        cur.close()
        conn.close()


# Initialize database when application starts
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
# REGISTER
# =========================================================

@app.route(
    "/register/<int:tournament_id>",
    methods=["GET", "POST"]
)
def register(tournament_id):

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
            WHERE id = %s
            """,
            (tournament_id,)
        )

        tournament_data = cur.fetchone()

    finally:

        cur.close()
        conn.close()


    if not tournament_data:

        abort(404)


    # Registration closed
    if tournament_data[6] != "Registration Open":

        return render_template(
            "tournament.html",
            tournament=tournament_data
        )


    # -----------------------------------------------------
    # GET
    # -----------------------------------------------------

    if request.method == "GET":

        return render_template(
            "register.html",
            tournament=tournament_data
        )


    # -----------------------------------------------------
    # POST
    # -----------------------------------------------------

    player_name = request.form.get(
        "player_name",
        ""
    ).strip()

    team_name = request.form.get(
        "team_name",
        ""
    ).strip()

    uid = request.form.get(
        "uid",
        ""
    ).strip()

    payment_ref = request.form.get(
        "payment_ref",
        ""
    ).strip()


    # -----------------------------------------------------
    # VALIDATION
    # -----------------------------------------------------

    if not player_name:

        return render_template(
            "register.html",
            tournament=tournament_data,
            error="Player Name required hai."
        )


    if not team_name:

        return render_template(
            "register.html",
            tournament=tournament_data,
            error="Team Name required hai."
        )


    if not uid:

        return render_template(
            "register.html",
            tournament=tournament_data,
            error="Free Fire UID required hai."
        )


    if not payment_ref:

        return render_template(
            "register.html",
            tournament=tournament_data,
            error="Payment Reference / UTR required hai."
        )


    # -----------------------------------------------------
    # SECURE ROOM TOKEN
    # -----------------------------------------------------

    room_token = secrets.token_urlsafe(32)


    conn = get_db()
    cur = conn.cursor()

    try:

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
                room_token
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s,
                %s,
                'Pending',
                %s
            )
            RETURNING id
            """,
            (
                tournament_id,
                player_name,
                team_name,
                uid,
                payment_ref,
                room_token
            )
        )

        registration_id = cur.fetchone()[0]

        conn.commit()

    except Exception:

        conn.rollback()

        cur.close()
        conn.close()

        raise

    finally:

        try:
            cur.close()
            conn.close()
        except Exception:
            pass


    # -----------------------------------------------------
    # SAVE REGISTRATION SESSION
    # -----------------------------------------------------

    session["registration_token"] = room_token
    session["registration_id"] = registration_id


    return redirect(
        url_for("my_registration")
    )


# =========================================================
# MY REGISTRATION
# =========================================================

@app.route("/my-registration")
def my_registration():

    token = session.get(
        "registration_token"
    )


    if not token:

        return render_template(
            "my_registration.html",
            registration=None
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

                t.id,
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

                r.id,
                r.tournament_id,
                r.player_name,
                r.team_name,
                r.uid,
                r.payment_status,
                t.name

            FROM registrations r

            LEFT JOIN tournaments t
                ON r.tournament_id = t.id

            WHERE r.payment_status = 'Verified'

            ORDER BY r.id ASC
            """
        )

        registrations = cur.fetchall()

    finally:

        cur.close()
        conn.close()


    return render_template(
        "leaderboard.html",
        registrations=registrations
    )


# =========================================================
# ADMIN LOGIN
# =========================================================

@app.route(
    "/admin",
    methods=["GET", "POST"]
)
def admin():

    # Already logged in
    if session.get("admin"):

        return redirect(
            url_for("admin_panel")
        )


    # -----------------------------------------------------
    # GET
    # -----------------------------------------------------

    if request.method == "GET":

        return render_template(
            "admin.html",
            login_page=True
        )


    # -----------------------------------------------------
    # POST
    # -----------------------------------------------------

    username = request.form.get(
        "username",
        ""
    ).strip()

    password = request.form.get(
        "password",
        ""
    )


    if not ADMIN_PASSWORD_HASH:

        return render_template(
            "admin.html",
            login_page=True,
            error=(
                "ADMIN_PASSWORD_HASH Render "
                "Environment Variable missing hai."
            )
        )


    # -----------------------------------------------------
    # CHECK LOGIN
    # -----------------------------------------------------

    if (
        username == ADMIN_USERNAME
        and check_password_hash(
            ADMIN_PASSWORD_HASH,
            password
        )
    ):

        session.clear()

        session["admin"] = True

        return redirect(
            url_for("admin_panel")
        )


    return render_template(
        "admin.html",
        login_page=True,
        error="Invalid username ya password."
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

        # -------------------------------------------------
        # TOURNAMENTS
        # -------------------------------------------------

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


        # -------------------------------------------------
        # REGISTRATIONS
        # -------------------------------------------------

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
                t.name

            FROM registrations r

            LEFT JOIN tournaments t
                ON r.tournament_id = t.id

            ORDER BY r.id DESC
            """
        )

        registrations = cur.fetchall()

    finally:

        cur.close()
        conn.close()


    return render_template(
        "admin.html",
        tournaments=tournaments,
        registrations=registrations,
        login_page=False
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
        ""
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

    status = request.form.get(
        "status",
        "Registration Open"
    ).strip()


    # Safe integer conversion
    try:

        entry = int(entry)

    except ValueError:

        entry = 0


    if not name:

        return redirect(
            url_for("admin_panel")
        )


    if not mode:

        mode = "BR"


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
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            """,
            (
                name,
                mode,
                entry,
                prize,
                date,
                status
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
# ADMIN ROOM DETAILS
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
#
# THIS WAS THE MISSING ENDPOINT IN YOUR ERROR
#
# admin.html:
# url_for('admin_verify', registration_id=r[0])
#
# Now this endpoint exists.
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

    token = session.get(
        "registration_token"
    )


    # No registration session
    if not token:

        return render_template(
            "room.html",
            registration=None,
            verified=False,
            room_ready=False
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


    if not registration:

        return render_template(
            "room.html",
            registration=None,
            verified=False,
            room_ready=False
        )


    # -----------------------------------------------------
    # PAYMENT STATUS
    # -----------------------------------------------------

    verified = (
        registration[4] == "Verified"
    )


    # -----------------------------------------------------
    # ROOM READY
    # -----------------------------------------------------

    room_ready = (
        verified
        and bool(registration[6])
        and bool(registration[7])
    )


    return render_template(
        "room.html",
        registration=registration,
        verified=verified,
        room_ready=room_ready
    )


# =========================================================
# ADMIN CLOSE ROOM
# =========================================================

@app.route(
    "/admin/close-room/<int:tournament_id>",
    methods=["POST"]
)
def close_room(tournament_id):

    if not session.get("admin"):

        return redirect(
            url_for("admin")
        )


    conn = get_db()
    cur = conn.cursor()

    try:

        # -------------------------------------------------
        # REMOVE ROOM DETAILS
        # -------------------------------------------------

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


        # -------------------------------------------------
        # DELETE REGISTRATIONS
        # -------------------------------------------------

        cur.execute(
            """
            DELETE FROM registrations

            WHERE tournament_id = %s
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
# ADMIN DELETE TOURNAMENT
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

    session.clear()

    return redirect(
        url_for("admin")
    )


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/health")
def health():

    try:

        conn = get_db()
        cur = conn.cursor()

        cur.execute("SELECT 1")

        result = cur.fetchone()

        cur.close()
        conn.close()


        if result and result[0] == 1:

            return {
                "status": "ok",
                "database": "connected"
            }


        return {
            "status": "error",
            "database": "unknown"
        }, 500


    except Exception as e:

        return {
            "status": "error",
            "database": "disconnected",
            "message": str(e)
        }, 500


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.getenv(
                "PORT",
                5000
            )
        ),
        debug=False
    )
