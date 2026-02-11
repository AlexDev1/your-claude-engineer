"""
Progress Tracking Utilities
===========================

Functions for displaying progress of the autonomous coding agent.
"""


def print_session_header(session_num: int) -> None:
    """Print a formatted header for the session."""
    print("\n" + "=" * 70)
    print(f"  СЕССИЯ {session_num}: ОРКЕСТРАТОР")
    print("=" * 70)
    print()
