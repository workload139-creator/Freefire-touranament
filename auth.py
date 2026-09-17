from flask import Blueprint, request, render_template, redirect, url_for, session, flash

from werkzeug.security import generate_password_hash, check_password_hash

from database import get_db

from utils import (
normalize_email,
normalize_phone,
validate_email,
validate_phone,
clean_text
)

auth = Blueprint("auth", name)

@auth.route("/player/register", methods=["GET", "POST"])
def player_register():

if request.method == "GET":
    return render_template("player_register.html")

player_name = clean_text(request.form.get("player_name"))
ff_uid = clean_text(request.form.get("ff_uid"))
phone = normalize_phone(request.form.get("phone"))
email = normalize_email(request.form.get("email"))

password = request.form.get("password", "")
confirm_password = request.form.get("confirm_password", "")

if not player_name:
    flash("Player name is required.", "error")
    return redirect(url_for("auth.player_register"))

if not ff_uid:
    flash("Free Fire UID is required.", "error")
    return redirect(url_for("auth.player_register"))

if not validate_phone(phone):
    flash("Enter a valid 10 digit Indian mobile number.", "error")
    return redirect(url_for("auth.player_register"))

if not validate_email(email):
    flash("Enter a valid email address.", "error")
    return redirect(url_for("auth.player_register"))

if len(password) < 8:
    flash("Password must be at least 8 characters.", "error")
    return redirect(url_for("auth.player_register"))

if password != confirm_password:
    flash("Passwords do not match.", "error")
    return redirect(url_for("auth.player_register"))

conn = get_db()

try:
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id
        FROM users
        WHERE ff_uid = %s
           OR phone = %s
           OR email = %s
        LIMIT 1
        """,
        (ff_uid, phone, email)
    )

    existing_user = cur.fetchone()

    if existing_user:
        flash(
            "An account with this UID, phone or email already exists.",
            "error"
        )
        return redirect(url_for("auth.player_register"))

    password_hash = generate_password_hash(password)

    cur.execute(
        """
        INSERT INTO users (
            player_name,
            ff_uid,
            phone,
            email,
            password_hash,
            phone_verified,
            email_verified,
            account_status
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s,
            TRUE,
            TRUE,
            'Active'
        )
        RETURNING id
        """,
        (
            player_name,
            ff_uid,
            phone,
            email,
            password_hash
        )
    )

    user = cur.fetchone()

    conn.commit()

except Exception:
    conn.rollback()
    raise

finally:
    conn.close()

flash(
    "Account created successfully. You can now login.",
    "success"
)

return redirect(url_for("auth.player_login"))

@auth.route("/player/login", methods=["GET", "POST"])
def player_login():

if request.method == "GET":
    return render_template("player_login.html")

login_value = clean_text(request.form.get("login"))
password = request.form.get("password", "")

if not login_value or not password:
    flash(
        "Enter your UID/email/phone and password.",
        "error"
    )
    return redirect(url_for("auth.player_login"))

login_value_lower = login_value.lower()
login_phone = normalize_phone(login_value)

conn = get_db()

try:
    cur = conn.cursor()

    cur.execute(
        """
        SELECT *
        FROM users
        WHERE
            ff_uid = %s
            OR phone = %s
            OR LOWER(email) = %s
        LIMIT 1
        """,
        (
            login_value,
            login_phone,
            login_value_lower
        )
    )

    user = cur.fetchone()

finally:
    conn.close()

if not user:
    flash("Invalid login details.", "error")
    return redirect(url_for("auth.player_login"))

if not check_password_hash(
    user["password_hash"],
    password
):
    flash("Invalid login details.", "error")
    return redirect(url_for("auth.player_login"))

if user["account_status"] != "Active":
    flash("Your account is not active.", "error")
    return redirect(url_for("auth.player_login"))

session.clear()

session["user_id"] = user["id"]
session["player_name"] = user["player_name"]
session["ff_uid"] = user["ff_uid"]

return redirect(url_for("player_dashboard"))

@auth.route("/player/logout")
def player_logout():

session.clear()

flash(
    "You have been logged out.",
    "success"
)

return redirect(
    url_for("auth.player_login")
)
