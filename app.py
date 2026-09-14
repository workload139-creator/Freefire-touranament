import os
import psycopg2
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")


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

    cur.execute(
        "SELECT COUNT(*) FROM tournaments"
    )

    count = cur.fetchone()[0]

    if count == 0:

        cur.execute("""
            INSERT INTO tournaments
            (name, mode, entry, prize, date, status)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            "FF Squad Championship",
            "Squad",
            "Free",
            "₹1,000",
            "20 September 2026",
            "Registration Open"
        ))

        cur.execute("""
            INSERT INTO tournaments
            (name, mode, entry, prize, date, status)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            "Battle Royale Cup",
            "Squad",
            "Free",
            "₹2,000",
            "25 September 2026",
            "Registration Open"
        ))

    conn.commit()
    cur.close()
    conn.close()


@app.route("/")
def home():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT * FROM tournaments
        ORDER BY id DESC
    """)

    tournaments = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "index.html",
        tournaments=tournaments
    )


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
            (tournament_id, player_name, team_name, uid)
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


@app.route("/admin")
def admin():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT * FROM tournaments
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
        tournaments=tournaments,
        registrations=registrations
    )


@app.route("/admin/add", methods=["POST"])
def add_tournament():

    name = request.form.get("name")
    mode = request.form.get("mode")
    entry = request.form.get("entry")
    prize = request.form.get("prize")
    date = request.form.get("date")

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
        "Registration Open"
    ))

    conn.commit()

    cur.close()
    conn.close()

    return redirect(url_for("admin"))


@app.route(
    "/admin/delete/<int:tournament_id>"
)
def delete_tournament(tournament_id):

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM tournaments WHERE id = %s",
        (tournament_id,)
    )

    conn.commit()

    cur.close()
    conn.close()

    return redirect(url_for("admin"))


@app.route("/health")
def health():
    return "Website and database are working!"


if __name__ == "__main__":

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL environment variable is missing"
        )

    init_db()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
      )
