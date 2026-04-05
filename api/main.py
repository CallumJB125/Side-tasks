from contextlib import asynccontextmanager

import aiosqlite
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import get_settings
from api.database import init_db, _db_path
from api.routers import subscribe, webhook, rates, keys
from api.scheduler import start_scheduler, stop_scheduler
from api.services.scraper_service import seed_from_json

_settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        await seed_from_json(db)
    start_scheduler()

    yield

    # Shutdown
    stop_scheduler()


app = FastAPI(
    title="SA Bank Mortgage & Interest Rates API",
    description=(
        "Access up-to-date interest rates from major South African banks. "
        "Subscribe at `/subscribe` to get an API key."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(subscribe.router)
app.include_router(webhook.router)
app.include_router(rates.router)
app.include_router(keys.router)


@app.get("/", tags=["info"])
def root():
    return {
        "name": "SA Bank Interest Rates API",
        "docs": "/docs",
        "subscribe": "/subscribe/plans",
        "banks_covered": [
            "Nedbank", "Absa", "Standard Bank", "Investec", "African Bank"
        ],
        "note": "FNB and Capitec are bot-protected — rates updated manually when available.",
    }
