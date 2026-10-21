import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from resolver.application.service import ResolverService
from resolver.domain.errors import BotDetectedError, ResolverError
from resolver.presentation.schemas import (
    ErrorSchema,
    ResolutionSchema,
    ResolveRequest,
    StreamSchema,
    TrackSchema,
)

logger = logging.getLogger(__name__)

_STATUS_BY_CODE = {
    "unsupported_input": 422,
    "not_found": 404,
    "unavailable": 404,
    "spotify_unavailable": 404,
    "bot_detected": 503,
    "upstream_error": 502,
}
_ERRORS = {code: {"model": ErrorSchema} for code in set(_STATUS_BY_CODE.values())}

router = APIRouter(prefix="/v1", responses=_ERRORS)


def get_service(request: Request) -> ResolverService:
    """Entrega el servicio de resolución guardado en el estado de la aplicación."""
    return request.app.state.service


@router.post("/resolve", response_model=ResolutionSchema)
async def resolve(
    body: ResolveRequest, service: ResolverService = Depends(get_service)
) -> ResolutionSchema:
    """Resuelve un link o texto de búsqueda en una o más canciones."""
    return ResolutionSchema.from_domain(await service.resolve(body.query))


@router.post("/stream", response_model=StreamSchema)
async def stream(
    body: TrackSchema, service: ResolverService = Depends(get_service)
) -> StreamSchema:
    """Obtiene la URL de audio reproducible de una canción ya resuelta."""
    return StreamSchema.from_domain(await service.stream(body.to_domain()))


def handle_resolver_error(_: Request, exc: ResolverError) -> JSONResponse:
    """Traduce un error de dominio a una respuesta JSON con código estable."""
    if isinstance(exc, BotDetectedError):
        logger.error("DETECCION DE BOT: YouTube pidio verificacion. %s", exc.message)
    else:
        logger.warning("resolver_error code=%s message=%s", exc.code, exc.message)
    status = _STATUS_BY_CODE.get(exc.code, 502)
    return JSONResponse(status_code=status, content={"code": exc.code, "message": exc.message})


def create_app(
    service: ResolverService, on_shutdown: Callable[[], Awaitable[None]] | None = None
) -> FastAPI:
    """Construye la aplicación HTTP con sus rutas, su manejo de errores y su ciclo de vida."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """Cierra los recursos externos cuando el servicio se apaga."""
        yield
        if on_shutdown:
            await on_shutdown()

    app = FastAPI(title="Resolver", version="1.0.0", lifespan=lifespan)
    app.state.service = service
    app.include_router(router)
    app.add_exception_handler(ResolverError, handle_resolver_error)

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Informa que el servicio está vivo."""
        return {"status": "ok"}

    return app
