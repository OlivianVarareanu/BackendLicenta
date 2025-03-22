from fastapi import FastAPI
from app.routes.video_routes import router as video_router

app = FastAPI()

app.include_router(video_router)