from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config.settings import get_settings
from src.routes.router import api_router

settings = get_settings()

app = FastAPI(
    title="Predict Strike Backend",
    version=settings.service_version,
    summary="MVP scaffold for signal snapshots, risk scoring, and market gaps.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_allowed_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)
