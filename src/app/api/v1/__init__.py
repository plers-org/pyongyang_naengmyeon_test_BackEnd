from fastapi import APIRouter

from api.v1 import recommendation

router = APIRouter()
router.include_router(recommendation.router, tags=["recommendation"])
