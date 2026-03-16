from fastapi import FastAPI
from app.core.logging import configure_logging
from app.routes.health import router as health_router
from app.routes.datasets import router as datasets_router
from app.routes.chat import router as chat_router

configure_logging()

app = FastAPI(title="WCOA Backend", version="1.0.0")

app.include_router(health_router)
app.include_router(datasets_router)
app.include_router(chat_router)