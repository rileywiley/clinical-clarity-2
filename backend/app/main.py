from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import (
    attrition_curves,
    auth,
    documents,
    enrollment_weeks,
    exports,
    forecast,
    health,
    org_settings,
    orgs,
    site_trials,
    sites,
    trials,
    users,
    visits,
)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Volume Forecasting Platform", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(orgs.router)
    app.include_router(org_settings.router)
    app.include_router(sites.router)
    app.include_router(attrition_curves.router)
    app.include_router(trials.router)
    app.include_router(visits.router)
    app.include_router(site_trials.router)
    app.include_router(enrollment_weeks.router)
    app.include_router(forecast.router)
    app.include_router(documents.router)
    app.include_router(users.router)
    app.include_router(exports.router)
    return app


app = create_app()
