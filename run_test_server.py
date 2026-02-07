"""Run the analytics server on port 8006 for testing ENG-54."""
import uvicorn
from analytics_server.server import app

if __name__ == "__main__":
    print("Starting analytics server on port 8006...")
    uvicorn.run(app, host="0.0.0.0", port=8006)
