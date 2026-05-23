import os
import secrets
import time
from hashlib import md5
from contextlib import contextmanager
from pathlib import Path

import psycopg2
from flask import Flask, flash, redirect, render_template, request, session, url_for
from psycopg2.extras import RealDictCursor
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "super-secret-key-13579")

DB_HOST = os.environ.get("DB_HOST", "db-postgres")
DB_NAME = os.environ.get("DB_NAME", "dashboard_db")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "secretpassword")
DB_PORT = os.environ.get("DB_PORT", "5432")
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

ASSETS_BASE_DIR = Path("/app/app/assets")


def get_db_connection(retries: int = 10, delay_seconds: int = 2):
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
        cur.execute("SELECT id FROM users WHERE username = %s", (ADMIN_USER,))
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
                (ADMIN_USER, generate_password_hash(ADMIN_PASSWORD), "admin"),
            )


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


init_db()


def current_user():
    username = session.get("username")
    if not username:
        return None
    with db_cursor(dict_cursor=True) as (_, cur):
        cur.execute("SELECT id, username, role FROM users WHERE username = %s", (username,))
        return cur.fetchone()


def require_login():
    if "username" not in session:
        return redirect(url_for("login"))
    return None


def get_user_cdns(user_id: int):
    with db_cursor(dict_cursor=True) as (_, cur):
        cur.execute(
            "SELECT id, name, is_public, created_at FROM cdns WHERE user_id = %s ORDER BY name",
            (user_id,),
        )
        return cur.fetchall()


def get_cdn_for_user(user_id: int, cdn_name: str):
    with db_cursor(dict_cursor=True) as (_, cur):
        cur.execute(
            "SELECT id, name, is_public FROM cdns WHERE user_id = %s AND name = %s",
            (user_id, cdn_name),
        )
        return cur.fetchone()


@app.route("/")
def index():
    guard = require_login()
    if guard:
        return guard

    user = current_user()
    with db_cursor(dict_cursor=True) as (_, cur):
        cur.execute("SELECT COUNT(*)::int AS total FROM cdns WHERE user_id = %s", (user["id"],))
        total_cdns = cur.fetchone()["total"]
        cur.execute(
            """
            SELECT COUNT(*)::int AS total
            FROM cdn_files cf
            JOIN cdns c ON c.id = cf.cdn_id
            WHERE c.user_id = %s
            """,
            (user["id"],),
        )
        total_files = cur.fetchone()["total"]

    return render_template("dashboard.html", user=user, total_cdns=total_cdns, total_files=total_files)


@app.route("/login", methods=["GET", "POST"])
def login():
    if "username" in session:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Por favor ingrese usuario y contraseña.", "error")
            return render_template("login.html")

        with db_cursor(dict_cursor=True) as (_, cur):
            cur.execute("SELECT username, password_hash, role FROM users WHERE username = %s", (username,))
            user = cur.fetchone()

        if user and check_password_hash(user["password_hash"], password):
            session["username"] = user["username"]
            session["role"] = user["role"]
            return redirect(url_for("index"))

        flash("Credenciales incorrectas.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/cdns", methods=["GET", "POST"])
def cdns():
    guard = require_login()
    if guard:
        return guard

    user = current_user()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        is_public = bool(request.form.get("is_public"))

        if not name:
            flash("Debe indicar un nombre para la CDN.", "error")
            return redirect(url_for("cdns"))

        if is_public and user["role"] != "admin":
            flash("Solo admin puede crear CDNs públicas.", "error")
            return redirect(url_for("cdns"))

        with db_cursor() as (_, cur):
            cur.execute(
                "INSERT INTO cdns (user_id, name, is_public) VALUES (%s, %s, %s) ON CONFLICT (user_id, name) DO NOTHING",
                (user["id"], name, is_public),
            )
        (ASSETS_BASE_DIR / user["username"] / name).mkdir(parents=True, exist_ok=True)
        flash("CDN creada o ya existente.", "success")
        return redirect(url_for("cdns"))

    return render_template("cdns.html", user=user, cdns=get_user_cdns(user["id"]))


@app.route("/cdns/<cdn_name>")
def cdn_detail(cdn_name: str):
    guard = require_login()
    if guard:
        return guard

    user = current_user()
    cdn = get_cdn_for_user(user["id"], cdn_name)
    if not cdn:
        flash("CDN no encontrada.", "error")
        return redirect(url_for("cdns"))

    with db_cursor(dict_cursor=True) as (_, cur):
        cur.execute("SELECT filename, checksum, created_at FROM cdn_files WHERE cdn_id = %s ORDER BY filename", (cdn["id"],))
        files = cur.fetchall()
        cur.execute("SELECT id, key_value, created_at FROM api_keys WHERE cdn_id = %s ORDER BY id DESC", (cdn["id"],))
        api_keys = cur.fetchall()

    api_base_url = request.host_url.rstrip("/") + "/api"
    return render_template("cdn_detail.html", user=user, cdn=cdn, files=files, api_keys=api_keys, api_base_url=api_base_url)


@app.route("/users")
def users_admin():
    guard = require_login()
    if guard:
        return guard
    user = current_user()
    if user["role"] != "admin":
        flash("Acceso solo para admin.", "error")
        return redirect(url_for("index"))

    with db_cursor(dict_cursor=True) as (_, cur):
        cur.execute("SELECT id, username, role, created_at FROM users ORDER BY username")
        users = cur.fetchall()
    return render_template("users.html", user=user, users=users)


@app.route("/users/create", methods=["POST"])
def create_user():
    guard = require_login()
    if guard:
        return guard
    user = current_user()
    if user["role"] != "admin":
        flash("Acceso solo para admin.", "error")
        return redirect(url_for("index"))

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "user")
    if not username or not password:
        flash("Usuario y contraseña son obligatorios.", "error")
        return redirect(url_for("users_admin"))
    if role not in {"admin", "user"}:
        role = "user"

    with db_cursor() as (_, cur):
        cur.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s) ON CONFLICT (username) DO NOTHING",
            (username, generate_password_hash(password), role),
        )
    flash("Usuario creado o ya existente.", "success")
    return redirect(url_for("users_admin"))


@app.route("/users/<int:user_id>/update", methods=["POST"])
def update_user(user_id: int):
    guard = require_login()
    if guard:
        return guard
    admin = current_user()
    if admin["role"] != "admin":
        flash("Acceso solo para admin.", "error")
        return redirect(url_for("index"))

    role = request.form.get("role", "user")
    if role not in {"admin", "user"}:
        role = "user"

    with db_cursor() as (_, cur):
        cur.execute("UPDATE users SET role = %s WHERE id = %s", (role, user_id))
    flash("Usuario actualizado.", "success")
    return redirect(url_for("users_admin"))


@app.route("/users/<int:user_id>/password", methods=["POST"])
def update_user_password(user_id: int):
    guard = require_login()
    if guard:
        return guard
    admin = current_user()
    if admin["role"] != "admin":
        flash("Acceso solo para admin.", "error")
        return redirect(url_for("index"))

    password = request.form.get("password", "")
    if not password:
        flash("La contraseña no puede estar vacía.", "error")
        return redirect(url_for("users_admin"))

    with db_cursor() as (_, cur):
        cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (generate_password_hash(password), user_id))
    flash("Contraseña actualizada.", "success")
    return redirect(url_for("users_admin"))


@app.route("/users/<int:user_id>/delete", methods=["POST"])
def delete_user(user_id: int):
    guard = require_login()
    if guard:
        return guard
    admin = current_user()
    if admin["role"] != "admin":
        flash("Acceso solo para admin.", "error")
        return redirect(url_for("index"))

    with db_cursor(dict_cursor=True) as (_, cur):
        cur.execute("SELECT id, username FROM users WHERE id = %s", (user_id,))
        target = cur.fetchone()
        if not target:
            flash("Usuario no encontrado.", "error")
            return redirect(url_for("users_admin"))
        if target["id"] == admin["id"]:
            flash("No puedes eliminar tu propio usuario.", "error")
            return redirect(url_for("users_admin"))

    with db_cursor() as (_, cur):
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    flash("Usuario eliminado.", "success")
    return redirect(url_for("users_admin"))


@app.route("/cdns/<cdn_name>/upload", methods=["POST"])
def upload_file(cdn_name: str):
    guard = require_login()
    if guard:
        return guard

    user = current_user()
    cdn = get_cdn_for_user(user["id"], cdn_name)
    if not cdn:
        flash("CDN no encontrada.", "error")
        return redirect(url_for("cdns"))

    file = request.files.get("file")
    if not file or not file.filename:
        flash("Debe seleccionar un archivo.", "error")
        return redirect(url_for("cdn_detail", cdn_name=cdn_name))

    filename = secure_filename(file.filename)
    if not filename:
        flash("Nombre de archivo inválido.", "error")
        return redirect(url_for("cdn_detail", cdn_name=cdn_name))

    folder = ASSETS_BASE_DIR / user["username"] / cdn_name
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / filename
    file.save(file_path)
    checksum = md5(file_path.read_bytes()).hexdigest()

    with db_cursor() as (_, cur):
        cur.execute(
            """
            INSERT INTO cdn_files (cdn_id, filename, checksum)
            VALUES (%s, %s, %s)
            ON CONFLICT (cdn_id, filename) DO UPDATE SET checksum = EXCLUDED.checksum
            """,
            (cdn["id"], filename, checksum),
        )

    flash("Archivo subido correctamente.", "success")
    return redirect(url_for("cdn_detail", cdn_name=cdn_name))


@app.route("/cdns/<cdn_name>/delete", methods=["POST"])
def delete_file(cdn_name: str):
    guard = require_login()
    if guard:
        return guard

    user = current_user()
    cdn = get_cdn_for_user(user["id"], cdn_name)
    filename = request.form.get("filename", "")

    if not cdn or not filename:
        flash("Solicitud inválida.", "error")
        return redirect(url_for("cdn_detail", cdn_name=cdn_name))

    file_path = (ASSETS_BASE_DIR / user["username"] / cdn_name / filename).resolve()
    folder = (ASSETS_BASE_DIR / user["username"] / cdn_name).resolve()

    if folder not in file_path.parents:
        flash("Ruta inválida.", "error")
        return redirect(url_for("cdn_detail", cdn_name=cdn_name))

    if file_path.exists() and file_path.is_file():
        file_path.unlink()

    with db_cursor() as (_, cur):
        cur.execute("DELETE FROM cdn_files WHERE cdn_id = %s AND filename = %s", (cdn["id"], filename))

    flash("Archivo eliminado.", "success")
    return redirect(url_for("cdn_detail", cdn_name=cdn_name))


@app.route("/cdns/<cdn_name>/delete-cdn", methods=["POST"])
def delete_cdn(cdn_name: str):
    guard = require_login()
    if guard:
        return guard

    user = current_user()
    cdn = get_cdn_for_user(user["id"], cdn_name)
    if not cdn:
        flash("CDN no encontrada.", "error")
        return redirect(url_for("cdns"))

    with db_cursor() as (_, cur):
        cur.execute("DELETE FROM cdns WHERE id = %s AND user_id = %s", (cdn["id"], user["id"]))

    cdn_folder = (ASSETS_BASE_DIR / user["username"] / cdn_name).resolve()
    base_user_folder = (ASSETS_BASE_DIR / user["username"]).resolve()
    if base_user_folder in cdn_folder.parents and cdn_folder.exists():
        for p in sorted(cdn_folder.rglob("*"), reverse=True):
            if p.is_file():
                p.unlink()
            elif p.is_dir():
                p.rmdir()
        cdn_folder.rmdir()

    flash("CDN eliminada.", "success")
    return redirect(url_for("cdns"))


@app.route("/cdns/<cdn_name>/api-keys", methods=["POST"])
def create_api_key(cdn_name: str):
    guard = require_login()
    if guard:
        return guard

    user = current_user()
    cdn = get_cdn_for_user(user["id"], cdn_name)
    if not cdn:
        flash("CDN no encontrada.", "error")
        return redirect(url_for("cdns"))

    key_value = generate_api_key()
    with db_cursor() as (_, cur):
        cur.execute("INSERT INTO api_keys (cdn_id, key_value) VALUES (%s, %s)", (cdn["id"], key_value))

    flash(f"API Key generada: {key_value}", "success")
    return redirect(url_for("cdn_detail", cdn_name=cdn_name))


@app.route("/cdns/<cdn_name>/api-keys/delete", methods=["POST"])
def delete_api_key(cdn_name: str):
    guard = require_login()
    if guard:
        return guard

    user = current_user()
    cdn = get_cdn_for_user(user["id"], cdn_name)
    key_id = request.form.get("key_id")

    if not cdn or not key_id:
        flash("Solicitud inválida.", "error")
        return redirect(url_for("cdn_detail", cdn_name=cdn_name))

    with db_cursor() as (_, cur):
        cur.execute("DELETE FROM api_keys WHERE id = %s AND cdn_id = %s", (key_id, cdn["id"]))

    flash("API Key eliminada.", "success")
    return redirect(url_for("cdn_detail", cdn_name=cdn_name))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8081, debug=True)
