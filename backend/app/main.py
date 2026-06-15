from contextlib import asynccontextmanager
from pathlib import Path

from arq.connections import ArqRedis, RedisSettings, create_pool
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import load_config
from app.routers import review, webhook

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_config()
    redis: ArqRedis = await create_pool(RedisSettings.from_dsn(config.redis_url))
    app.state.redis = redis
    yield
    await redis.aclose()


app = FastAPI(title="PRism API", version="0.1.0", lifespan=lifespan)

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
