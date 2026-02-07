"""Temporary test to verify reviewer agent imports correctly."""
from agents.definitions import AGENT_DEFINITIONS, REVIEWER_AGENT

print("Agents:", list(AGENT_DEFINITIONS.keys()))
print("Reviewer model:", REVIEWER_AGENT.model)
print("Reviewer tools:", REVIEWER_AGENT.tools)
print("Reviewer description:", REVIEWER_AGENT.description[:80])
print()
print("All agent definitions loaded successfully.")
