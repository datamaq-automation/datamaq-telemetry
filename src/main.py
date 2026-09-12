"""src/main.py."""

from src.infrastructure.fastapi.server import create_app
from src.infrastructure.settings.config import get_settings
from src.infrastructure.settings.logger import setup_logging

setup_logging()
app = create_app(get_settings())

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run("src.main:app", host=settings.API_HOST, port=settings.API_PORT, reload=settings.DEBUG or False)
