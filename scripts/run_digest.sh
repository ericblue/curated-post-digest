#!/bin/bash
#
# run_digest.sh - Fetch and preprocess Reddit data for AI Digest
#
# This script fetches and preprocesses Reddit posts. The summarization
# is handled by Claude Code directly.
#
# Usage:
#   ./scripts/run_digest.sh                                    # Default: last 7 days
#   ./scripts/run_digest.sh 2025-01-01T00:00:00Z 2025-01-08T00:00:00Z  # Custom range
#

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Change to project directory
cd "$PROJECT_DIR"

# Parse arguments
START="${1:-}"
END="${2:-}"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  AI Reddit Digest - Data Collection${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Build time window args
TIME_ARGS=""
if [ -n "$START" ]; then
    TIME_ARGS="$TIME_ARGS --start $START"
    echo -e "${GREEN}Start:${NC} $START"
fi
if [ -n "$END" ]; then
    TIME_ARGS="$TIME_ARGS --end $END"
    echo -e "${GREEN}End:${NC} $END"
fi
if [ -z "$TIME_ARGS" ]; then
    echo -e "${YELLOW}Using default time window (last 7 days)${NC}"
fi
echo ""

# Step 1: Fetch Reddit posts
echo -e "${BLUE}[1/2] Fetching Reddit posts...${NC}"
python3 scripts/fetch_reddit.py $TIME_ARGS
echo -e "${GREEN}Done!${NC}"
echo ""

# Step 2: Preprocess posts
echo -e "${BLUE}[2/2] Preprocessing posts...${NC}"
python3 scripts/preprocess.py
echo -e "${GREEN}Done!${NC}"
echo ""

# Show results
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Data collection complete!${NC}"
echo ""
echo -e "Processed data: ${YELLOW}output/processed_posts.json${NC}"
echo ""
