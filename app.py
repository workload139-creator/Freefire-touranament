from flask import Flask, render_template, request, redirect, url_for
import sqlite3

app = Flask(__name__)

DB = "tournament.db"


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS tournaments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            mode TEXT NOT NULL,
            entry TEXT NOT NULL,
            prize TEXT NOT NULL,
            date TEXT NOT NULL,
            status TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS registrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER NOT NULL,
            player_name TEXT NOT NULL,
            team_name TEXT NOT NULL,
            uid TEXT NOT NULL
        )
    """)

    count = conn.execute(
        "SELECT COUNT(*) FROM tournaments"
    ).fetchone()[0]

    if count == 0:
        conn.execute("""
            INSERT INTO tournaments
            (name, mode, entry, prize, date, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            "FF Squad Championship",
            "Squad",
            "Free",
            "₹1,000",
            "20 September 2026",
            "Registration Open"
        ))

        conn.execute("""
            INSERT INTO tournaments
            (name, mode, entry, prize, date, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            "Battle Royale Cup",
            "Squad",
            "Free",
            "₹2,000",
            "25 September 2026",
            "Registration Open"
        ))

    conn.commit()
    conn.close()


@app.route("/")
def home():
    conn = get_db()

    tournaments = conn.execute(
        "SELECT * FROM tournaments ORDER BY id DESC"
    ).fetchall()

    conn.close()

    return render_template(
        "index.html",
        tournaments=tournaments
    )


@app.route("/tournament/<int:tournament_id>")
def tournament(tournament_id):
    conn = get_db()

    tournament_data = conn.execute(
        "SELECT * FROM tournaments WHERE id = ?",
        (tournament_id,)
    ).fetchone()

    conn.close()

    if tournament_data is None:
        return "Tournament not found", 404

    return render_template(
        "tournament.html",
        tournament=tournament_data
    )


@app.route("/register/<int:tournament_id>", methods=["GET", "POST"])
def register(tournament_id):

    conn = get_db()

    tournament_data = conn.execute(
        "SELECT * FROM tournaments WHERE id = ?",
        (tournament_id,)
    ).fetchone()

    if tournament_data is None:
        conn.close()
        return "Tournament not found", 404

    if request.method == "POST":

        player_name = request.form["player_name"]
        team_name = request.form["team_name"]
        uid = request.form["uid"]

        conn.execute("""
            INSERT INTO registrations
            (tournament_id, player_name, team_name, uid)
            VALUES (?, ?, ?, ?)
        """, (
            tournament_id,
            player_name,
            team_name,
            uid
        ))

        conn.commit()
        conn.close()

        return redirect(
            url_for(
                "leaderboard",
                tournament_id=tournament_id
            )
        )

    conn.close()

    return render_template(
        "register.html",
        tournament=tournament_data
    )


@app.route("/leaderboard")
def leaderboard():

    tournament_id = request.args.get("tournament_id")

    conn = get_db()

    if tournament_id:

        tournament_data = conn.execute(
            "SELECT * FROM tournaments WHERE id = ?",
            (tournament_id,)
        ).fetchone()

        registrations = conn.execute("""
            SELECT * FROM registrations
            WHERE tournament_id = ?
            ORDER BY id DESC
        """, (tournament_id,)).fetchall()

    else:

        tournament_data = None

        registrations = conn.execute("""
            SELECT * FROM registrations
            ORDER BY id DESC
        """).fetchall()

    conn.close()

    return render_template(
        "leaderboard.html",
        tournament=tournament_data,
        registrations=registrations
    )


@app.route("/admin")
def admin():

    conn = get_db()

    tournaments = conn.execute(
        "SELECT * FROM tournaments ORDER BY id DESC"
    ).fetchall()

    registrations = conn.execute("""
        SELECT
            registrations.*,
            tournaments.name AS tournament_name
        FROM registrations
        JOIN tournaments
        ON registrations.tournament_id = tournaments.id
        ORDER BY registrations.id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "admin.html",
        tournaments=tournaments,
        registrations=registrations
    )


@app.route("/admin/add", methods=["POST"])
def add_tournament():

    name = request.form["name"]
    mode = request.form["mode"]
    entry = request.form["entry"]
    prize = request.form["prize"]
    date = request.form["date"]

    conn = get_db()

    conn.execute("""
        INSERT INTO tournaments
        (name, mode, entry, prize, date, status)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        name,
        mode,
        entry,
        prize,
        date,
        "Registration Open"
    ))

    conn.commit()
    conn.close()

    return redirect(url_for("admin"))


@app.route("/admin/delete/<int:tournament_id>")
def delete_tournament(tournament_id):

    conn = get_db()

    conn.execute(
        "DELETE FROM registrations WHERE tournament_id = ?",
        (tournament_id,)
    )

    conn.execute(
        "DELETE FROM tournaments WHERE id = ?",
        (tournament_id,)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("admin"))


if __name__ == "__main__":
    init_db()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
)
