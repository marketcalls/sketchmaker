"""What each priced option costs, for the prices shown across the app."""

from fastapi import APIRouter

from app.dependencies import CurrentUser
from app.services.pricing import cost_table

router = APIRouter()


@router.get("/costs")
def get_costs(_user: CurrentUser):
    return {"models": cost_table()}
