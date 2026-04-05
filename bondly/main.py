from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bondly.database import init_db
from bondly.routers import auth, subscribe, webhook, mortgage


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Bondly Mortgage Data API",
    description=(
        "Helps South African homeowners retrieve their mortgage and property data "
        "via Lightstone. Powered by bondly.co.za.\n\n"
        "**Flow:**\n"
        "1. `POST /auth/register` — create your account\n"
        "2. `POST /auth/login` — get your JWT token\n"
        "3. `POST /subscribe` — pay to activate access\n"
        "4. `GET /mortgage/search?address=...` — find your property\n"
        "5. `GET /mortgage/report?erf_key=...` — retrieve full mortgage data\n"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://bondly.co.za", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(subscribe.router)
app.include_router(webhook.router)
app.include_router(mortgage.router)


@app.get("/", tags=["info"])
def root():
    return {
        "service": "Bondly Mortgage Data API",
        "powered_by": "Lightstone Property",
        "docs": "/docs",
        "register": "/auth/register",
    }
