from fastapi import FastAPI
from app.routes.video_routes import router as video_router
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.include_router(video_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)