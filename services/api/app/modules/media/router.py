"""Public entry point of the media module (Claude 1.3).

main.py does:  app.include_router(media.router, prefix="/api/v1")
Exposes media + reminders + routines routes under a single APIRouter named ``router``.
"""
from fastapi import APIRouter

from .media_routes import router as _media_router
from .reminders_routes import router as _reminders_router
from .routines_routes import router as _routines_router

router = APIRouter()
router.include_router(_media_router)
router.include_router(_reminders_router)
router.include_router(_routines_router)

__all__ = ["router"]
