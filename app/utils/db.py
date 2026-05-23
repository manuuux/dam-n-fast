import logging
import os
import secrets
import time
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash

DB_HOST = os.environ.get("DB_HOST", "db-postgres")
DB_NAME = os.environ.get("DB_NAME", "dashboard_db")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "secretpassword")
DB_PORT = os.environ.get("DB_PORT", "5432")


def get_db_connection(retries: int = 10, delay_seconds: int = 2):
    conn = None
    for attempt in range(retries):
        try:
            conn = psycopg2.connect(
                host=DB_HOST,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                port=DB_PORT,
            )
            conn.autocommit = False
            return conn
        except psycopg2.OperationalError:
            if attempt == retries - 1:
                raise
            time.sleep(delay_seconds)
    return conn


@contextmanager
def db_cursor(dict_cursor: bool = False):
    conn = get_db_connection()
    cursor_factory = RealDictCursor if dict_cursor else None
    cur = conn.cursor(cursor_factory=cursor_factory)
    try:
        yield conn, cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def init_db():
    with db_cursor() as (_, cur):
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'user';")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(20) NOT NULL DEFAULT 'user',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS cdns (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name VARCHAR(120) NOT NULL,
                is_public BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, name)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                id SERIAL PRIMARY KEY,
                cdn_id INTEGER NOT NULL REFERENCES cdns(id) ON DELETE CASCADE,
                key_value VARCHAR(128) UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS cdn_files (
                id SERIAL PRIMARY KEY,
                cdn_id INTEGER NOT NULL REFERENCES cdns(id) ON DELETE CASCADE,
                filename VARCHAR(255) NOT NULL,
                checksum VARCHAR(64),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(cdn_id, filename)
            );
            """
        )
        cur.execute("ALTER TABLE cdn_files ADD COLUMN IF NOT EXISTS checksum VARCHAR(64);")
        cur.execute("SELECT id FROM users WHERE username = %s", ("admin",))
        admin = cur.fetchone()
        if not admin:
            cur.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
                ("admin", generate_password_hash("admin123"), "admin"),
            )
            logging.info("Default admin user created")


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)
