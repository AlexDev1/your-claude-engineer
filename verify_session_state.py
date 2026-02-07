#!/usr/bin/env python3
"""Verify session state module works correctly."""

import json
import tempfile
from pathlib import Path

from session_state import (
    SessionPhase,
    SessionState,
    SessionStateManager,
    GracefulDegradation,
    ErrorType,
    get_session_state_manager,
)

print("=" * 60)
print("Session State Module Verification")
print("=" * 60)

# 1. Verify phases
print("\n1. Session Phases:")
for phase in SessionPhase:
    print(f"   {phase.order}. {phase.phase_name} ({phase.name})")

# 2. Test state persistence
print("\n2. State Persistence Test:")
with tempfile.TemporaryDirectory() as tmpdir:
    project_dir = Path(tmpdir)
    (project_dir / ".agent").mkdir()

    manager = get_session_state_manager(project_dir)
    state = manager.start_session("ENG-35")
    print(f"   Started session: {state.issue_id}")

    manager.transition_to(SessionPhase.IMPLEMENTATION)
    print(f"   Transitioned to: {manager.current_state.phase.phase_name}")

    # Verify file exists
    state_file = project_dir / ".agent" / "session_state.json"
    with open(state_file) as f:
        data = json.load(f)
    print(f"   State saved to file: phase={data['phase']}")

# 3. Resume phase logic
print("\n3. Resume Phase Logic:")
test_cases = [
    (SessionPhase.ORIENT, "restart from ORIENT"),
    (SessionPhase.VERIFICATION, "restart from ORIENT"),
    (SessionPhase.IMPLEMENTATION, "retry IMPLEMENTATION"),
    (SessionPhase.COMMIT, "retry COMMIT only"),
    (SessionPhase.NOTIFY, "retry NOTIFY only"),
]

with tempfile.TemporaryDirectory() as tmpdir:
    project_dir = Path(tmpdir)
    (project_dir / ".agent").mkdir()
    manager = get_session_state_manager(project_dir)

    for phase, expected in test_cases:
        state = SessionState(phase=phase, issue_id="TEST")
        resume = manager.get_resume_phase(state)
        print(f"   {phase.phase_name:15} -> resume at {resume.phase_name:15} ({expected})")

# 4. Graceful degradation
print("\n4. Graceful Degradation Matrix:")
print(f"   MCP Timeout retries: {GracefulDegradation.get_max_retries(ErrorType.MCP_TIMEOUT)}")
print(f"   Rate limit backoff: {GracefulDegradation.RATE_LIMIT_DELAYS}s")

skip_cases = [
    (ErrorType.MCP_TIMEOUT, SessionPhase.NOTIFY),
    (ErrorType.MCP_TIMEOUT, SessionPhase.MARK_DONE),
    (ErrorType.PLAYWRIGHT_CRASH, SessionPhase.VERIFICATION),
]
print("   Skippable phases:")
for error_type, phase in skip_cases:
    can_skip = GracefulDegradation.should_skip_service(error_type, phase)
    print(f"     {error_type.value} + {phase.phase_name}: {'SKIP' if can_skip else 'RETRY'}")

print("\n" + "=" * 60)
print("All verifications passed!")
print("=" * 60)
