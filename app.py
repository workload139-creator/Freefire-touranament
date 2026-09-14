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


# =========================================================
# FLASK
# =========================================================

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")
SECRET_KEY = os.environ.get("SECRET_KEY")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing")

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is missing")

app.secret_key = SECRET_KEY


# =========================================================
# DATABASE
# =========================================================

def get_db():
    return psycopg2.connect(DATABASE_URL)


def init_db():

    conn = get_db()
    cur = conn.cursor()

    # -------------------------
    # TOURNAMENTS
    # -------------------------

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

    # -------------------------
    # REGISTRATIONS
    # -------------------------

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

    # Existing database में नए columns जोड़ना
    cur.execute("""
        ALTER TABLE registrations
        ADD COLUMN IF NOT EXISTS payment_ref TEXT
    """)

    cur.execute("""
        ALTER TABLE registrations
        ADD COLUMN IF NOT EXISTS payment_status TEXT
        DEFAULT 'Pending'
    """)

    conn.commit()

    cur.close()
    conn.close()


init_db()


# =========================================================
# HOME
# =========================================================

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


# =========================================================
# TOURNAMENT DETAILS
# =========================================================

@app.route("/tournament/<int:tournament_id>")
def tournament(tournament_id):

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
    """, (tournament_id,))

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
# REGISTER + PAYMENT REFERENCE
# =========================================================

@app.route(
    "/register/<int:tournament_id>",
    methods=["GET", "POST"]
)
def register(tournament_id):

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
    """, (tournament_id,))

    tournament_data = cur.fetchone()

    if not tournament_data:

        cur.close()
        conn.close()

        return "Tournament not found", 404


    # -------------------------
    # POST
    # -------------------------

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


        # Validation
        if not player_name:
            cur.close()
            conn.close()
            return "Player name is required!", 400

        if not team_name:
            cur.close()
            conn.close()
            return "Team name is required!", 400

        if not uid:
            cur.close()
            conn.close()
            return "UID is required!", 400

        if not payment_ref:
            cur.close()
            conn.close()
            return "Payment reference is required!", 400


        # -------------------------
        # SAVE REGISTRATION
        # -------------------------

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
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            tournament_id,
            player_name,
            team_name,
            uid,
            payment_ref,
            "Pending"
        ))

        conn.commit()

        cur.close()
        conn.close()


        return render_template(
            "payment_pending.html",
            player_name=player_name,
            tournament=tournament_data
        )


    cur.close()
    conn.close()

    return render_template(
        "register.html",
        tournament=tournament_data
    )


# =========================================================
# LEADERBOARD
# केवल VERIFIED players
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


        cur.execute("""
            SELECT
                id,
                tournament_id,
                player_name,
                team_name,
                uid,
                payment_ref,
                payment_status
            FROM registrations
            WHERE tournament_id = %s
              AND payment_status = 'Verified'
            ORDER BY id ASC
        """, (tournament_id,))

    else:

        tournament_data = None

        cur.execute("""
            SELECT
                id,
                tournament_id,
                player_name,
                team_name,
                uid,
                payment_ref,
                payment_status
            FROM registrations
            WHERE payment_status = 'Verified'
            ORDER BY id ASC
        """)


    registrations = cur.fetchall()

    cur.close()
    conn.close()


    return render_template(
        "leaderboard.html",
        tournament=tournament_data,
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

    if session.get("admin_logged_in"):
        return admin_panel()


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
            admin_username
            and admin_password_hash
            and username == admin_username
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


    return render_template(
        "admin.html"
    )


# =========================================================
# ADMIN PANEL
# =========================================================

def admin_panel():

    conn = get_db()
    cur = conn.cursor()


    # Tournaments
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


    # Registrations
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
        logged_in=True,
        tournaments=tournaments,
        registrations=registrations
    )


# =========================================================
# VERIFY PAYMENT
# =========================================================

@app.route(
    "/admin/verify/<int:registration_id>"
)
def verify_payment(registration_id):

    if not session.get("admin_logged_in"):

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
        url_for("admin")
    )


# =========================================================
# REJECT PAYMENT
# =========================================================

@app.route(
    "/admin/reject/<int:registration_id>"
)
def reject_payment(registration_id):

    if not session.get("admin_logged_in"):

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
        url_for("admin")
    )


# =========================================================
# ADD TOURNAMENT
# =========================================================

@app.route(
    "/admin/add",
    methods=["POST"]
)
def add_tournament():

    if not session.get("admin_logged_in"):

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


    if (
        not name
        or not mode
        or not entry
        or not prize
        or not date
    ):

        return "All tournament fields are required!", 400


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


# =========================================================
# DELETE TOURNAMENT
# =========================================================

@app.route(
    "/admin/delete/<int:tournament_id>"
)
def delete_tournament(tournament_id):

    if not session.get("admin_logged_in"):

        return redirect(
            url_for("admin")
        )


    conn = get_db()
    cur = conn.cursor()


    cur.execute("""
        DELETE FROM tournaments
        WHERE id = %s
    """, (tournament_id,))


    conn.commit()

    cur.close()
    conn.close()


    return redirect(
        url_for("admin")
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/admin/logout")
def admin_logout():

    session.pop(
        "admin_logged_in",
        None
    )

    return redirect(
        url_for("admin")
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

        result = cur.fetchone()

        cur.close()
        conn.close()

        if result:
            return "Website and database are working!", 200

        return "Database error", 500

    except Exception:
        return "Database error", 500


# =========================================================
# LOCAL
# =========================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
