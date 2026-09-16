# app.py

import os

from flask import (
    Flask,
    render_template,
    redirect,
    url_for,
    session,
    flash
)

from database import get_db, init_db

from auth import auth
from tournament import tournament
from registration import registration
from admin import admin


# =========================================================
# APP
# =========================================================

app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv(
    "SECRET_KEY",
    "change-this-secret-key"
)


# =========================================================
# BLUEPRINTS
# =========================================================

app.register_blueprint(auth)
app.register_blueprint(tournament)
app.register_blueprint(registration)
app.register_blueprint(admin)


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

try:
    init_db()
    print("✅ Database ready.")

except Exception as e:
    print("❌ Database initialization failed:")
    print(e)


# =========================================================
# HOME
# =========================================================

@app.route("/")
def index():

    conn = get_db()

    try:
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

    finally:
        conn.close()

    return render_template(
        "index.html",
        tournaments=tournaments
    )


# =========================================================
# PLAYER DASHBOARD
# =========================================================

@app.route("/player/dashboard")
def player_dashboard():

    user_id = session.get("user_id")

    # पुराने session को भी support करें
    if not user_id:
        user_id = session.get("player_id")

    if not user_id:

        flash(
            "Please login first.",
            "error"
        )

        return redirect(
            url_for("auth.player_login")
        )

    conn = get_db()

    try:

        cur = conn.cursor()

        # Player information
        cur.execute("""
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
        """, (user_id,))

        player = cur.fetchone()

        if not player:

            session.clear()

            flash(
                "Player account not found.",
                "error"
            )

            return redirect(
                url_for("auth.player_login")
            )

        # Player registrations
        cur.execute("""
            SELECT
                r.id,
                r.tournament_id,
                r.player_name,
                r.team_name,
                r.uid,
                r.payment_ref,
                r.payment_status,
                r.room_token,
                r.joined_at,

                t.name AS tournament_name,
                t.mode,
                t.entry,
                t.prize,
                t.date AS tournament_date,
                t.status AS tournament_status,
                t.room_id,
                t.room_password

            FROM registrations r

            LEFT JOIN tournaments t
                ON t.id = r.tournament_id

            WHERE r.user_id = %s

            ORDER BY r.id DESC
        """, (user_id,))

        registrations = cur.fetchall()

    finally:
        conn.close()

    return render_template(
        "player_dashboard.html",
        player=player,
        registrations=registrations
    )


# =========================================================
# PLAYER PROFILE
# =========================================================

@app.route("/player/profile")
def profile():

    user_id = session.get("user_id")

    if not user_id:
        user_id = session.get("player_id")

    if not user_id:

        return redirect(
            url_for("auth.player_login")
        )

    conn = get_db()

    try:

        cur = conn.cursor()

        cur.execute("""
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
        """, (user_id,))

        player = cur.fetchone()

    finally:
        conn.close()

    if not player:

        session.clear()

        return redirect(
            url_for("auth.player_login")
        )

    return render_template(
        "profile.html",
        player=player
    )


# =========================================================
# TOURNAMENTS PAGE
# =========================================================

@app.route("/tournaments")
def tournaments_page():

    return redirect(
        url_for("tournament.tournaments")
    )


# =========================================================
# LEADERBOARD
# =========================================================

@app.route("/leaderboard")
def leaderboard():

    conn = get_db()

    try:

        cur = conn.cursor()

        cur.execute("""
            SELECT
                player_name,
                uid,
                payment_status,
                joined_at
            FROM registrations
            WHERE payment_status = 'Verified'
            ORDER BY joined_at ASC
        """)

        leaderboard_data = cur.fetchall()

    finally:
        conn.close()

    return render_template(
        "leaderboard.html",
        leaderboard=leaderboard_data
    )


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/health")
def health():

    try:

        conn = get_db()

        try:

            cur = conn.cursor()

            cur.execute("SELECT 1")
            cur.fetchone()

        finally:

            conn.close()

        return {
            "status": "ok",
            "database": "connected"
        }

    except Exception as e:

        return {
            "status": "error",
            "database": "disconnected",
            "message": str(e)
        }, 500


# =========================================================
# 404
# =========================================================

@app.errorhandler(404)
def page_not_found(error):

    return (
        "<h1>404</h1>"
        "<p>Page not found.</p>"
    ), 404


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

#अब repo में पुराने बड़े "app.py" को पूरा हटाकर यही code रखना है।

Structure:

Freefire-touranament/
│
├── app.py              ← नया code
├── database.py
├── auth.py
├── tournament.py
├── registration.py
├── admin.py
├── utils.py
├── rests.txt
│
├── templates/
│   ├── index.html
│   ├── leaderboard.html
│   ├── player_register.html
│   ├── verify_account.html
│   ├── player_login.html
│   ├── player_dashboard.html
│   ├── profile.html
│   ├── tournament.html
│   ├── join_tournament.html
│   ├── my_registration.html
│   ├── room.html
│   ├── admin.html
│   └── admin_player.html
│
└── static/
    ├── style.css
    ├── script.js
    └── qr.png

अभी Deploy मत करना। अगला काम templates को इन routes के साथ match करना है। खासकर "leaderboard.html" जरूरी है, क्योंकि इसी वजह से तुम्हारा पहले "BuildError" आया था।
