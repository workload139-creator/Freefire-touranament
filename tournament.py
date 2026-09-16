# tournament.py

from flask import (
    Blueprint,
    render_template,
    abort
)

from database import get_db


tournament = Blueprint(
    "tournament",
    __name__
)


# =========================================================
# TOURNAMENT LIST
# =========================================================

@tournament.route("/tournaments")
def tournaments():

    conn = get_db()

    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT *
            FROM tournaments
            ORDER BY id DESC
        """)

        tournament_list = cur.fetchall()

    finally:
        conn.close()

    return render_template(
        "index.html",
        tournaments=tournament_list
    )


# =========================================================
# SINGLE TOURNAMENT
# =========================================================

@tournament.route("/tournament/<int:tournament_id>")
def tournament_detail(tournament_id):

    conn = get_db()

    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT *
            FROM tournaments
            WHERE id = %s
        """, (tournament_id,))

        item = cur.fetchone()

    finally:
        conn.close()

    if not item:
        abort(404)

    return render_template(
        "tournament.html",
        tournament=item
    )


# =========================================================
# LEADERBOARD
# =========================================================

@tournament.route("/leaderboard")
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
