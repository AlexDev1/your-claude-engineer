#!/usr/bin/env python3
"""
Test script to demonstrate and verify the session state machine (ENG-66).

Creates a web-based demo that shows:
- Current session phase
- State file contents
- Phase transitions
- Error recording
- Recovery simulation
"""

import asyncio
import json
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlparse

from session_state import (
    ErrorType,
    SessionPhase,
    SessionState,
    SessionStateManager,
    get_session_state_manager,
)

# Global state manager
PROJECT_DIR = Path(__file__).parent
state_manager: SessionStateManager | None = None


class StateHandler(SimpleHTTPRequestHandler):
    """HTTP handler for session state demo."""

    def do_GET(self) -> None:
        """Handle GET requests."""
        if self.path == "/" or self.path == "/index.html":
            self.send_demo_page()
        elif self.path == "/api/state":
            self.send_state_json()
        else:
            self.send_error(404, "Not Found")

    def do_POST(self) -> None:
        """Handle POST requests for state transitions."""
        global state_manager

        if self.path.startswith("/api/"):
            # Parse request body
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")

            if self.path == "/api/start":
                # Start new session
                params = parse_qs(body)
                issue_id = params.get("issue_id", ["ENG-66"])[0]
                state_manager = get_session_state_manager(PROJECT_DIR)
                state_manager.start_session(issue_id)
                self.send_json_response({"status": "ok", "message": f"Started session for {issue_id}"})

            elif self.path == "/api/transition":
                # Transition to new phase
                if state_manager is None or state_manager.current_state is None:
                    self.send_json_response({"status": "error", "message": "No active session"}, 400)
                    return

                params = parse_qs(body)
                phase_name = params.get("phase", [""])[0]
                try:
                    phase = SessionPhase.from_string(phase_name)
                    state_manager.transition_to(phase)
                    self.send_json_response({"status": "ok", "message": f"Transitioned to {phase.phase_name}"})
                except ValueError as e:
                    self.send_json_response({"status": "error", "message": str(e)}, 400)

            elif self.path == "/api/error":
                # Record error
                if state_manager is None or state_manager.current_state is None:
                    self.send_json_response({"status": "error", "message": "No active session"}, 400)
                    return

                params = parse_qs(body)
                error_msg = params.get("message", ["Test error"])[0]
                error_type_str = params.get("type", ["unknown"])[0]

                try:
                    error_type = ErrorType[error_type_str.upper()]
                except KeyError:
                    error_type = ErrorType.UNKNOWN

                error = Exception(error_msg)
                state_manager.record_error(error, error_type)
                self.send_json_response({"status": "ok", "message": "Error recorded"})

            elif self.path == "/api/clear":
                # Clear session
                if state_manager:
                    state_manager.clear_state()
                self.send_json_response({"status": "ok", "message": "Session cleared"})

            else:
                self.send_error(404, "Not Found")
        else:
            self.send_error(404, "Not Found")

    def send_json_response(self, data: dict, status: int = 200) -> None:
        """Send JSON response."""
        json_data = json.dumps(data)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(json_data)))
        self.end_headers()
        self.wfile.write(json_data.encode("utf-8"))

    def send_state_json(self) -> None:
        """Send current state as JSON."""
        global state_manager

        if state_manager and state_manager.current_state:
            state_dict = state_manager.current_state.to_dict()
        else:
            state_dict = None

        # Load from file if exists
        state_file = PROJECT_DIR / ".agent" / "session_state.json"
        if state_file.exists():
            with open(state_file, "r") as f:
                file_content = json.load(f)
        else:
            file_content = None

        response = {
            "memory_state": state_dict,
            "file_state": file_content,
            "file_exists": state_file.exists(),
            "file_path": str(state_file),
        }

        self.send_json_response(response)

    def send_demo_page(self) -> None:
        """Send HTML demo page."""
        html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Session State Machine Demo (ENG-66)</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        h1 {
            color: white;
            text-align: center;
            margin-bottom: 30px;
            font-size: 2.5em;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
        }
        .grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 20px;
        }
        .card {
            background: white;
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }
        h2 {
            color: #667eea;
            margin-bottom: 16px;
            font-size: 1.5em;
        }
        .button-group {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-bottom: 16px;
        }
        button {
            background: #667eea;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 600;
            transition: all 0.3s ease;
            box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
        }
        button:hover {
            background: #5568d3;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        }
        button:active {
            transform: translateY(0);
        }
        .btn-danger {
            background: #e74c3c;
        }
        .btn-danger:hover {
            background: #c0392b;
        }
        .btn-warning {
            background: #f39c12;
        }
        .btn-warning:hover {
            background: #d68910;
        }
        pre {
            background: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 6px;
            padding: 16px;
            overflow-x: auto;
            font-size: 13px;
            line-height: 1.5;
            max-height: 400px;
            overflow-y: auto;
        }
        .status {
            display: inline-block;
            padding: 6px 12px;
            border-radius: 4px;
            font-weight: 600;
            font-size: 12px;
            margin-bottom: 12px;
        }
        .status.active {
            background: #d4edda;
            color: #155724;
        }
        .status.inactive {
            background: #f8d7da;
            color: #721c24;
        }
        .phase-indicator {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 16px;
        }
        .phase-badge {
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 600;
            background: #e9ecef;
            color: #495057;
        }
        .phase-badge.current {
            background: #667eea;
            color: white;
            animation: pulse 2s infinite;
        }
        .phase-badge.completed {
            background: #28a745;
            color: white;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.7; }
        }
        .info-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #e9ecef;
        }
        .info-label {
            font-weight: 600;
            color: #6c757d;
        }
        .info-value {
            color: #212529;
        }
        .full-width {
            grid-column: 1 / -1;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔄 Session State Machine Demo</h1>
        <p style="text-align: center; color: white; margin-bottom: 20px; font-size: 1.1em;">
            ENG-66: Session state machine and phase tracking
        </p>

        <div class="grid">
            <div class="card">
                <h2>Session Control</h2>
                <div class="button-group">
                    <button onclick="startSession()">▶️ Start Session</button>
                    <button onclick="clearSession()" class="btn-danger">🗑️ Clear Session</button>
                    <button onclick="refreshState()">🔄 Refresh</button>
                </div>

                <h3 style="margin-top: 20px; margin-bottom: 12px; color: #495057;">Phase Transitions</h3>
                <div class="button-group">
                    <button onclick="transitionTo('orient')">1. Orient</button>
                    <button onclick="transitionTo('status')">2. Status</button>
                    <button onclick="transitionTo('verify')">3. Verify</button>
                    <button onclick="transitionTo('implement')">4. Implement</button>
                    <button onclick="transitionTo('commit')">5. Commit</button>
                    <button onclick="transitionTo('mark_done')">6. Mark Done</button>
                    <button onclick="transitionTo('notify')">7. Notify</button>
                    <button onclick="transitionTo('flush')">8. Flush</button>
                </div>

                <h3 style="margin-top: 20px; margin-bottom: 12px; color: #495057;">Error Simulation</h3>
                <div class="button-group">
                    <button onclick="recordError('mcp_timeout')" class="btn-warning">MCP Timeout</button>
                    <button onclick="recordError('playwright_crash')" class="btn-warning">Playwright Crash</button>
                    <button onclick="recordError('git_error')" class="btn-warning">Git Error</button>
                    <button onclick="recordError('rate_limit')" class="btn-warning">Rate Limit</button>
                </div>
            </div>

            <div class="card">
                <h2>Current State</h2>
                <div id="statusIndicator" class="status inactive">No Active Session</div>
                <div id="phaseIndicator" class="phase-indicator"></div>
                <div id="stateInfo"></div>
            </div>

            <div class="card full-width">
                <h2>Session State File (.agent/session_state.json)</h2>
                <pre id="fileContent">No session state file</pre>
            </div>

            <div class="card full-width">
                <h2>In-Memory State</h2>
                <pre id="memoryContent">No in-memory state</pre>
            </div>
        </div>
    </div>

    <script>
        async function api(endpoint, method = 'GET', body = null) {
            const options = { method };
            if (body) {
                options.headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
                options.body = new URLSearchParams(body).toString();
            }
            const response = await fetch(endpoint, options);
            const data = await response.json();
            if (data.status === 'error') {
                alert('Error: ' + data.message);
            }
            await refreshState();
            return data;
        }

        async function startSession() {
            await api('/api/start', 'POST', { issue_id: 'ENG-66' });
        }

        async function clearSession() {
            await api('/api/clear', 'POST');
        }

        async function transitionTo(phase) {
            await api('/api/transition', 'POST', { phase });
        }

        async function recordError(type) {
            const message = `Simulated ${type.replace('_', ' ')} error`;
            await api('/api/error', 'POST', { type, message });
        }

        async function refreshState() {
            const response = await fetch('/api/state');
            const data = await response.json();

            // Update status indicator
            const statusEl = document.getElementById('statusIndicator');
            if (data.memory_state || data.file_state) {
                statusEl.className = 'status active';
                statusEl.textContent = '✓ Active Session';
            } else {
                statusEl.className = 'status inactive';
                statusEl.textContent = '○ No Active Session';
            }

            // Update phase indicator
            const state = data.memory_state || data.file_state;
            const phaseEl = document.getElementById('phaseIndicator');
            if (state) {
                const phases = ['orient', 'status', 'verify', 'implement', 'commit', 'mark_done', 'notify', 'flush'];
                const completed = state.completed_phases || [];
                const current = state.phase;

                phaseEl.innerHTML = phases.map(p => {
                    let className = 'phase-badge';
                    if (p === current) className += ' current';
                    else if (completed.includes(p)) className += ' completed';
                    return `<span class="${className}">${p}</span>`;
                }).join('');
            } else {
                phaseEl.innerHTML = '';
            }

            // Update state info
            const infoEl = document.getElementById('stateInfo');
            if (state) {
                infoEl.innerHTML = `
                    <div class="info-row">
                        <span class="info-label">Issue ID:</span>
                        <span class="info-value">${state.issue_id}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Current Phase:</span>
                        <span class="info-value">${state.phase}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Attempt:</span>
                        <span class="info-value">${state.attempt}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Started:</span>
                        <span class="info-value">${new Date(state.started_at).toLocaleString()}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Last Updated:</span>
                        <span class="info-value">${new Date(state.last_updated).toLocaleString()}</span>
                    </div>
                `;
            } else {
                infoEl.innerHTML = '<p style="color: #6c757d;">Start a session to see state information</p>';
            }

            // Update file content
            const fileEl = document.getElementById('fileContent');
            if (data.file_state) {
                fileEl.textContent = JSON.stringify(data.file_state, null, 2);
            } else {
                fileEl.textContent = `File does not exist: ${data.file_path}`;
            }

            // Update memory content
            const memoryEl = document.getElementById('memoryContent');
            if (data.memory_state) {
                memoryEl.textContent = JSON.stringify(data.memory_state, null, 2);
            } else {
                memoryEl.textContent = 'No in-memory state (not loaded or session cleared)';
            }
        }

        // Auto-refresh every 2 seconds
        setInterval(refreshState, 2000);

        // Initial load
        refreshState();
    </script>
</body>
</html>"""

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format: str, *args) -> None:
        """Suppress request logging."""
        pass


def run_server(port: int = 8007) -> None:
    """Run the demo server."""
    server = HTTPServer(("127.0.0.1", port), StateHandler)
    print(f"Server running at http://127.0.0.1:{port}/")
    print("Press Ctrl+C to stop")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
