import asyncio
import os
import re
import shutil
import uuid
from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse


CACHE_DIR = Path(os.getenv("CACHE_DIR", "/cache"))
UPSTREAM_BASE_URL = os.getenv("UPSTREAM_BASE_URL", "https://placehold.co").rstrip("/")
CHUNK_SIZE = 1024 * 1024
FILENAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")

app = FastAPI(title="mycache", version="1.0.0")
_download_locks: dict[str, asyncio.Lock] = {}
_download_locks_guard = asyncio.Lock()


def validate_filename(filename: str) -> str:
    if not filename or not FILENAME_RE.fullmatch(filename):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if filename in {".", ".."} or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return filename


def cache_path(filename: str) -> Path:
    return CACHE_DIR / filename


async def lock_for(filename: str) -> asyncio.Lock:
    async with _download_locks_guard:
        lock = _download_locks.get(filename)
        if lock is None:
            lock = asyncio.Lock()
            _download_locks[filename] = lock
        return lock


async def download_to_cache(filename: str) -> Path:
    destination = cache_path(filename)
    if destination.exists():
        return destination

    tmp_dir = CACHE_DIR / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"{filename}.{uuid.uuid4().hex}.part"
    upstream_url = f"{UPSTREAM_BASE_URL}/{quote(filename)}"

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=None) as client:
            async with client.stream("GET", upstream_url) as response:
                if response.status_code == 404:
                    raise HTTPException(status_code=404, detail="Upstream file not found")
                if response.status_code >= 400:
                    raise HTTPException(
                        status_code=502,
                        detail=f"Upstream returned HTTP {response.status_code}",
                    )

                with tmp_path.open("wb") as file_handle:
                    async for chunk in response.aiter_bytes(CHUNK_SIZE):
                        if chunk:
                            file_handle.write(chunk)

        tmp_path.replace(destination)
        return destination
    except HTTPException:
        tmp_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=502, detail=f"Failed to cache upstream file: {exc}") from exc


@app.on_event("startup")
async def startup() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / ".tmp").mkdir(parents=True, exist_ok=True)


@app.get("/healthz")
async def healthz() -> JSONResponse:
    usage = shutil.disk_usage(CACHE_DIR)
    return JSONResponse(
        {
            "status": "ok",
            "cache_dir": str(CACHE_DIR),
            "upstream_base_url": UPSTREAM_BASE_URL,
            "free_bytes": usage.free,
        }
    )


@app.get("/files/{filename}")
async def get_file(filename: str) -> FileResponse:
    safe_filename = validate_filename(filename)
    path = cache_path(safe_filename)

    if not path.exists():
        lock = await lock_for(safe_filename)
        async with lock:
            path = await download_to_cache(safe_filename)

    if not path.is_file():
        raise HTTPException(status_code=404, detail="Cached file not found")

    return FileResponse(path, filename=safe_filename)
