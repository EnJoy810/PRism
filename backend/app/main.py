import logging
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from asgi_correlation_id import CorrelationIdMiddleware
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import load_config
from app.routers import review, webhook

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ── Structured logging setup ──────────────────────────────────────────────────
# Shared processors used by both structlog-native calls and stdlib logging.
_shared_processors: list = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso"),
]

structlog.configure(
    processors=[
        *_shared_processors,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

# Route stdlib logging through the same JSON pipeline so every logger.info()
# call in agents/services also outputs structured JSON.
_handler = logging.StreamHandler()
_handler.setFormatter(
    structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            *_shared_processors,
            structlog.processors.JSONRenderer(),
        ],
    )
)
_root = logging.getLogger()
_root.handlers.clear()
_root.addHandler(_handler)
_root.setLevel(logging.INFO)
# ─────────────────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_config()
    from arq.connections import ArqRedis, RedisSettings, create_pool
    redis: ArqRedis = await create_pool(RedisSettings.from_dsn(config.redis_url))
    app.state.redis = redis
    yield
    await redis.aclose()


app = FastAPI(title="PRism API", version="0.1.0", lifespan=lifespan)

# Attach a unique X-Review-Id header to every request (auto-generated if absent).
# All structlog calls within the request inherit this ID via contextvars.
app.add_middleware(CorrelationIdMiddleware, header_name="X-Review-Id")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(review.router, prefix="/api")
app.include_router(webhook.router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}
