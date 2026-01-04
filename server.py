import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from dotenv import load_dotenv
from loguru import logger
from starlette.middleware.cors import CORSMiddleware

load_dotenv()


def print_logo():
    from pyfiglet import Figlet
    f = Figlet(font="slant")
    print(f.renderText("Genie Backend"))


def log_setting():
    log_path = os.getenv("LOG_PATH", Path(__file__).resolve().parent / "logs" / "server.log")
    log_format = "{time:YYYY-MM-DD HH:mm:ss.SSS} {level} {module}.{function} {message}"
    logger.add(log_path, format=log_format, rotation="200 MB")


def create_app():
    _app = FastAPI(
        on_startup=[log_setting, print_logo]
    )
    register_middleware(_app)
    register_router(_app)
    return _app


def register_middleware(app: FastAPI):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True
    )


def register_router(app: FastAPI):
    from api.genie import router
    from api.data_agent import data_router
    app.include_router(router)
    app.include_router(data_router)


app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        app="server:app",
        host="0.0.0.0",
        port=8080,
        workers=1
    )

