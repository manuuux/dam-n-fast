from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routes.assets import router as assets_router
from app.utils.db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(assets_router)


@app.get("/")
def root():
    return {"status": "ok"}
