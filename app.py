import os
import secrets
import psycopg2

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session
)
from werkzeug.security import check_password_hash


app = Flask(__name__)

# =========================
# ENVIRONMENT VARIABLES
# =========================

DATABASE_URL = os.environ.get("DATABASE_URL")
SECRET_KEY = os.environ.get("SECRET_KEY")

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH")


if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing")

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is missing")

if not ADMIN_PASSWORD_HASH:
    raise RuntimeError("ADMIN_PASSWORD_HASH is missing")


app.secret_key = SECRET_KEY


# =========================
# DATABASE
# =========================

def get_db():
    return psycopg2.connect(DATABASE_URL)


def init_db():

    conn = get_db()
    cur = conn.cursor()

    # -------------------------
    # TOURNAMENTS TABLE
    # -------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tournaments (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            mode TEXT NOT NULL,
            entry TEXT NOT NULL,
            prize TEXT NOT NULL,
            date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Registration Open'
        )
    """)

    # -------------------------
    # ADD ROOM COLUMNS
    # -------------------------

    cur.execute("""
        ALTER TABLE tournaments
        ADD COLUMN IF NOT EXISTS room_id TEXT
    """)

    cur.execute("""
        ALTER TABLE tournaments
        ADD COLUMN IF NOT EXISTS room_password TEXT
    """)

    # -------------------------
    # REGISTRATIONS TABLE
    # -------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS registrations (
            id SERIAL PRIMARY KEY,
            tournament_id INTEGER
                REFERENCES tournaments(id)
                ON DELETE CASCADE,
            player_name TEXT NOT NULL,
            team_name TEXT NOT NULL,
            uid TEXT NOT NULL
        )
    """)

    # -------------------------
    # PAYMENT COLUMNS
    # -------------------------

    cur.execute("""
        ALTER TABLE registrations
        ADD COLUMN IF NOT EXISTS payment_ref TEXT
    """)

    cur.execute("""
        ALTER TABLE registrations
        ADD COLUMN IF NOT EXISTS payment_status TEXT DEFAULT 'Pending'
    """)

    # -------------------------
    # SECURE ROOM TOKEN
    # -------------------------

    cur.execute("""
        ALTER TABLE registrations
        ADD COLUMN IF NOT EXISTS room_token TEXT
    """)

    # Old registrations without token
    cur.execute("""
        SELECT id
        FROM registrations
        WHERE room_token IS NULL
    """)

    old_rows = cur.fetchall()

    for row in old_rows:
        token = secrets.token_urlsafe(32)

        cur.execute("""
            UPDATE registrations
            SET room_token = %s
            WHERE id = %s
        """, (token, row[0]))

    conn.commit()

    cur.close()
    conn.close()


# Initialize database
init_db()


# =========================
# ADMIN CHECK
# =========================

def admin_required():

    return session.get("admin") is True


# =========================
# HOME
# =========================

@app.route("/")
def home():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
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
    """)

    tournaments = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "index.html",
        tournaments=tournaments
    )


# =========================
# TOURNAMENT DETAILS
# =========================

@app.route("/tournament/<int:id>")
def tournament(id):

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
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
    """, (id,))

    tournament_data = cur.fetchone()

    cur.close()
    conn.close()

    if not tournament_data:
        return "Tournament not found", 404

    return render_template(
        "tournament.html",
        tournament=tournament_data
    )


# =========================
# REGISTER PLAYER
# =========================

@app.route(
    "/register/<int:tournament_id>",
    methods=["GET", "POST"]
)
def register(tournament_id):

    conn = get_db()
    cur = conn.cursor()

    # Get tournament
    cur.execute("""
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
    """, (tournament_id,))

    tournament_data = cur.fetchone()

    if not tournament_data:
        cur.close()
        conn.close()
        return "Tournament not found", 404

    # Registration closed
    if tournament_data[6] != "Registration Open":

        cur.close()
        conn.close()

        return """
        <h2>Registration Closed</h2>
        <a href="/">Go Home</a>
        """

    if request.method == "POST":

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

        # Required fields
        if not player_name or not team_name or not uid:
            cur.close()
            conn.close()

            return "All player details are required", 400

        if not payment_ref:
            cur.close()
            conn.close()

            return "Payment reference is required", 400

        # Generate secure room token
        room_token = secrets.token_urlsafe(32)

        cur.execute("""
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
            (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            tournament_id,
            player_name,
            team_name,
            uid,
            payment_ref,
            "Pending",
            room_token
        ))

        registration_id = cur.fetchone()[0]

        conn.commit()

        cur.close()
        conn.close()

        # Save secure token in browser session
        session["registration_token"] = room_token
        session["registration_id"] = registration_id

        return render_template(
            "payment_pending.html",
            registration_id=registration_id
        )

    cur.close()
    conn.close()

    return render_template(
        "register.html",
        tournament=tournament_data
    )


# =========================
# LEADERBOARD
# =========================

@app.route("/leaderboard")
def leaderboard():

    tournament_id = request.args.get(
        "tournament_id",
        type=int
    )

    conn = get_db()
    cur = conn.cursor()

    if tournament_id:

        cur.execute("""
            SELECT
                id,
                tournament_id,
                player_name,
                team_name,
                uid
            FROM registrations
            WHERE tournament_id = %s
            AND payment_status = 'Verified'
            ORDER BY id DESC
        """, (tournament_id,))

    else:

        cur.execute("""
            SELECT
                id,
                tournament_id,
                player_name,
                team_name,
                uid
            FROM registrations
            WHERE payment_status = 'Verified'
            ORDER BY id DESC
        """)

    registrations = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "leaderboard.html",
        registrations=registrations
    )


# =========================
# ADMIN LOGIN
# =========================

@app.route(
    "/admin",
    methods=["GET", "POST"]
)
def admin():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        if (
            username == ADMIN_USERNAME
            and check_password_hash(
                ADMIN_PASSWORD_HASH,
                password
            )
        ):

            session["admin"] = True

            return redirect(
                url_for("admin_panel")
            )

        return render_template(
            "admin.html",
            error="Invalid username or password",
            tournaments=[],
            registrations=[]
        )

    if admin_required():

        return redirect(
            url_for("admin_panel")
        )

    return render_template(
        "admin.html",
        tournaments=[],
        registrations=[]
    )


# =========================
# ADMIN DASHBOARD
# =========================

@app.route("/admin/panel")
def admin_panel():

    if not admin_required():
        return redirect(
            url_for("admin")
        )

    conn = get_db()
    cur = conn.cursor()

    # -------------------------
    # ALL TOURNAMENTS
    # -------------------------

    cur.execute("""
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
    """)

    tournaments = cur.fetchall()

    # -------------------------
    # ALL PLAYER REGISTRATIONS
    # -------------------------

    cur.execute("""
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
    """)

    registrations = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "admin.html",
        tournaments=tournaments,
        registrations=registrations
    )


# =========================
# CREATE TOURNAMENT
# =========================

@app.route(
    "/admin/add",
    methods=["POST"]
)
def admin_add():

    if not admin_required():
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
        ""
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

    if not name or not mode or not entry or not prize or not date:

        return redirect(
            url_for("admin_panel")
        )

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
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
        (%s, %s, %s, %s, %s, %s)
    """, (
        name,
        mode,
        entry,
        prize,
        date,
        status
    ))

    conn.commit()

    cur.close()
    conn.close()

    return redirect(
        url_for("admin_panel")
    )


# =========================
# SET ROOM
# =========================

@app.route(
    "/admin/room/<int:tournament_id>",
    methods=["POST"]
)
def admin_room(tournament_id):

    if not admin_required():
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

    cur.execute("""
        UPDATE tournaments
        SET
            room_id = %s,
            room_password = %s
        WHERE id = %s
    """, (
        room_id,
        room_password,
        tournament_id
    ))

    conn.commit()

    cur.close()
    conn.close()

    return redirect(
        url_for("admin_panel")
    )


# =========================
# VERIFY PAYMENT
# =========================

@app.route(
    "/admin/verify/<int:registration_id>",
    methods=["POST"]
)
def admin_verify(registration_id):

    if not admin_required():
        return redirect(
            url_for("admin")
        )

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE registrations
        SET payment_status = 'Verified'
        WHERE id = %s
    """, (registration_id,))

    conn.commit()

    cur.close()
    conn.close()

    return redirect(
        url_for("admin_panel")
    )


# =========================
# REJECT PAYMENT
# =========================

@app.route(
    "/admin/reject/<int:registration_id>",
    methods=["POST"]
)
def admin_reject(registration_id):

    if not admin_required():
        return redirect(
            url_for("admin")
        )

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE registrations
        SET payment_status = 'Rejected'
        WHERE id = %s
    """, (registration_id,))

    conn.commit()

    cur.close()
    conn.close()

    return redirect(
        url_for("admin_panel")
    )


# =========================
# PLAYER ROOM
# =========================

@app.route("/room")
def room():

    token = session.get(
        "registration_token"
    )

    if not token:
        return render_template(
            "room.html",
            registration=None
        )

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            r.id,
            r.player_name,
            r.team_name,
            r.uid,
            r.payment_status,
            t.room_id,
            t.room_password,
            t.name
        FROM registrations r
        JOIN tournaments t
            ON r.tournament_id = t.id
        WHERE r.room_token = %s
    """, (token,))

    registration = cur.fetchone()

    cur.close()
    conn.close()

    return render_template(
        "room.html",
        registration=registration
    )


# =========================
# CLOSE ROOM
# =========================

@app.route(
    "/admin/close-room/<int:tournament_id>",
    methods=["POST"]
)
def close_room(tournament_id):

    if not admin_required():
        return redirect(
            url_for("admin")
        )

    conn = get_db()
    cur = conn.cursor()

    # Remove room details
    cur.execute("""
        UPDATE tournaments
        SET
            room_id = NULL,
            room_password = NULL
        WHERE id = %s
    """, (tournament_id,))

    # Remove all players of this tournament
    cur.execute("""
        DELETE FROM registrations
        WHERE tournament_id = %s
    """, (tournament_id,))

    conn.commit()

    cur.close()
    conn.close()

    return redirect(
        url_for("admin_panel")
    )


# =========================
# DELETE TOURNAMENT
# =========================

@app.route(
    "/admin/delete/<int:id>",
    methods=["POST"]
)
def admin_delete(id):

    if not admin_required():
        return redirect(
            url_for("admin")
        )

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM tournaments
        WHERE id = %s
    """, (id,))

    conn.commit()

    cur.close()
    conn.close()

    return redirect(
        url_for("admin_panel")
    )


# =========================
# LOGOUT
# =========================

@app.route("/admin/logout")
def admin_logout():

    session.pop("admin", None)

    return redirect(
        url_for("admin")
    )


# =========================
# HEALTH CHECK
# =========================

@app.route("/health")
def health():

    return {
        "status": "ok",
        "database": "connected"
    }


# =========================
# RUN
# =========================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
