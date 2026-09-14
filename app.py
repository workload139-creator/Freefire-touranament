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

# Render Environment Variable
app.secret_key = os.environ.get("SECRET_KEY")


def get_db():
    return psycopg2.connect(DATABASE_URL)


def init_db():

    conn = get_db()
    cur = conn.cursor()

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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS registrations (
            id SERIAL PRIMARY KEY,
            tournament_id INTEGER NOT NULL
                REFERENCES tournaments(id)
                ON DELETE CASCADE,
            player_name TEXT NOT NULL,
            team_name TEXT NOT NULL,
            uid TEXT NOT NULL
        )
    """)

    conn.commit()

    cur.close()
    conn.close()


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

@app.route("/tournament/<int:tournament_id>")
def tournament(tournament_id):

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM tournaments WHERE id = %s",
        (tournament_id,)
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

@app.route(
    "/register/<int:tournament_id>",
    methods=["GET", "POST"]
)
def register(tournament_id):

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM tournaments WHERE id = %s",
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

        if not player_name or not team_name or not uid:
            cur.close()
            conn.close()
            return "All fields are required!", 400

        cur.execute("""
            INSERT INTO registrations
            (
                tournament_id,
                player_name,
                team_name,
                uid
            )
            VALUES (%s, %s, %s, %s)
        """, (
            tournament_id,
            player_name,
            team_name,
            uid
        ))

        conn.commit()

        cur.close()
        conn.close()

        return redirect(
            url_for(
                "leaderboard",
                tournament_id=tournament_id
            )
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
        "tournament_id"
    )

    conn = get_db()
    cur = conn.cursor()

    if tournament_id:

        cur.execute(
            "SELECT * FROM tournaments WHERE id = %s",
            (tournament_id,)
        )

        tournament_data = cur.fetchone()

        cur.execute("""
            SELECT *
            FROM registrations
            WHERE tournament_id = %s
            ORDER BY id DESC
        """, (tournament_id,))

    else:

        tournament_data = None

        cur.execute("""
            SELECT *
            FROM registrations
            ORDER BY id DESC
        """)

    registrations = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "leaderboard.html",
        tournament=tournament_data,
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

    # Already logged in
    if session.get("admin_logged_in"):
        return admin_panel()

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

            session["admin_logged_in"] = True

            return redirect(
                url_for("admin")
            )

        return render_template(
            "admin.html",
            login_error="Invalid username or password"
        )

    return render_template("admin.html")


# =========================
# ADMIN PANEL
# =========================

def admin_panel():

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
            registrations.*,
            tournaments.name AS tournament_name
        FROM registrations
        JOIN tournaments
        ON registrations.tournament_id =
           tournaments.id
        ORDER BY registrations.id DESC
    """)

    registrations = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "admin.html",
        logged_in=True,
        tournaments=tournaments,
        registrations=registrations
    )


# =========================
# ADD TOURNAMENT
# =========================

@app.route(
    "/admin/add",
    methods=["POST"]
)
def add_tournament():

    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    name = request.form.get("name")
    mode = request.form.get("mode")
    entry = request.form.get("entry")
    prize = request.form.get("prize")
    date = request.form.get("date")

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
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        name,
        mode,
        entry,
        prize,
        date,
        "Registration Open"
    ))

    conn.commit()

    cur.close()
    conn.close()

    return redirect(
        url_for("admin")
    )


# =========================
# DELETE TOURNAMENT
# =========================

@app.route(
    "/admin/delete/<int:tournament_id>"
)
def delete_tournament(tournament_id):

    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM tournaments WHERE id = %s",
        (tournament_id,)
    )

    conn.commit()

    cur.close()
    conn.close()

    return redirect(
        url_for("admin")
    )


# =========================
# LOGOUT
# =========================

@app.route("/admin/logout")
def admin_logout():

    session.pop(
        "admin_logged_in",
        None
    )

    return redirect(
        url_for("admin")
    )


# =========================
# HEALTH
# =========================

@app.route("/health")
def health():

    return "Website and database are working!"


# =========================
# START
# =========================

if __name__ == "__main__":

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is missing"
        )

    if not app.secret_key:
        raise RuntimeError(
            "SECRET_KEY is missing"
        )

    init_db()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
            )
