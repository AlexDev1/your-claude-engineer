"""Built-in analytics dashboard — starts with the agent automatically."""

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI


def start_dashboard(port: int = 8003) -> threading.Thread:
    """Launch the FastAPI + static dashboard in a background daemon thread.

    Args:
        port: TCP port to bind (default 8003).

    Returns:
        The started daemon thread.
    """
    import uvicorn

    from axon_agent.dashboard.api import app

    thread = threading.Thread(
        target=uvicorn.run,
        args=(app,),
        kwargs={"host": "0.0.0.0", "port": port, "log_level": "warning"},
        daemon=True,
    )
    thread.start()
    return thread
