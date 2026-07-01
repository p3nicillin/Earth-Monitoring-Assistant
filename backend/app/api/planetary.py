from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser
from app.core.config import get_settings
from app.schemas.planetary import EarthquakeFeed, SatelliteCatalog
from app.services.planetary import PlanetaryFeedError, PlanetaryOperationsService

router = APIRouter(prefix="/planet", tags=["planetary operations"])


@router.get("/satellites", response_model=SatelliteCatalog)
async def satellites(user: CurrentUser) -> SatelliteCatalog:
    del user
    try:
        return await PlanetaryOperationsService(get_settings()).satellite_catalog()
    except PlanetaryFeedError as exc:
        raise HTTPException(status_code=502, detail="Orbital data feed is unavailable") from exc


@router.get("/earthquakes", response_model=EarthquakeFeed)
async def earthquakes(user: CurrentUser) -> EarthquakeFeed:
    del user
    try:
        return await PlanetaryOperationsService(get_settings()).earthquake_feed()
    except PlanetaryFeedError as exc:
        raise HTTPException(status_code=502, detail="Earthquake feed is unavailable") from exc
