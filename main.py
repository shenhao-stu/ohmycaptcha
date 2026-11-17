"""Service entrypoint compatible with Render-style deployment."""

import os

import uvicorn

if __name__ == "__main__":
    from src.core.config import config

    port = int(os.environ.get("PORT", config.server_port))
    uvicorn.run(
        "src.main:app",
        host=config.server_host,
        port=port,
        reload=False,
    )
