import io
import markdown as md
import yaml

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.responses import HTMLResponse
from fastapi.responses import Response
from PIL import Image, UnidentifiedImageError

from app.config import ASSETS_DIR
from app.utils.db import db_cursor

router = APIRouter()

_MARKDOWN_CSS_TEMPLATES = {
    "default": """
body { max-width: 900px; margin: 2rem auto; padding: 0 1rem; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.6; color: #222; }
h1, h2, h3, h4, h5, h6 { line-height: 1.25; }
pre, code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
pre { background: #f6f8fa; padding: 1rem; border-radius: 8px; overflow-x: auto; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
th, td { border: 1px solid #d0d7de; padding: 0.5rem; text-align: left; }
blockquote { border-left: 4px solid #d0d7de; margin: 1rem 0; padding: 0.25rem 1rem; color: #57606a; }
img { max-width: 100%; height: auto; }
""",
    "dark_console": """
body { max-width: 1000px; margin: 1rem auto; padding: 1rem; background: #0b1020; color: #c8f7d6; font-family: "Fira Code", "JetBrains Mono", ui-monospace, monospace; line-height: 1.55; }
a { color: #7ee787; }
h1, h2, h3, h4, h5, h6 { color: #8be9fd; }
pre { background: #0f172a; border: 1px solid #1f2937; border-radius: 10px; padding: 1rem; overflow-x: auto; }
code { color: #f8fafc; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
th, td { border: 1px solid #334155; padding: 0.5rem; }
blockquote { border-left: 4px solid #22c55e; margin: 1rem 0; padding: 0.25rem 1rem; color: #86efac; background: #111827; }
img { max-width: 100%; height: auto; border: 1px solid #334155; border-radius: 8px; }
""",
    "saas_modern": """
body { max-width: 800px; margin: 0 auto; padding: 4rem 1.5rem; font-family: 'Inter', system-ui, sans-serif; color: #1e293b; background: #f8fafc; line-height: 1.7; }
h1 { font-size: 3rem; font-weight: 800; tracking: -0.025em; color: #0f172a; margin-bottom: 1.5rem; text-align: center; }
h2 { font-size: 2rem; margin-top: 3rem; color: #0f172a; border-bottom: 1px solid #e2e8f0; padding-bottom: 0.5rem; }
p { font-size: 1.125rem; color: #475569; }
a { color: #ffffff; background: #4f46e5; padding: 0.75rem 1.5rem; border-radius: 0.5rem; text-decoration: none; font-weight: 600; display: inline-block; margin: 1rem 0; box-shadow: 0 4px 6px -1px rgba(79, 70, 229, 0.2); transition: background 0.2s; }
a:hover { background: #4338ca; }
pre { background: #1e293b; color: #f8fafc; padding: 1.25rem; border-radius: 0.75rem; overflow-x: auto; }
img { max-width: 100%; border-radius: 0.75rem; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.1); margin: 2rem 0; }
""",
    "minimal_mono": """
body { max-width: 700px; margin: 0 auto; padding: 3rem 1rem; font-family: Garamond, Baskerville, "Baskerville Old Face", "Hoefler Text", "Times New Roman", serif; color: #111; background: #fdfdfd; line-height: 1.6; }
h1, h2, h3 { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; font-weight: 700; color: #000; letter-spacing: -0.05em; }
h1 { font-size: 2.5rem; text-transform: uppercase; border-bottom: 2px solid #000; padding-bottom: 1rem; margin-bottom: 2rem; }
h2 { font-size: 1.5rem; margin-top: 2.5rem; }
a { color: #000; text-decoration: underline; text-underline-offset: 4px; font-weight: bold; }
a:hover { background: #000; color: #fff; text-decoration: none; }
blockquote { font-style: italic; border-left: 2px solid #000; padding-left: 1.5rem; margin: 2rem 0; color: #444; }
img { filter: grayscale(100%); max-width: 100%; border: 1px solid #000; padding: 4px; }
""",
    "startup_dark": """
body { max-width: 850px; margin: 0 auto; padding: 4rem 1.5rem; font-family: system-ui, -apple-system, sans-serif; color: #94a3b8; background: #030712; line-height: 1.7; }
h1, h2, h3 { color: #f8fafc; font-weight: 800; }
h1 { font-size: 3.5rem; background: linear-gradient(to right, #581c87, #3b82f6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; text-align: center; margin-bottom: 2rem; }
h2 { font-size: 1.75rem; margin-top: 3rem; border-left: 4px solid #3b82f6; padding-left: 1rem; }
a { color: #030712; background: #3b82f6; padding: 0.8rem 1.8rem; border-radius: 9999px; text-decoration: none; font-weight: 600; display: inline-block; margin: 1rem 0; transition: transform 0.2s; }
a:hover { transform: scale(1.05); background: #60a5fa; }
code { background: #1e293b; color: #e2e8f0; padding: 0.2rem 0.4rem; border-radius: 0.25rem; font-size: 0.875rem; }
pre { background: #111827; border: 1px solid #1f2937; padding: 1.25rem; border-radius: 0.75rem; }
""",
    "neo_brutalism": """
body { max-width: 800px; margin: 2rem auto; padding: 1.5rem; font-family: "Courier New", Courier, monospace; color: #000000; background: #ffde4d; line-height: 1.5; }
h1, h2, h3 { font-family: 'Arial Black', Impact, sans-serif; text-transform: uppercase; color: #000000; }
h1 { font-size: 3.5rem; border: 4px solid #000; background: #ff6b6b; padding: 1.5rem; box-shadow: 8px 8px 0px #000; margin-bottom: 2.5rem; text-align: center; }
h2 { font-size: 2rem; border: 3px solid #000; background: #4dabf7; padding: 0.5rem 1rem; display: inline-block; box-shadow: 4px 4px 0px #000; margin-top: 2.5rem; }
a { color: #000; background: #51cf66; padding: 1rem 2rem; border: 3px solid #000; font-weight: bold; text-decoration: none; display: inline-block; box-shadow: 5px 5px 0px #000; margin: 1.5rem 0; }
a:hover { transform: translate(-2px, -2px); box-shadow: 7px 7px 0px #000; }
a:active { transform: translate(3px, 3px); box-shadow: 2px 2px 0px #000; }
table { border: 4px solid #000; background: #fff; box-shadow: 6px 6px 0px #000; }
th, td { border: 2px solid #000; padding: 0.75rem; font-weight: bold; }
""",
    "warm_editorial": """
body { max-width: 750px; margin: 0 auto; padding: 3rem 1.5rem; font-family: Georgia, serif; color: #2d241e; background: #fbfbf8; line-height: 1.8; font-size: 1.15rem; }
h1, h2, h3 { font-family: system-ui, sans-serif; color: #1c1917; font-weight: 700; }
h1 { font-size: 2.75rem; text-align: center; color: #7c2d12; margin-bottom: 3rem; }
h2 { font-size: 1.6rem; margin-top: 3rem; border-bottom: 1px solid #e7e5e4; padding-bottom: 0.5rem; }
a { color: #c2410c; text-decoration: none; border-bottom: 2px solid #fdba74; font-weight: 600; padding-bottom: 2px; }
a:hover { background: #ffedd5; color: #9a3412; }
blockquote { font-style: italic; color: #7c2d12; background: #fff7ed; border-left: 4px solid #ea580c; padding: 1rem 1.5rem; margin: 2rem 0; border-radius: 0 0.5rem 0.5rem 0; }
img { max-width: 100%; border-radius: 4px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
"""
}


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


def _cdn_base_path(username: str, cdn_name: str):
    return (ASSETS_DIR / username / cdn_name).resolve()


def _safe_file_in_cdn(username: str, cdn_name: str, filename: str):
    base_path = _cdn_base_path(username, cdn_name)
    file_path = (base_path / filename).resolve()
    if base_path != file_path.parent:
        raise HTTPException(status_code=400, detail="Ruta inválida")
    if not file_path.exists() or not file_path.is_file():
        return None
    return file_path


def _parse_res(res: str | None):
    if not res:
        return None
    value = res.strip().lower()
    if "x" not in value:
        raise HTTPException(status_code=400, detail="Formato de res inválido. Use ANCHOxALTO, por ejemplo 600x400")
    width_raw, height_raw = value.split("x", 1)
    if not width_raw.isdigit() or not height_raw.isdigit():
        raise HTTPException(status_code=400, detail="Formato de res inválido. Use ANCHOxALTO, por ejemplo 600x400")
    width = int(width_raw)
    height = int(height_raw)
    if width <= 0 or height <= 0:
        raise HTTPException(status_code=400, detail="res debe tener valores positivos")
    return width, height


def _image_response_with_resize(file_path, resize_to):
    if not resize_to:
        return FileResponse(path=str(file_path))
    try:
        with Image.open(file_path) as img:
            original_format = (img.format or "").upper()
            if original_format not in {"JPEG", "JPG", "PNG", "WEBP", "GIF", "BMP"}:
                return FileResponse(path=str(file_path))
            target_w, target_h = resize_to
            if img.width <= target_w and img.height <= target_h:
                return FileResponse(path=str(file_path))
            out = img.copy()
            out.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)
            if out.mode in {"RGBA", "LA", "P"} and original_format in {"JPEG", "JPG"}:
                out = out.convert("RGB")
            buffer = io.BytesIO()
            save_format = "JPEG" if original_format == "JPG" else original_format
            out.save(buffer, format=save_format, optimize=True)
            content_type = Image.MIME.get(save_format, "application/octet-stream")
            return Response(content=buffer.getvalue(), media_type=content_type)
    except (UnidentifiedImageError, OSError):
        return FileResponse(path=str(file_path))


def _extract_markdown_frontmatter(markdown_text: str):
    if not markdown_text.startswith("---"):
        return {}, markdown_text

    lines = markdown_text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, markdown_text

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return {}, markdown_text

    yaml_block = "\n".join(lines[1:end_idx])
    content = "\n".join(lines[end_idx + 1 :])

    try:
        data = yaml.safe_load(yaml_block) or {}
        if not isinstance(data, dict):
            return {}, content
        return data, content
    except yaml.YAMLError:
        return {}, content


def _markdown_to_html(markdown_text: str) -> str:
    frontmatter, markdown_content = _extract_markdown_frontmatter(markdown_text)
    template_name = str(frontmatter.get("template", "default")).strip().lower()
    css = _MARKDOWN_CSS_TEMPLATES.get(template_name, _MARKDOWN_CSS_TEMPLATES["default"])

    body = md.markdown(
        markdown_content,
        extensions=[
            "extra",
            "sane_lists",
            "pymdownx.tilde",
            "codehilite",
            "nl2br",
            "toc",
        ],
        output_format="html5",
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>README</title>"
        f"<style>{css}</style></head><body>"
        f"{body}</body></html>"
    )


def _serve_cdn_root_content(username: str, cdn_name: str):
    base_path = _cdn_base_path(username, cdn_name)
    if not base_path.exists() or not base_path.is_dir():
        return None

    lower_name_map = {p.name.lower(): p.name for p in base_path.iterdir() if p.is_file()}
    candidates = ("index.html", "index.mhtml", "index.md", "readme.md")
    for filename in candidates:
        real_name = lower_name_map.get(filename)
        if not real_name:
            continue
        file_path = _safe_file_in_cdn(username, cdn_name, real_name)
        if not file_path:
            continue
        if real_name.lower().endswith(".md"):
            return HTMLResponse(content=_markdown_to_html(file_path.read_text(encoding="utf-8")), status_code=200)
        return FileResponse(path=str(file_path))
    return None


def _serve_cdn_markdown_file(username: str, cdn_name: str, cdn_id: int, markdown_filename: str):
    if not markdown_filename.lower().endswith(".md"):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos markdown")

    with db_cursor(dict_cursor=True) as (_, cur):
        cur.execute(
            "SELECT id FROM cdn_files WHERE cdn_id = %s AND filename = %s",
            (cdn_id, markdown_filename),
        )
        exists = cur.fetchone()

    if not exists:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    file_path = _safe_file_in_cdn(username, cdn_name, markdown_filename)
    if not file_path:
        raise HTTPException(status_code=404, detail="Archivo no encontrado en disco")

    return HTMLResponse(content=_markdown_to_html(file_path.read_text(encoding="utf-8")), status_code=200)


@router.get("/{username}/{cdn_name}/json")
def list_cdn_files_json(
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


@router.get("/{cdn_name}/json")
def list_public_admin_cdn_files_json(request: Request, cdn_name: str):
    cdn = _get_public_cdn(cdn_name)
    if not cdn:
        raise HTTPException(status_code=404, detail="CDN no encontrada")
    return _build_listing_response(request, cdn["id"], cdn["username"], cdn_name, True)


@router.get("/{username}/{cdn_name}")
def list_cdn_files(
    request: Request,
    username: str,
    cdn_name: str,
    x_cdn_api_key: str | None = Header(default=None),
    apikey: str | None = Query(default=None),
    md: str | None = Query(default=None),
):
    cdn = _get_cdn(username, cdn_name)
    if not cdn:
        raise HTTPException(status_code=404, detail="CDN no encontrada")

    _assert_access(cdn, apikey or x_cdn_api_key)

    if md:
        return _serve_cdn_markdown_file(username, cdn_name, cdn["id"], md)

    content = _serve_cdn_root_content(username, cdn_name)
    if content is not None:
        return content

    return _build_listing_response(request, cdn["id"], username, cdn_name)


@router.get("/{cdn_name}")
def list_public_admin_cdn_files(
    request: Request,
    cdn_name: str,
    md: str | None = Query(default=None),
):
    cdn = _get_public_cdn(cdn_name)
    if not cdn:
        raise HTTPException(status_code=404, detail="CDN no encontrada")

    if md:
        return _serve_cdn_markdown_file(cdn["username"], cdn_name, cdn["id"], md)

    content = _serve_cdn_root_content(cdn["username"], cdn_name)
    if content is not None:
        return content

    return _build_listing_response(request, cdn["id"], cdn["username"], cdn_name, True)


def _build_listing_response(request: Request, cdn_id: int, username: str, cdn_name: str, short_public: bool = False):
    base_url = str(request.base_url).rstrip("/") + "/api"
    with db_cursor(dict_cursor=True) as (_, cur):
        cur.execute(
            "SELECT filename, checksum, original_width, original_height FROM cdn_files WHERE cdn_id = %s ORDER BY filename",
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
                "original_width": row.get("original_width"),
                "original_height": row.get("original_height"),
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
    res: str | None = Query(default=None),
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

    file_path = _safe_file_in_cdn(username, cdn_name, filename)
    if not file_path:
        raise HTTPException(status_code=404, detail="Archivo no encontrado en disco")

    resize_to = _parse_res(res)
    return _image_response_with_resize(file_path, resize_to)


@router.get("/assets/{cdn_name}/{filename:path}")
def serve_public_asset(
    cdn_name: str,
    filename: str,
    res: str | None = Query(default=None),
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

    file_path = _safe_file_in_cdn(cdn["username"], cdn_name, filename)
    if not file_path:
        raise HTTPException(status_code=404, detail="Archivo no encontrado en disco")

    resize_to = _parse_res(res)
    return _image_response_with_resize(file_path, resize_to)
