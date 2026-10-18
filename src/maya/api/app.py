from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from maya.api.routes.chat import router as chat_router
from maya.api.routes.health import router as health_router

app = FastAPI(
    title="Maya API",
    description="API for Maya, your personal AI assistant.",
    version="0.1.0",
)

# Temporary development configuration.
# Restrict this to specific origins before browser-based production use.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8000"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(health_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "name": "Maya",
        "message": "Maya API is running.",
        "docs": "/docs",
    }
