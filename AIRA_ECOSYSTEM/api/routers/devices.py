from fastapi import APIRouter

from agents.akane.network_tools import list_devices

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.get("")
def devices():
    return list_devices()
