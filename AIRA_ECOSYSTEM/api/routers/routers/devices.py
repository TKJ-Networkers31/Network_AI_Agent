from fastapi import APIRouter

from tools.inventory import list_devices

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.get("")
def devices():
    return list_devices()
