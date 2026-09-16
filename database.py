# database.py

import os
import psycopg2
from psycopg2.extras import RealDictCursor


def get_database_url():
    """Render/PostgreSQL database URL प्राप्त करें."""
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL environment variable is not configured."
        )

    return database_url


def get_db():
    """PostgreSQL database connection बनाएं."""
    return psycopg2.connect(
        get_database_url(),
        cursor_factory=RealDictCursor
    )


def init_db():
    """Required database tables बनाएं."""
    conn = get_db()

    try:
        cur = conn.cursor()

        # -------------------------
        # USERS TABLE
        # -------------------------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                player_name TEXT NOT NULL,
                ff_uid TEXT NOT NULL UNIQUE,
                phone TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,

                phone_verified BOOLEAN DEFAULT FALSE,
                email_verified BOOLEAN DEFAULT FALSE,

                account_status TEXT DEFAULT 'Active',

                phone_otp_hash TEXT,
                phone_otp_expires TIMESTAMP,

                email_otp_hash TEXT,
                email_otp_expires TIMESTAMP,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # -------------------------
        # TOURNAMENTS TABLE
        # -------------------------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tournaments (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                mode TEXT,
                entry INTEGER DEFAULT 0,
                prize TEXT,
                date TEXT,
                status TEXT DEFAULT 'Open',
                room_id TEXT,
                room_password TEXT
            )
        """)

        # -------------------------
        # REGISTRATIONS TABLE
        # -------------------------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS registrations (
                id SERIAL PRIMARY KEY,

                tournament_id INTEGER
                    REFERENCES tournaments(id)
                    ON DELETE CASCADE,

                player_name TEXT,
                team_name TEXT,
                uid TEXT,
                payment_ref TEXT,

                payment_status TEXT DEFAULT 'Pending',

                room_token TEXT,

                user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE SET NULL,

                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Existing registrations table में user_id नहीं है
        # तो safely add कर दें।
        cur.execute("""
            ALTER TABLE registrations
            ADD COLUMN IF NOT EXISTS user_id INTEGER
        """)

        conn.commit()

        print("✅ Database initialized successfully.")

    except Exception as e:
        conn.rollback()
        print("❌ Database initialization error:", e)
        raise

    finally:
        conn.close()


def fetch_one(query, params=None):
    """एक database record प्राप्त करें."""
    conn = get_db()

    try:
        cur = conn.cursor()
        cur.execute(query, params or ())
        return cur.fetchone()

    finally:
        conn.close()


def fetch_all(query, params=None):
    """Multiple database records प्राप्त करें."""
    conn = get_db()

    try:
        cur = conn.cursor()
        cur.execute(query, params or ())
        return cur.fetchall()

    finally:
        conn.close()


def execute_query(query, params=None, fetch=False):
    """INSERT/UPDATE/DELETE जैसी queries चलाएं."""
    conn = get_db()

    try:
        cur = conn.cursor()
        cur.execute(query, params or ())

        result = None

        if fetch:
            result = cur.fetchall()

        conn.commit()
        return result

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()
