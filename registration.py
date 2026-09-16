# registration.py

from flask import (
    Blueprint,
    request,
    render_template,
    redirect,
    url_for,
    session,
    flash,
    abort
)

from database import get_db


registration = Blueprint(
    "registration",
    __name__
)


# =========================================================
# JOIN TOURNAMENT
# =========================================================

@registration.route(
    "/join-tournament/<int:tournament_id>",
    methods=["GET", "POST"]
)
def join_tournament(tournament_id):

    user_id = session.get("user_id")

    if not user_id:
        flash(
            "Please login to join the tournament.",
            "error"
        )
        return redirect(
            url_for("auth.player_login")
        )

    conn = get_db()

    try:
        cur = conn.cursor()

        # Tournament
        cur.execute(
            """
            SELECT *
            FROM tournaments
            WHERE id = %s
            """,
            (tournament_id,)
        )

        tournament_data = cur.fetchone()

        if not tournament_data:
            abort(404)

        # Player
        cur.execute(
            """
            SELECT
                id,
                player_name,
                ff_uid
            FROM users
            WHERE id = %s
            """,
            (user_id,)
        )

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

        # Check existing registration
        cur.execute(
            """
            SELECT *
            FROM registrations
            WHERE tournament_id = %s
              AND user_id = %s
            LIMIT 1
            """,
            (
                tournament_id,
                user_id
            )
        )

        existing = cur.fetchone()

        if request.method == "GET":

            return render_template(
                "join_tournament.html",
                tournament=tournament_data,
                player=player,
                existing=existing
            )

        # -------------------------------------------------
        # POST
        # -------------------------------------------------

        if existing:

            flash(
                "You have already registered for this tournament.",
                "error"
            )

            return redirect(
                url_for(
                    "registration.my_registration",
                    tournament_id=tournament_id
                )
            )

        team_name = request.form.get(
            "team_name",
            ""
        ).strip()

        payment_ref = request.form.get(
            "payment_ref",
            ""
        ).strip()

        if not payment_ref:

            flash(
                "Payment reference/UTR is required.",
                "error"
            )

            return redirect(
                url_for(
                    "registration.join_tournament",
                    tournament_id=tournament_id
                )
            )

        # -------------------------------------------------
        # CREATE REGISTRATION
        # -------------------------------------------------

        cur.execute(
            """
            INSERT INTO registrations (
                tournament_id,
                player_name,
                team_name,
                uid,
                payment_ref,
                payment_status,
                user_id
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
            """,
            (
                tournament_id,
                player["player_name"],
                team_name,
                player["ff_uid"],
                payment_ref,
                user_id
            )
        )

        new_registration = cur.fetchone()

        conn.commit()

    except Exception:

        conn.rollback()
        raise

    finally:

        conn.close()

    flash(
        "Tournament registration submitted. Payment will be verified by admin.",
        "success"
    )

    return redirect(
        url_for(
            "registration.my_registration",
            tournament_id=tournament_id
        )
    )


# =========================================================
# MY REGISTRATION
# =========================================================

@registration.route(
    "/my-registration/<int:tournament_id>"
)
def my_registration(tournament_id):

    user_id = session.get("user_id")

    if not user_id:

        return redirect(
            url_for("auth.player_login")
        )

    conn = get_db()

    try:

        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                r.*,
                t.name AS tournament_name,
                t.mode,
                t.entry,
                t.prize,
                t.date AS tournament_date,
                t.status AS tournament_status
            FROM registrations r
            JOIN tournaments t
                ON t.id = r.tournament_id
            WHERE r.tournament_id = %s
              AND r.user_id = %s
            LIMIT 1
            """,
            (
                tournament_id,
                user_id
            )
        )

        registration_data = cur.fetchone()

    finally:

        conn.close()

    if not registration_data:

        flash(
            "Registration not found.",
            "error"
        )

        return redirect(
            url_for("tournament.tournaments")
        )

    return render_template(
        "my_registration.html",
        registration=registration_data
    )


# =========================================================
# ROOM
# =========================================================

@registration.route(
    "/room/<int:tournament_id>"
)
def room(tournament_id):

    user_id = session.get("user_id")

    if not user_id:

        return redirect(
            url_for("auth.player_login")
        )

    conn = get_db()

    try:

        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                r.payment_status,
                r.room_token,
                t.id,
                t.name,
                t.room_id,
                t.room_password,
                t.status
            FROM registrations r
            JOIN tournaments t
                ON t.id = r.tournament_id
            WHERE r.tournament_id = %s
              AND r.user_id = %s
            LIMIT 1
            """,
            (
                tournament_id,
                user_id
            )
        )

        data = cur.fetchone()

    finally:

        conn.close()

    if not data:

        flash(
            "You are not registered for this tournament.",
            "error"
        )

        return redirect(
            url_for("tournament.tournaments")
        )

    # Payment verification required
    if data["payment_status"] != "Verified":

        flash(
            "Room details will be available after payment verification.",
            "error"
        )

        return redirect(
            url_for(
                "registration.my_registration",
                tournament_id=tournament_id
            )
        )

    return render_template(
        "room.html",
        tournament=data
      )
