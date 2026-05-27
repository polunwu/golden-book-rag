from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from api.routers import books
from db.connection import get_pool


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    pool = get_pool()
    pool.open()
    pool.wait()
    try:
        yield
    finally:
        pool.close()


app = FastAPI(title="golden-book-rag", lifespan=lifespan)
app.include_router(books.router)
