# admin.py

import os

from functools import wraps

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

from werkzeug.security import check_password_hash

from database import get_db


admin = Blueprint(
    "admin",
    __name__
)


# =========================================================
# ADMIN LOGIN REQUIRED
# =========================================================

def admin_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not session.get("admin_logged_in"):
            return redirect(
                url_for("admin.admin_login")
            )

        return function(*args, **kwargs)

    return wrapper


# =========================================================
# ADMIN LOGIN
# =========================================================

@admin.route(
    "/admin/login",
    methods=["GET", "POST"]
)
def admin_login():

    if session.get("admin_logged_in"):
        return redirect(
            url_for("admin.admin_panel")
        )

    if request.method == "GET":
        return render_template(
            "admin.html"
        )

    username = request.form.get(
        "username",
        ""
    ).strip()

    password = request.form.get(
        "password",
        ""
    )

    admin_username = os.getenv(
        "ADMIN_USERNAME"
    )

    admin_password_hash = os.getenv(
        "ADMIN_PASSWORD_HASH"
    )

    if not admin_username or not admin_password_hash:

        flash(
            "Admin environment variables are not configured.",
            "error"
        )

        return redirect(
            url_for("admin.admin_login")
        )

    if (
        username == admin_username
        and check_password_hash(
            admin_password_hash,
            password
        )
    ):

        session.clear()

        session["admin_logged_in"] = True

        session["admin_username"] = username

        return redirect(
            url_for("admin.admin_panel")
        )

    flash(
        "Invalid admin username or password.",
        "error"
    )

    return redirect(
        url_for("admin.admin_login")
    )


# =========================================================
# ADMIN PANEL
# =========================================================

@admin.route("/admin")
@admin_required
def admin_panel():

    conn = get_db()

    try:

        cur = conn.cursor()

        # All tournaments
        cur.execute(
            """
            SELECT *
            FROM tournaments
            ORDER BY id DESC
            """
        )

        tournaments = cur.fetchall()

        # All registrations
        cur.execute(
            """
            SELECT
                r.*,
                t.name AS tournament_name
            FROM registrations r
            LEFT JOIN tournaments t
                ON t.id = r.tournament_id
            ORDER BY r.id DESC
            """
        )

        registrations = cur.fetchall()

        # All players
        cur.execute(
            """
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
            ORDER BY id DESC
            """
        )

        players = cur.fetchall()

    finally:

        conn.close()

    return render_template(
        "admin.html",
        tournaments=tournaments,
        registrations=registrations,
        players=players
    )


# =========================================================
# VERIFY PAYMENT
# =========================================================

@admin.route(
    "/admin/verify-payment/<int:registration_id>",
    methods=["POST"]
)
@admin_required
def verify_payment(registration_id):

    conn = get_db()

    try:

        cur = conn.cursor()

        cur.execute(
            """
            UPDATE registrations
            SET payment_status = 'Verified'
            WHERE id = %s
            """,
            (registration_id,)
        )

        conn.commit()

    except Exception:

        conn.rollback()
        raise

    finally:

        conn.close()

    flash(
        "Payment marked as verified.",
        "success"
    )

    return redirect(
        url_for("admin.admin_panel")
    )


# =========================================================
# REJECT PAYMENT
# =========================================================

@admin.route(
    "/admin/reject-payment/<int:registration_id>",
    methods=["POST"]
)
@admin_required
def reject_payment(registration_id):

    conn = get_db()

    try:

        cur = conn.cursor()

        cur.execute(
            """
            UPDATE registrations
            SET payment_status = 'Rejected'
            WHERE id = %s
            """,
            (registration_id,)
        )

        conn.commit()

    except Exception:

        conn.rollback()
        raise

    finally:

        conn.close()

    flash(
        "Payment marked as rejected.",
        "success"
    )

    return redirect(
        url_for("admin.admin_panel")
    )


# =========================================================
# ADD / UPDATE ROOM
# =========================================================

@admin.route(
    "/admin/room/<int:tournament_id>",
    methods=["POST"]
)
@admin_required
def update_room(tournament_id):

    room_id = request.form.get(
        "room_id",
        ""
    ).strip()

    room_password = request.form.get(
        "room_password",
        ""
    ).strip()

    conn = get_db()

    try:

        cur = conn.cursor()

        cur.execute(
            """
            UPDATE tournaments
            SET
                room_id = %s,
                room_password = %s
            WHERE id = %s
            """,
            (
                room_id,
                room_password,
                tournament_id
            )
        )

        conn.commit()

    except Exception:

        conn.rollback()
        raise

    finally:

        conn.close()

    flash(
        "Room details updated.",
        "success"
    )

    return redirect(
        url_for("admin.admin_panel")
    )


# =========================================================
# CLOSE ROOM
# =========================================================

@admin.route(
    "/admin/close-room/<int:tournament_id>",
    methods=["POST"]
)
@admin_required
def close_room(tournament_id):

    conn = get_db()

    try:

        cur = conn.cursor()

        cur.execute(
            """
            UPDATE tournaments
            SET
                room_id = NULL,
                room_password = NULL
            WHERE id = %s
            """,
            (tournament_id,)
        )

        conn.commit()

    except Exception:

        conn.rollback()
        raise

    finally:

        conn.close()

    flash(
        "Room closed. Registrations were preserved.",
        "success"
    )

    return redirect(
        url_for("admin.admin_panel")
    )


# =========================================================
# DELETE TOURNAMENT
# =========================================================

@admin.route(
    "/admin/delete-tournament/<int:tournament_id>",
    methods=["POST"]
)
@admin_required
def delete_tournament(tournament_id):

    conn = get_db()

    try:

        cur = conn.cursor()

        cur.execute(
            """
            DELETE FROM tournaments
            WHERE id = %s
            """,
            (tournament_id,)
        )

        conn.commit()

    except Exception:

        conn.rollback()
        raise

    finally:

        conn.close()

    flash(
        "Tournament deleted.",
        "success"
    )

    return redirect(
        url_for("admin.admin_panel")
    )


# =========================================================
# PLAYER DETAILS
# =========================================================

@admin.route(
    "/admin/player/<int:user_id>"
)
@admin_required
def admin_player(user_id):

    conn = get_db()

    try:

        cur = conn.cursor()

        cur.execute(
            """
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
            """,
            (user_id,)
        )

        player = cur.fetchone()

        if not player:
            abort(404)

        cur.execute(
            """
            SELECT
                r.*,
                t.name AS tournament_name,
                t.date AS tournament_date
            FROM registrations r
            LEFT JOIN tournaments t
                ON t.id = r.tournament_id
            WHERE r.user_id = %s
            ORDER BY r.id DESC
            """,
            (user_id,)
        )

        registrations = cur.fetchall()

    finally:

        conn.close()

    return render_template(
        "admin_player.html",
        player=player,
        registrations=registrations
    )


# =========================================================
# LOGOUT
# =========================================================

@admin.route(
    "/admin/logout"
)
def admin_logout():

    session.pop(
        "admin_logged_in",
        None
    )

    session.pop(
        "admin_username",
        None
    )

    return redirect(
        url_for("admin.admin_login")
    )
