import os
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

DATABASE_URL = os.environ.get("DATABASE_URL")
SECRET_KEY = os.environ.get("SECRET_KEY")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is not set")

app.secret_key = SECRET_KEY


def get_db():
    return psycopg2.connect(DATABASE_URL)


# =========================
# DATABASE
# =========================

def init_db():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tournaments (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            mode TEXT,
            entry TEXT,
            prize TEXT,
            date TEXT,
            status TEXT
        )
    """)

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

    # Payment columns
    cur.execute("""
        ALTER TABLE registrations
        ADD COLUMN IF NOT EXISTS payment_ref TEXT
    """)

    cur.execute("""
        ALTER TABLE registrations
        ADD COLUMN IF NOT EXISTS payment_status TEXT
        DEFAULT 'Pending'
    """)

    # Room columns
    cur.execute("""
        ALTER TABLE tournaments
        ADD COLUMN IF NOT EXISTS room_id TEXT
    """)

    cur.execute("""
        ALTER TABLE tournaments
        ADD COLUMN IF NOT EXISTS room_password TEXT
    """)

    conn.commit()
    cur.close()
    conn.close()


init_db()


# =========================
# HOME
# =========================

@app.route("/")
def home():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
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
# TOURNAMENT
# =========================

@app.route("/tournament/<int:id>")
def tournament(id):

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM tournaments WHERE id=%s",
        (id,)
    )

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
# REGISTER
# =========================

@app.route("/register/<int:tournament_id>", methods=["GET", "POST"])
def register(tournament_id):

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM tournaments WHERE id=%s",
        (tournament_id,)
    )

    tournament_data = cur.fetchone()

    if not tournament_data:
        cur.close()
        conn.close()
        return "Tournament not found", 404

    if request.method == "POST":

        player_name = request.form.get("player_name")
        team_name = request.form.get("team_name")
        uid = request.form.get("uid")
        payment_ref = request.form.get("payment_ref")

        if not all([
            player_name,
            team_name,
            uid,
            payment_ref
        ]):
            cur.close()
            conn.close()
            return "All fields are required", 400

        cur.execute("""
            INSERT INTO registrations
            (
                tournament_id,
                player_name,
                team_name,
                uid,
                payment_ref,
                payment_status
            )
            VALUES (%s, %s, %s, %s, %s, 'Pending')
        """, (
            tournament_id,
            player_name,
            team_name,
            uid,
            payment_ref
        ))

        conn.commit()

        cur.close()
        conn.close()

        return render_template(
            "payment_pending.html"
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

    tournament_id = request.args.get("tournament_id")

    conn = get_db()
    cur = conn.cursor()

    if tournament_id:

        cur.execute("""
            SELECT *
            FROM registrations
            WHERE tournament_id=%s
            AND payment_status='Verified'
            ORDER BY id DESC
        """, (tournament_id,))

    else:

        cur.execute("""
            SELECT *
            FROM registrations
            WHERE payment_status='Verified'
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

@app.route("/admin", methods=["GET", "POST"])
def admin():

    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")

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
            error="Invalid username or password"
        )

    return render_template("admin.html")


# =========================
# ADMIN PANEL
# =========================

@app.route("/admin/panel")
def admin_panel():

    if not session.get("admin"):
        return redirect(
            url_for("admin")
        )

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM tournaments
        ORDER BY id DESC
    """)

    tournaments = cur.fetchall()

    cur.execute("""
        SELECT
            registrations.id,
            registrations.tournament_id,
            registrations.player_name,
            registrations.team_name,
            registrations.uid,
            registrations.payment_ref,
            registrations.payment_status,
            tournaments.name
        FROM registrations
        JOIN tournaments
        ON registrations.tournament_id = tournaments.id
        ORDER BY registrations.id DESC
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
# ADD TOURNAMENT
# =========================

@app.route("/admin/add", methods=["POST"])
def add_tournament():

    if not session.get("admin"):
        return redirect(
            url_for("admin")
        )

    name = request.form.get("name")
    mode = request.form.get("mode")
    entry = request.form.get("entry")
    prize = request.form.get("prize")
    date = request.form.get("date")
    status = request.form.get("status")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO tournaments
        (name, mode, entry, prize, date, status)
        VALUES (%s, %s, %s, %s, %s, %s)
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
# ROOM DETAILS
# =========================

@app.route("/admin/room/<int:tournament_id>", methods=["POST"])
def save_room(tournament_id):

    if not session.get("admin"):
        return redirect(
            url_for("admin")
        )

    room_id = request.form.get("room_id")
    room_password = request.form.get("room_password")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE tournaments
        SET room_id=%s,
            room_password=%s
        WHERE id=%s
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

@app.route("/admin/verify/<int:registration_id>")
def verify_payment(registration_id):

    if not session.get("admin"):
        return redirect(
            url_for("admin")
        )

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE registrations
        SET payment_status='Verified'
        WHERE id=%s
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

@app.route("/admin/reject/<int:registration_id>")
def reject_payment(registration_id):

    if not session.get("admin"):
        return redirect(
            url_for("admin")
        )

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE registrations
        SET payment_status='Rejected'
        WHERE id=%s
    """, (registration_id,))

    conn.commit()

    cur.close()
    conn.close()

    return redirect(
        url_for("admin_panel")
    )


# =========================
# ROOM DETAILS FOR PLAYER
# =========================

@app.route("/room/<int:registration_id>")
def room_details(registration_id):

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            registrations.id,
            registrations.player_name,
            registrations.uid,
            registrations.payment_status,
            tournaments.name,
            tournaments.room_id,
            tournaments.room_password
        FROM registrations
        JOIN tournaments
        ON registrations.tournament_id = tournaments.id
        WHERE registrations.id=%s
    """, (registration_id,))

    registration = cur.fetchone()

    cur.close()
    conn.close()

    if not registration:
        return "Registration not found", 404

    # Only verified player gets room details
    if registration[3] != "Verified":
        return render_template(
            "room.html",
            verified=False,
            registration=registration
        )

    return render_template(
        "room.html",
        verified=True,
        registration=registration
    )


# =========================
# DELETE TOURNAMENT
# =========================

@app.route("/admin/delete/<int:id>")
def delete_tournament(id):

    if not session.get("admin"):
        return redirect(
            url_for("admin")
        )

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM tournaments WHERE id=%s",
        (id,)
    )

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
# HEALTH
# =========================

@app.route("/health")
def health():
    return "OK"


# =========================
# RUN
# =========================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
