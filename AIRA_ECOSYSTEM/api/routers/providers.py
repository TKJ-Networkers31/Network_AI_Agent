from fastapi import APIRouter

from agents.rei.provider_client import get_active_provider, get_openrouter_credits

router = APIRouter(prefix="/api/providers", tags=["providers"])


@router.get("/credits")
def credits():
    """
    Saldo OpenRouter untuk model DEFAULT saat ini (diatur lewat halaman
    Models). Endpoint list/select provider sudah dihapus dari sini -
    lihat /api/models untuk manajemen model lengkap.
    """
    _, active_config = get_active_provider()

    if not active_config or active_config.get("type") != "openrouter":
        return {"success": False, "error": "Provider aktif bukan OpenRouter (tidak ada saldo)."}

    return get_openrouter_credits()