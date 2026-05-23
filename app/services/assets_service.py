from pathlib import Path

from app.config import ASSETS_DIR, BASE_URL
from app.utils.checksum import md5_file


def list_zone_files(zone: str):

    zone_path = ASSETS_DIR / zone

    try:
        resolved_path = zone_path.resolve()
        resolved_assets_dir = ASSETS_DIR.resolve()
        
        # Ensure the path is a directory and is inside the ASSETS_DIR
        if not resolved_path.is_dir() or resolved_assets_dir not in resolved_path.parents:
            return {"archivos": []}
    except Exception:
        return {"archivos": []}

    files = []

    for file in zone_path.iterdir():

        if file.is_file():

            files.append({
                "nombre": file.name,
                "url": f"{BASE_URL}/assets/{zone}/{file.name}",
                "tamano_bytes": file.stat().st_size,
                "checksum": md5_file(file)
            })

    return {
        "archivos": files
    }