from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bondly.database import init_db
from bondly.routers import auth, subscribe, webhook, property as property_router, inspect, profile


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Bondly Mortgage Data API",
    description=(
        "Complete South African home loan data for homeowners — powered by bondly.co.za.\n\n"
        "Combines **Deeds Registry** data (property, bonds, ownership, title deed) with "
        "**bank statement parsing** (outstanding balance, interest rate, repayments, arrears).\n\n"
        "**Flow:**\n"
        "1. `POST /auth/register` — create your account\n"
        "2. `POST /auth/login` — get your JWT token\n"
        "3. `POST /subscribe` — pay to activate\n"
        "4. `GET /property/search?q=your+address` — find your property\n"
        "5. `GET /property/report?erf_key=...` — deeds data only\n"
        "6. `POST /property/report/full?erf_key=...` — deeds + statement (upload PDF)\n"
    ),
    version="2.0.0",
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
app.include_router(property_router.router)
app.include_router(inspect.router)
app.include_router(profile.router)


@app.get("/", tags=["info"])
def root():
    return {
        "service": "Bondly Mortgage Data API v2",
        "data_sources": ["Deeds Registry (AfriGIS / Datanamix)", "Bank Statement PDF Parser"],
        "banks_supported": ["Absa", "FNB", "Standard Bank", "Nedbank", "Capitec"],
        "docs": "/docs",
    }
