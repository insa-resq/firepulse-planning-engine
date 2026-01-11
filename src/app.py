import asyncio
import logging
import contextlib
from typing import AsyncGenerator, Literal, TypedDict

from fastapi import FastAPI

from src.router import router
from src.utils.config import settings
from src.utils.remote_client import remote_client
from src.worker import worker_processor

RootResponse = TypedDict("RootResponse", {"message": str})
HealthCheckResponse = TypedDict("HealthCheckResponse", {"status": Literal["UP"]})

logging.basicConfig(
    format="%(asctime)s [%(name)-25s] %(levelname)-8s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True
)

@contextlib.asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    task = asyncio.create_task(worker_processor(), name="Solver worker")
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await remote_client.close()

app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

@app.get("/")
def root() -> RootResponse:
    return {"message": "Welcome to the Firepulse Planning Engine API"}

@app.get("/health")
def health() -> HealthCheckResponse:
    return {"status": "UP"}

app.include_router(router)
