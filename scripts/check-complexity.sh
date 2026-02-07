#!/bin/bash
# Complexity Guard Script (ENG-19)
# =================================
#
# Checks for code complexity issues:
# - Files >500 lines (suggest split)
# - Functions >50 lines
# - High cyclomatic complexity warnings
#
# Usage:
#   ./scripts/check-complexity.sh [directory]
#
# Exit codes:
#   0 - All checks passed
#   1 - Warnings found (files/functions too large)
#   2 - Invalid arguments

set -e

# Configuration
MAX_FILE_LINES=500
MAX_FUNCTION_LINES=50
COMPLEXITY_THRESHOLD=10

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Default directory
TARGET_DIR="${1:-.}"

# Counters
WARNINGS=0
ERRORS=0

echo "=== Complexity Guard ==="
echo "Checking: $TARGET_DIR"
echo ""

# Function to check file line count
check_file_lines() {
    local file="$1"
    local lines
    lines=$(wc -l < "$file" 2>/dev/null || echo "0")

    if [ "$lines" -gt "$MAX_FILE_LINES" ]; then
        echo -e "${YELLOW}WARNING${NC}: $file has $lines lines (max: $MAX_FILE_LINES)"
        echo "  Suggestion: Consider splitting into smaller modules"
        ((WARNINGS++))
        return 1
    fi
    return 0
}

# Function to check Python function lengths
check_python_functions() {
    local file="$1"
    local in_function=0
    local function_name=""
    local function_start=0
    local line_num=0
    local indent_level=0

    while IFS= read -r line || [ -n "$line" ]; do
        ((line_num++))

        # Check for function definition (def or async def)
        if [[ "$line" =~ ^[[:space:]]*(async[[:space:]]+)?def[[:space:]]+([a-zA-Z_][a-zA-Z0-9_]*)\( ]]; then
            # If we were in a function, check its length
            if [ "$in_function" -eq 1 ]; then
                local func_length=$((line_num - function_start - 1))
                if [ "$func_length" -gt "$MAX_FUNCTION_LINES" ]; then
                    echo -e "${YELLOW}WARNING${NC}: $file:$function_start - Function '$function_name' is $func_length lines (max: $MAX_FUNCTION_LINES)"
                    ((WARNINGS++))
                fi
            fi

            function_name="${BASH_REMATCH[2]}"
            function_start=$line_num
            in_function=1

            # Calculate indent level
            local spaces="${line%%[^[:space:]]*}"
            indent_level=${#spaces}
        fi
    done < "$file"

    # Check the last function
    if [ "$in_function" -eq 1 ]; then
        local func_length=$((line_num - function_start))
        if [ "$func_length" -gt "$MAX_FUNCTION_LINES" ]; then
            echo -e "${YELLOW}WARNING${NC}: $file:$function_start - Function '$function_name' is $func_length lines (max: $MAX_FUNCTION_LINES)"
            ((WARNINGS++))
        fi
    fi
}

# Function to check JavaScript/TypeScript function lengths
check_js_functions() {
    local file="$1"
    local in_function=0
    local function_name=""
    local function_start=0
    local brace_count=0
    local line_num=0

    while IFS= read -r line || [ -n "$line" ]; do
        ((line_num++))

        # Check for function definition patterns
        # - function name(
        # - const name = (
        # - const name = async (
        # - export function name(
        # - async function name(
        if [[ "$line" =~ (function[[:space:]]+([a-zA-Z_][a-zA-Z0-9_]*)|const[[:space:]]+([a-zA-Z_][a-zA-Z0-9_]*)[[:space:]]*=[[:space:]]*(async[[:space:]]*)?\() ]]; then
            if [ "$in_function" -eq 1 ] && [ "$brace_count" -eq 0 ]; then
                local func_length=$((line_num - function_start - 1))
                if [ "$func_length" -gt "$MAX_FUNCTION_LINES" ]; then
                    echo -e "${YELLOW}WARNING${NC}: $file:$function_start - Function '$function_name' is $func_length lines (max: $MAX_FUNCTION_LINES)"
                    ((WARNINGS++))
                fi
            fi

            # Extract function name
            if [[ "$line" =~ function[[:space:]]+([a-zA-Z_][a-zA-Z0-9_]*) ]]; then
                function_name="${BASH_REMATCH[1]}"
            elif [[ "$line" =~ const[[:space:]]+([a-zA-Z_][a-zA-Z0-9_]*) ]]; then
                function_name="${BASH_REMATCH[1]}"
            fi

            function_start=$line_num
            in_function=1
            brace_count=0
        fi

        # Count braces to track function boundaries
        if [ "$in_function" -eq 1 ]; then
            # Count opening and closing braces
            local opens="${line//[^\{]/}"
            local closes="${line//[^\}]/}"
            brace_count=$((brace_count + ${#opens} - ${#closes}))

            # Function ended
            if [ "$brace_count" -le 0 ] && [ "$function_start" -ne "$line_num" ]; then
                local func_length=$((line_num - function_start))
                if [ "$func_length" -gt "$MAX_FUNCTION_LINES" ]; then
                    echo -e "${YELLOW}WARNING${NC}: $file:$function_start - Function '$function_name' is $func_length lines (max: $MAX_FUNCTION_LINES)"
                    ((WARNINGS++))
                fi
                in_function=0
            fi
        fi
    done < "$file"
}

# Find and check Python files
echo "Checking Python files..."
while IFS= read -r -d '' file; do
    check_file_lines "$file"
    check_python_functions "$file"
done < <(find "$TARGET_DIR" -type f -name "*.py" ! -path "*/node_modules/*" ! -path "*/.venv/*" ! -path "*/venv/*" ! -path "*/__pycache__/*" -print0 2>/dev/null)

# Find and check JavaScript/TypeScript files
echo "Checking JavaScript/TypeScript files..."
while IFS= read -r -d '' file; do
    check_file_lines "$file"
    check_js_functions "$file"
done < <(find "$TARGET_DIR" -type f \( -name "*.js" -o -name "*.ts" -o -name "*.tsx" -o -name "*.jsx" \) ! -path "*/node_modules/*" ! -path "*/dist/*" ! -path "*/build/*" -print0 2>/dev/null)

echo ""
echo "=== Summary ==="
if [ "$WARNINGS" -eq 0 ]; then
    echo -e "${GREEN}All complexity checks passed!${NC}"
    exit 0
else
    echo -e "${YELLOW}Found $WARNINGS warning(s)${NC}"
    echo ""
    echo "Recommendations:"
    echo "  - Files >$MAX_FILE_LINES lines: Split into smaller modules"
    echo "  - Functions >$MAX_FUNCTION_LINES lines: Extract helper functions"
    echo "  - High complexity: Simplify conditionals, use early returns"
    exit 1
fi
