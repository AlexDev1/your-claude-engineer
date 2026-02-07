#!/bin/bash
# Post-Commit Linting Gate (ENG-19)
# ==================================
#
# Runs code quality checks after commit:
# - TypeScript type check (tsc --noEmit)
# - ESLint for JavaScript/TypeScript
# - Python syntax check (py_compile)
# - Ruff for Python linting
# - Complexity guard
#
# Usage:
#   ./scripts/lint-gate.sh [--fix]
#
# Options:
#   --fix    Attempt to auto-fix issues (eslint --fix, ruff --fix)
#
# Exit codes:
#   0 - All checks passed
#   1 - Linting errors found
#   2 - Type errors found

set -e

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
FIX_MODE=0
if [ "$1" = "--fix" ]; then
    FIX_MODE=1
    echo -e "${BLUE}Running in auto-fix mode${NC}"
fi

# Track overall status
ERRORS=0
WARNINGS=0

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== Linting Gate ==="
echo "Project: $PROJECT_ROOT"
echo ""

# Function to run a check
run_check() {
    local name="$1"
    local cmd="$2"
    local fix_cmd="$3"

    echo -e "${BLUE}[$name]${NC}"

    if [ "$FIX_MODE" -eq 1 ] && [ -n "$fix_cmd" ]; then
        echo "  Running auto-fix: $fix_cmd"
        if eval "$fix_cmd" 2>&1; then
            echo -e "  ${GREEN}Auto-fix completed${NC}"
        fi
    fi

    if eval "$cmd" 2>&1; then
        echo -e "  ${GREEN}PASS${NC}"
        return 0
    else
        echo -e "  ${RED}FAIL${NC}"
        return 1
    fi
}

# Check if we have TypeScript files and tsc is available
check_typescript() {
    local ts_files
    ts_files=$(find "$PROJECT_ROOT" -type f \( -name "*.ts" -o -name "*.tsx" \) ! -path "*/node_modules/*" ! -path "*/dist/*" 2>/dev/null | head -1)

    if [ -n "$ts_files" ]; then
        # Check for tsconfig.json
        if [ -f "$PROJECT_ROOT/tsconfig.json" ] || [ -f "$PROJECT_ROOT/dashboard/tsconfig.json" ]; then
            echo -e "${BLUE}[TypeScript Type Check]${NC}"

            # Try to run tsc
            if command -v npx &> /dev/null; then
                local tsc_dir="$PROJECT_ROOT"
                if [ -f "$PROJECT_ROOT/dashboard/tsconfig.json" ]; then
                    tsc_dir="$PROJECT_ROOT/dashboard"
                fi

                if (cd "$tsc_dir" && npx tsc --noEmit 2>&1); then
                    echo -e "  ${GREEN}PASS${NC}"
                else
                    echo -e "  ${RED}FAIL${NC} - Type errors found"
                    ((ERRORS++))
                fi
            else
                echo -e "  ${YELLOW}SKIP${NC} - npx not available"
            fi
        fi
    fi
}

# Check JavaScript/TypeScript with ESLint
check_eslint() {
    local js_files
    js_files=$(find "$PROJECT_ROOT" -type f \( -name "*.js" -o -name "*.ts" -o -name "*.tsx" -o -name "*.jsx" \) ! -path "*/node_modules/*" ! -path "*/dist/*" 2>/dev/null | head -1)

    if [ -n "$js_files" ]; then
        echo -e "${BLUE}[ESLint]${NC}"

        # Check for eslint config
        local eslint_config=""
        if [ -f "$PROJECT_ROOT/.eslintrc.js" ] || [ -f "$PROJECT_ROOT/.eslintrc.json" ] || [ -f "$PROJECT_ROOT/eslint.config.js" ]; then
            eslint_config="$PROJECT_ROOT"
        elif [ -f "$PROJECT_ROOT/dashboard/.eslintrc.js" ] || [ -f "$PROJECT_ROOT/dashboard/eslint.config.js" ]; then
            eslint_config="$PROJECT_ROOT/dashboard"
        fi

        if [ -n "$eslint_config" ]; then
            if command -v npx &> /dev/null; then
                local fix_flag=""
                if [ "$FIX_MODE" -eq 1 ]; then
                    fix_flag="--fix"
                fi

                if (cd "$eslint_config" && npx eslint src/ --max-warnings 0 $fix_flag 2>&1); then
                    echo -e "  ${GREEN}PASS${NC}"
                else
                    echo -e "  ${RED}FAIL${NC} - ESLint errors found"
                    ((ERRORS++))
                fi
            else
                echo -e "  ${YELLOW}SKIP${NC} - npx not available"
            fi
        else
            echo -e "  ${YELLOW}SKIP${NC} - No ESLint config found"
        fi
    fi
}

# Check Python files for syntax errors
check_python_syntax() {
    local py_files
    py_files=$(find "$PROJECT_ROOT" -type f -name "*.py" ! -path "*/node_modules/*" ! -path "*/.venv/*" ! -path "*/venv/*" ! -path "*/__pycache__/*" 2>/dev/null)

    if [ -n "$py_files" ]; then
        echo -e "${BLUE}[Python Syntax Check]${NC}"

        local syntax_errors=0
        while IFS= read -r file; do
            if ! python3 -m py_compile "$file" 2>&1; then
                echo -e "  ${RED}Syntax error in: $file${NC}"
                ((syntax_errors++))
            fi
        done <<< "$py_files"

        if [ "$syntax_errors" -eq 0 ]; then
            echo -e "  ${GREEN}PASS${NC}"
        else
            echo -e "  ${RED}FAIL${NC} - $syntax_errors file(s) with syntax errors"
            ((ERRORS++))
        fi
    fi
}

# Check Python files with Ruff
check_ruff() {
    local py_files
    py_files=$(find "$PROJECT_ROOT" -type f -name "*.py" ! -path "*/node_modules/*" ! -path "*/.venv/*" ! -path "*/venv/*" ! -path "*/__pycache__/*" 2>/dev/null | head -1)

    if [ -n "$py_files" ]; then
        echo -e "${BLUE}[Ruff Python Linter]${NC}"

        if command -v ruff &> /dev/null; then
            local fix_flag=""
            if [ "$FIX_MODE" -eq 1 ]; then
                fix_flag="--fix"
            fi

            if ruff check "$PROJECT_ROOT" --exclude node_modules --exclude .venv --exclude venv --exclude __pycache__ $fix_flag 2>&1; then
                echo -e "  ${GREEN}PASS${NC}"
            else
                echo -e "  ${YELLOW}WARN${NC} - Ruff found issues"
                ((WARNINGS++))
            fi
        else
            echo -e "  ${YELLOW}SKIP${NC} - ruff not installed"
        fi
    fi
}

# Run complexity check
check_complexity() {
    echo -e "${BLUE}[Complexity Guard]${NC}"

    if [ -x "$SCRIPT_DIR/check-complexity.sh" ]; then
        if "$SCRIPT_DIR/check-complexity.sh" "$PROJECT_ROOT" 2>&1; then
            echo -e "  ${GREEN}PASS${NC}"
        else
            echo -e "  ${YELLOW}WARN${NC} - Complexity warnings found"
            ((WARNINGS++))
        fi
    else
        echo -e "  ${YELLOW}SKIP${NC} - check-complexity.sh not executable"
    fi
}

# Run all checks
echo ""
check_typescript
echo ""
check_eslint
echo ""
check_python_syntax
echo ""
check_ruff
echo ""
check_complexity

# Summary
echo ""
echo "=== Summary ==="
if [ "$ERRORS" -eq 0 ] && [ "$WARNINGS" -eq 0 ]; then
    echo -e "${GREEN}All checks passed!${NC}"
    exit 0
elif [ "$ERRORS" -eq 0 ]; then
    echo -e "${YELLOW}Passed with $WARNINGS warning(s)${NC}"
    exit 0
else
    echo -e "${RED}Failed with $ERRORS error(s) and $WARNINGS warning(s)${NC}"
    echo ""
    echo "Fix the errors before marking the task as Done."
    echo "Run with --fix to attempt auto-fixes: ./scripts/lint-gate.sh --fix"
    exit 1
fi
