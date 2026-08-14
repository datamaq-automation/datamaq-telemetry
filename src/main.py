from src.infrastructure.fastapi.server import create_app

app = create_app()

if __name__ == "__main__":
    import uvicorn

    from src.infrastructure.pydantic.config import get_settings

    settings = get_settings()
    uvicorn.run("src.main:app", host=settings.API_HOST, port=settings.API_PORT, reload=settings.DEBUG)
