#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

print_action() {
    echo -e "${PURPLE}🔄${NC} $1"
}

# Check branch naming convention
check_branch_name() {
    local branch=$(git rev-parse --abbrev-ref HEAD)
    local branch_regex="^[a-zA-Z0-9_-]+\/[a-zA-Z0-9_-]+$|^(main|dev|develop)$"
    
    print_action "Checking branch name: $branch"
    
    if [[ $branch =~ $branch_regex ]]; then
        print_success "Branch name follows convention"
        return 0
    else
        print_warning "Branch name '$branch' doesn't follow convention ((discord-username)/feature-description)"
        print_info "Expected format: (discord-username)/feature-description or (discord-username)/bugfix-description"
        return 0  # Warning only, don't block
    fi
}

# Run type check, lint, format, knip
run_quality_checks() {
    print_action "Running quality checks..."
    
    print_info "Running Ruff Lint..."
    # Get currently staged files
    local staged_files=$(git diff --name-only --cached --diff-filter=ACMR)
    
    if ! uv tool run ruff check . --fix; then
        print_error "Ruff check failed"
        return 1
    fi
    print_success "Ruff check passed"
    
    # Check if any staged files have unstaged changes after Ruff Lint
    if [ -n "$staged_files" ]; then
        local ruff_changed_files=""
        while IFS= read -r file; do
            if [ -n "$(git diff "$file")" ]; then
                ruff_changed_files="$ruff_changed_files $file"
            fi
        done <<< "$staged_files"

        if [ -n "$ruff_changed_files" ] && [ "$ruff_changed_files" != " " ]; then
            print_info "Auto-staging Ruff Lint fixes for:$ruff_changed_files"
            echo "$ruff_changed_files" | xargs git add
        fi
    fi    
    return 0
}

# Install dependencies from pyproject.toml
maybe_install_packages() {
    if uv sync; then
        print_success "Dependencies installed successfully"
    else
        print_error "Failed to install dependencies"
        return 1
    fi
    return 0
}

# Validate commit message
validate_commit_message() {
    local commit_msg="$1"
    local commit_regex='^(feat|fix|docs|style|refactor|test|chore|perf|ci|build|revert): .{1,50}'
    
    print_action "Validating commit message..."
    
    # Check minimum length
    if [ ${#commit_msg} -lt 10 ]; then
        print_error "Commit message must be at least 10 characters long"
        return 1
    fi
    
    # Check format (warning only)
    if [[ ! $commit_msg =~ $commit_regex ]]; then
        print_warning "Commit message doesn't follow conventional format"
        print_info "Expected: 'type: description' where type is one of:"
        print_info "feat, fix, docs, style, refactor, test, chore, perf, ci, build, revert"
        print_info "Example: 'feat: add user authentication'"
    else
        print_success "Commit message follows conventional format"
    fi
    
    return 0
}
