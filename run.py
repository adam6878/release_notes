import uvicorn

from app import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        timeout_graceful_shutdown=settings.graceful_shutdown_seconds,
        reload=settings.reload,
        access_log=False,  # the request middleware already logs each request as JSON
    )
