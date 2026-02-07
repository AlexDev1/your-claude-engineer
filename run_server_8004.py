"""Temporary script to run analytics server on port 8004 for testing."""
import uvicorn
from analytics_server.server import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8004)
