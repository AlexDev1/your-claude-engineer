"""Encode HTML file to data URI for browser viewing."""
import base64
import sys
from pathlib import Path

html_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("ENG-66-verification.html")
content = html_path.read_bytes()
encoded = base64.b64encode(content).decode()
print(f"data:text/html;base64,{encoded}")
