from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from app.config import settings
from app.repositories import RepositoryError
from app.routers import catalogs, tickets
from app.schemas import AuthenticatedUser
from app.security import get_current_user

app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    description="Módulo 1: Intermediario API de Tickets con Patrón Repositorio y Transacciones ACID.",
)


@app.exception_handler(RepositoryError)
async def repository_error_handler(_request: Request, exc: RepositoryError):
    """
    Si falla cualquier paso intermedio de una transacción, tras el ROLLBACK
    devuelve un JSON estructurado indicando qué paso falló y por qué, sin tumbar el servicio.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "ok": False,
            "failed_step": exc.step,
            "detail": exc.message,
        },
    )


app.include_router(catalogs.router)
app.include_router(tickets.router)


@app.get("/health", tags=["Sistema"])
def healthcheck():
    return {"status": "ok", "service": "core-tickets", "version": settings.app_version}


@app.get("/api/v1/auth/me", tags=["Autenticación"])
def get_authenticated_profile(current_user: AuthenticatedUser = Depends(get_current_user)):
    return {
        "user_uuid": str(current_user.user_uuid),
        "username": current_user.username,
        "display_name": current_user.display_name,
        "role": current_user.role,
    }
