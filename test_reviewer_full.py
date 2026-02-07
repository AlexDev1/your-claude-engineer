"""Temporary test to verify full reviewer agent integration."""
from agents import AGENT_DEFINITIONS, REVIEWER_AGENT
from mcp_config import get_reviewer_tools

# Test 1: Agent available in definitions dict
assert "reviewer" in AGENT_DEFINITIONS, "reviewer not in AGENT_DEFINITIONS"
print("PASS: reviewer in AGENT_DEFINITIONS")

# Test 2: Reviewer agent has correct model
assert REVIEWER_AGENT.model == "haiku", f"Expected haiku, got {REVIEWER_AGENT.model}"
print("PASS: reviewer model is haiku")

# Test 3: Reviewer has correct tools
expected_tools = ["Read", "Glob", "Grep", "Bash"]
assert REVIEWER_AGENT.tools == expected_tools, f"Expected {expected_tools}, got {REVIEWER_AGENT.tools}"
print("PASS: reviewer tools are correct")

# Test 4: get_reviewer_tools returns same tools
assert get_reviewer_tools() == expected_tools
print("PASS: get_reviewer_tools() returns correct tools")

# Test 5: Reviewer prompt is loaded (non-empty)
assert len(REVIEWER_AGENT.prompt) > 100, "Prompt too short"
assert "APPROVE" in REVIEWER_AGENT.prompt, "Missing APPROVE in prompt"
assert "REQUEST_CHANGES" in REVIEWER_AGENT.prompt, "Missing REQUEST_CHANGES in prompt"
assert "security" in REVIEWER_AGENT.prompt.lower(), "Missing security in prompt"
print("PASS: reviewer prompt loaded with expected content")

# Test 6: All 4 agents present
assert len(AGENT_DEFINITIONS) == 4, f"Expected 4 agents, got {len(AGENT_DEFINITIONS)}"
agent_names = set(AGENT_DEFINITIONS.keys())
expected_names = {"task", "telegram", "coding", "reviewer"}
assert agent_names == expected_names, f"Expected {expected_names}, got {agent_names}"
print("PASS: all 4 agents present")

# Test 7: Verify prompt file structure
from pathlib import Path
prompt_path = Path(__file__).parent / "prompts" / "reviewer_prompt.md"
assert prompt_path.exists(), "reviewer_prompt.md not found"
content = prompt_path.read_text()
assert "## YOUR ROLE - CODE REVIEWER AGENT" in content
assert "Auto-Approve Rules" in content
assert "Always Review" in content
assert "severity: critical" in content
print("PASS: reviewer_prompt.md has correct structure")

# Test 8: Verify execute_task.md has review gate
exec_prompt = (Path(__file__).parent / "prompts" / "execute_task.md").read_text()
assert "Step 4b: Code Review Gate" in exec_prompt, "Missing review gate in execute_task.md"
assert "reviewer" in exec_prompt, "Missing reviewer reference in execute_task.md"
print("PASS: execute_task.md has review gate")

# Test 9: Verify continuation_task.md has review gate
cont_prompt = (Path(__file__).parent / "prompts" / "continuation_task.md").read_text()
assert "Step 4b: Code Review Gate" in cont_prompt, "Missing review gate in continuation_task.md"
assert "reviewer" in cont_prompt, "Missing reviewer reference in continuation_task.md"
print("PASS: continuation_task.md has review gate")

# Test 10: Verify orchestrator_prompt.md has reviewer
orch_prompt = (Path(__file__).parent / "prompts" / "orchestrator_prompt.md").read_text()
assert "reviewer" in orch_prompt, "Missing reviewer in orchestrator_prompt.md"
assert "Code Review Gate" in orch_prompt, "Missing review gate in orchestrator_prompt.md"
print("PASS: orchestrator_prompt.md has reviewer and review gate")

print()
print("=" * 50)
print("ALL 10 TESTS PASSED")
print("=" * 50)
