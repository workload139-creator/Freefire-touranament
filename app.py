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


# =========================================================
# FLASK CONFIG
# =========================================================

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")
SECRET_KEY = os.environ.get("SECRET_KEY")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is not set")

app.secret_key = SECRET_KEY


# =========================================================
# DATABASE
# =========================================================

def get_db():
    return psycopg2.connect(DATABASE_URL)


def init_db():

    conn = get_db()
    cur = conn.cursor()

    # -----------------------------------------------------
    # TOURNAMENTS
    # -----------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tournaments (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            mode TEXT NOT NULL,
            entry TEXT NOT NULL,
            prize TEXT NOT NULL,
            date TEXT NOT NULL,
            status TEXT NOT NULL
        )
    """)

    # Existing database migration
    cur.execute("""
        ALTER TABLE tournaments
        ADD COLUMN IF NOT EXISTS room_id TEXT
    """)

    cur.execute("""
        ALTER TABLE tournaments
        ADD COLUMN IF NOT EXISTS room_password TEXT
    """)

    # -----------------------------------------------------
    # REGISTRATIONS
    # -----------------------------------------------------

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

    # Existing database migration
    cur.execute("""
        ALTER TABLE registrations
        ADD COLUMN IF NOT EXISTS payment_ref TEXT
    """)

    cur.execute("""
        ALTER TABLE registrations
        ADD COLUMN IF NOT EXISTS payment_status TEXT
        DEFAULT 'Pending'
    """)

    cur.execute("""
        ALTER TABLE registrations
        ADD COLUMN IF NOT EXISTS room_token TEXT
    """)

    # -----------------------------------------------------
    # OLD REGISTRATIONS KE LIYE TOKEN
    # -----------------------------------------------------

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


init_db()


# =========================================================
# HOME
# =========================================================

@app.route("/")
def index():

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


# =========================================================
# TOURNAMENT DETAILS
# =========================================================

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

    # Tournament check
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

    # -----------------------------------------------------
    # POST
    # -----------------------------------------------------

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
        if not player_name:
            cur.close()
            conn.close()
            return "Player name is required"

        if not team_name:
            cur.close()
            conn.close()
            return "Team name is required"

        if not uid:
            cur.close()
            conn.close()
            return "UID is required"

        if not payment_ref:
            cur.close()
            conn.close()
            return "Payment reference is required"

        # -------------------------------------------------
        # SECURE TOKEN
        # -------------------------------------------------

        room_token = secrets.token_urlsafe(32)

        # -------------------------------------------------
        # INSERT REGISTRATION
        # -------------------------------------------------

        cur.execute("""
            INSERT INTO registrations (
                tournament_id,
                player_name,
                team_name,
                uid,
                payment_ref,
                payment_status,
                room_token
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                'Pending',
                %s
            )
            RETURNING id
        """, (
            tournament_id,
            player_name,
            team_name,
            uid,
            payment_ref,
            room_token
        ))

        registration_id = cur.fetchone()[0]

        conn.commit()

        cur.close()
        conn.close()

        # -------------------------------------------------
        # PLAYER SESSION
        # -------------------------------------------------

        session["registration_token"] = room_token
        session["registration_id"] = registration_id

        # Directly My Registration page
        return redirect(
            url_for("my_registration")
        )

    # GET
    cur.close()
    conn.close()

    return render_template(
        "register.html",
        tournament=tournament_data
    )


# =========================================================
# MY REGISTRATION
# =========================================================

@app.route("/my-registration")
def my_registration():

    token = session.get("registration_token")

    if not token:

        return render_template(
            "my_registration.html",
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
    """, (token,))

    registration = cur.fetchone()

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

    tournament_id = request.args.get(
        "tournament_id"
    )

    conn = get_db()
    cur = conn.cursor()

    if tournament_id:

        cur.execute("""
            SELECT
                r.id,
                r.tournament_id,
                r.player_name,
                r.team_name,
                r.uid

            FROM registrations r

            WHERE r.tournament_id = %s
            AND r.payment_status = 'Verified'

            ORDER BY r.id ASC
        """, (tournament_id,))

    else:

        cur.execute("""
            SELECT
                r.id,
                r.tournament_id,
                r.player_name,
                r.team_name,
                r.uid

            FROM registrations r

            WHERE r.payment_status = 'Verified'

            ORDER BY r.id ASC
        """)

    registrations = cur.fetchall()

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

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        admin_username = os.environ.get(
            "ADMIN_USERNAME"
        )

        admin_password_hash = os.environ.get(
            "ADMIN_PASSWORD_HASH"
        )

        if (
            username == admin_username
            and admin_password_hash
            and check_password_hash(
                admin_password_hash,
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

    if session.get("admin"):

        return redirect(
            url_for("admin_panel")
        )

    return render_template(
        "admin.html",
        error=None,
        tournaments=[],
        registrations=[]
    )


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin/panel")
def admin_panel():

    if not session.get("admin"):

        return redirect(
            url_for("admin")
        )

    conn = get_db()
    cur = conn.cursor()

    # -----------------------------------------------------
    # TOURNAMENTS
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # REGISTRATIONS
    # -----------------------------------------------------

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
        error=None,
        tournaments=tournaments,
        registrations=registrations
    )


# =========================================================
# CREATE TOURNAMENT
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

    if not all([
        name,
        mode,
        entry,
        prize,
        date,
        status
    ]):

        return redirect(
            url_for("admin_panel")
        )

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO tournaments (
            name,
            mode,
            entry,
            prize,
            date,
            status
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s
        )
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


# =========================================================
# VERIFY PAYMENT
# =========================================================

@app.route(
    "/admin/verify/<int:registration_id>",
    methods=["POST"]
)
def verify_registration(registration_id):

    if not session.get("admin"):

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


# =========================================================
# REJECT PAYMENT
# =========================================================

@app.route(
    "/admin/reject/<int:registration_id>",
    methods=["POST"]
)
def reject_registration(registration_id):

    if not session.get("admin"):

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


# =========================================================
# ROOM PAGE
# =========================================================

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
            t.name,
            t.room_id,
            t.room_password

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


# =========================================================
# CLOSE ROOM
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

    # Room details remove
    cur.execute("""
        UPDATE tournaments

        SET
            room_id = NULL,
            room_password = NULL

        WHERE id = %s
    """, (tournament_id,))

    # Tournament ke registrations delete
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
        url_for("admin")
    )


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/health")
def health():

    return "OK"


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        ),
        debug=False
    )
