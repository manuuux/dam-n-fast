from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse

from app.config import ASSETS_DIR
from app.utils.db import db_cursor

router = APIRouter()


def _get_cdn(username: str, cdn_name: str):
    with db_cursor(dict_cursor=True) as (_, cur):
        cur.execute(
            """
            SELECT c.id, c.name, c.is_public, u.username
            FROM cdns c
            JOIN users u ON u.id = c.user_id
            WHERE u.username = %s AND c.name = %s
            """,
            (username, cdn_name),
        )
        return cur.fetchone()


def _get_public_cdn(cdn_name: str):
    with db_cursor(dict_cursor=True) as (_, cur):
        cur.execute(
            """
            SELECT c.id, c.name, c.is_public, u.username
            FROM cdns c
            JOIN users u ON u.id = c.user_id
            WHERE c.name = %s AND c.is_public = TRUE
            """,
            (cdn_name,),
        )
        rows = cur.fetchall()
        if len(rows) > 1:
            raise HTTPException(status_code=409, detail="Nombre de CDN público ambiguo")
        return rows[0] if rows else None


def _assert_access(cdn, provided_api_key: str | None):
    if cdn["is_public"]:
        return

    if not provided_api_key:
        raise HTTPException(status_code=401, detail="API Key requerida para CDN privada")

    with db_cursor(dict_cursor=True) as (_, cur):
        cur.execute(
            "SELECT id FROM api_keys WHERE cdn_id = %s AND key_value = %s",
            (cdn["id"], provided_api_key),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=401, detail="API Key inválida")


@router.get("/{username}/{cdn_name}")
def list_cdn_files(
    request: Request,
    username: str,
    cdn_name: str,
    x_cdn_api_key: str | None = Header(default=None),
    apikey: str | None = Query(default=None),
):
    cdn = _get_cdn(username, cdn_name)
    if not cdn:
        raise HTTPException(status_code=404, detail="CDN no encontrada")

    _assert_access(cdn, apikey or x_cdn_api_key)

    return _build_listing_response(request, cdn["id"], username, cdn_name)


@router.get("/{cdn_name}")
def list_public_admin_cdn_files(request: Request, cdn_name: str):
    cdn = _get_public_cdn(cdn_name)
    if not cdn:
        raise HTTPException(status_code=404, detail="CDN no encontrada")
    return _build_listing_response(request, cdn["id"], cdn["username"], cdn_name, True)


def _build_listing_response(request: Request, cdn_id: int, username: str, cdn_name: str, short_public: bool = False):
    base_url = str(request.base_url).rstrip("/") + "/api"
    with db_cursor(dict_cursor=True) as (_, cur):
        cur.execute(
            "SELECT filename, checksum FROM cdn_files WHERE cdn_id = %s ORDER BY filename",
            (cdn_id,),
        )
        files = cur.fetchall()

    return {
        "username": username,
        "cdn": cdn_name,
        "archivos": [
            {
                "nombre": row["filename"],
                "checksum": row.get("checksum"),
                "url": (
                    f"{base_url}/assets/{cdn_name}/{row['filename']}"
                    if short_public
                    else f"{base_url}/assets/{username}/{cdn_name}/{row['filename']}"
                ),
            }
            for row in files
        ],
    }


@router.get("/assets/{username}/{cdn_name}/{filename:path}")
def serve_asset(
    username: str,
    cdn_name: str,
    filename: str,
    x_cdn_api_key: str | None = Header(default=None),
    apikey: str | None = Query(default=None),
):
    cdn = _get_cdn(username, cdn_name)
    if not cdn:
        raise HTTPException(status_code=404, detail="CDN no encontrada")

    _assert_access(cdn, apikey or x_cdn_api_key)

    with db_cursor(dict_cursor=True) as (_, cur):
        cur.execute(
            "SELECT id FROM cdn_files WHERE cdn_id = %s AND filename = %s",
            (cdn["id"], filename),
        )
        exists = cur.fetchone()

    if not exists:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    file_path = (ASSETS_DIR / username / cdn_name / filename).resolve()
    base_path = (ASSETS_DIR / username / cdn_name).resolve()

    if base_path not in file_path.parents:
        raise HTTPException(status_code=400, detail="Ruta inválida")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Archivo no encontrado en disco")

    return FileResponse(path=str(file_path))


@router.get("/assets/{cdn_name}/{filename:path}")
def serve_public_asset(
    cdn_name: str,
    filename: str,
):
    cdn = _get_public_cdn(cdn_name)
    if not cdn:
        raise HTTPException(status_code=404, detail="CDN no encontrada")

    with db_cursor(dict_cursor=True) as (_, cur):
        cur.execute(
            "SELECT id FROM cdn_files WHERE cdn_id = %s AND filename = %s",
            (cdn["id"], filename),
        )
        exists = cur.fetchone()
    if not exists:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    file_path = (ASSETS_DIR / cdn["username"] / cdn_name / filename).resolve()
    base_path = (ASSETS_DIR / cdn["username"] / cdn_name).resolve()
    if base_path not in file_path.parents:
        raise HTTPException(status_code=400, detail="Ruta inválida")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Archivo no encontrado en disco")

    return FileResponse(path=str(file_path))
