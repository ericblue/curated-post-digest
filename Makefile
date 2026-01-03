# AI Reddit Digest - Makefile
# ============================
#
# Usage:
#   make install          - Install Python dependencies
#   make fetch            - Fetch and preprocess Reddit posts
#   make clean            - Remove output files
#   make help             - Show this help
#
# Time window options (ISO-8601 format):
#   make fetch START=2025-01-01T00:00:00Z END=2025-01-08T00:00:00Z
#
# Shortcuts:
#   make daily            - Fetch last 24 hours
#   make weekly           - Fetch last 7 days
#   make monthly          - Fetch last 30 days
#
# Single subreddit mode:
#   make single SUBREDDIT=ClaudeAI TOP=10
#   make single SUBREDDIT=ClaudeAI TOP=15 FETCH=50
#
# Parameters:
#   TOP=N        - Number of posts in final report (default: 10)
#   FETCH=N      - Number of source posts to analyze (default: 50)
#   MAX_POSTS=N  - Maximum posts to fetch per subreddit (default: from config)
#   CONFIG=P     - Path to config file (default: config.yaml)
#
# Report generation:
#   make report               - Re-generate report from existing data
#   make report-interactive   - Re-generate report with full Claude UI
#

.PHONY: all install fetch clean help daily weekly monthly single report report-interactive

# Default target
all: help

# Virtual environment directory
VENV_DIR ?= venv

# Config file location
CONFIG ?= config.yaml

# Python command - prefer venv if it exists, otherwise system python
# This is evaluated at runtime, not at Makefile parse time
PYTHON = $(shell if [ -f "$(VENV_DIR)/bin/python" ]; then echo "$(VENV_DIR)/bin/python"; else echo "python3"; fi)

# Time window arguments
ifdef START
    TIME_ARGS += --start $(START)
endif
ifdef END
    TIME_ARGS += --end $(END)
endif

# Single subreddit mode
ifdef SUBREDDIT
    SUBREDDIT_ARG = --subreddit $(SUBREDDIT)
endif

# Max posts per subreddit
ifdef MAX_POSTS
    MAX_POSTS_ARG = --max-posts $(MAX_POSTS)
endif

# FETCH = number of source posts to preprocess/analyze (default 50)
FETCH ?= 50
# TOP = number of posts to include in final report (default 10)
TOP ?= 10
# MAX_POSTS = maximum posts to fetch per subreddit (default: from config, typically 50)
MAX_POSTS ?=

# Output directory naming
# MODE is set by targets (daily, weekly, monthly, single)
MODE ?= custom
# Generate timestamped output directory name
TIMESTAMP := $(shell date +%Y-%m-%d_%H%M%S)
ifdef SUBREDDIT
    OUTPUT_DIR = output/$(TIMESTAMP)_$(MODE)_$(SUBREDDIT)
else
    OUTPUT_DIR = output/$(TIMESTAMP)_$(MODE)_all
endif

# Legacy paths (for clean target)
RAW_JSON = output/raw_posts.json
PROCESSED_JSON = output/processed_posts.json
REPORT_MD = output/report.md

# ============================================================
# Main targets
# ============================================================

## install: Install Python dependencies (creates venv if needed)
install:
	@echo "Setting up virtual environment..."
	@if [ ! -d "$(VENV_DIR)" ]; then \
		echo "Creating virtual environment..."; \
		python3 -m venv $(VENV_DIR); \
	fi
	@echo "Installing dependencies..."
	@$(VENV_DIR)/bin/python -m pip install --upgrade pip
	@$(VENV_DIR)/bin/python -m pip install -r requirements.txt
	@echo "Done! Virtual environment ready at $(VENV_DIR)"
	@echo "To activate: source $(VENV_DIR)/bin/activate"

## fetch: Fetch and preprocess Reddit posts
fetch:
	@echo "Output directory: $(OUTPUT_DIR)"
	@mkdir -p $(OUTPUT_DIR)
	@echo "Fetching Reddit posts..."
	$(PYTHON) scripts/fetch_reddit.py $(TIME_ARGS) $(SUBREDDIT_ARG) $(MAX_POSTS_ARG) --config $(CONFIG) --output-dir $(OUTPUT_DIR)
	@echo ""
	@echo "Preprocessing posts..."
	$(PYTHON) scripts/preprocess.py --config $(CONFIG) --top $(FETCH) --output-dir $(OUTPUT_DIR)
	@echo ""
	@echo "Updating latest symlink..."
	@rm -f output/latest
	@ln -s $(shell basename $(OUTPUT_DIR)) output/latest
	@echo ""
	@echo "=========================================="
	@echo "Data ready: $(OUTPUT_DIR)/processed_posts.json"
	@echo "Latest:     output/latest -> $(shell basename $(OUTPUT_DIR))"
	@echo "=========================================="

## clean: Remove all output files
clean:
	@echo "Cleaning output directory..."
	rm -f $(RAW_JSON) $(PROCESSED_JSON) $(REPORT_MD)
	@echo "Done!"

# ============================================================
# Convenience shortcuts
# ============================================================

## daily: Fetch last 24 hours and generate report
daily:
	@START=$$(date -u -v-1d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d "1 day ago" +%Y-%m-%dT%H:%M:%SZ); \
	END=$$(date -u +%Y-%m-%dT%H:%M:%SZ); \
	echo "Fetching daily data: $$START to $$END"; \
	$(MAKE) fetch START=$$START END=$$END MODE=daily SUBREDDIT=$(SUBREDDIT) TOP=$(TOP) MAX_POSTS=$(MAX_POSTS) CONFIG=$(CONFIG)
	@$(MAKE) report CONFIG=$(CONFIG)

## weekly: Fetch last 7 days and generate report
weekly:
	@START=$$(date -u -v-7d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d "7 days ago" +%Y-%m-%dT%H:%M:%SZ); \
	END=$$(date -u +%Y-%m-%dT%H:%M:%SZ); \
	echo "Fetching weekly data: $$START to $$END"; \
	$(MAKE) fetch START=$$START END=$$END MODE=weekly SUBREDDIT=$(SUBREDDIT) TOP=$(TOP) MAX_POSTS=$(MAX_POSTS) CONFIG=$(CONFIG)
	@$(MAKE) report CONFIG=$(CONFIG)

## monthly: Fetch last 30 days and generate report
monthly:
	@START=$$(date -u -v-30d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d "30 days ago" +%Y-%m-%dT%H:%M:%SZ); \
	END=$$(date -u +%Y-%m-%dT%H:%M:%SZ); \
	echo "Fetching monthly data: $$START to $$END"; \
	$(MAKE) fetch START=$$START END=$$END MODE=monthly SUBREDDIT=$(SUBREDDIT) TOP=$(TOP) MAX_POSTS=$(MAX_POSTS) CONFIG=$(CONFIG)
	@$(MAKE) report CONFIG=$(CONFIG)

## single: Fetch top posts from a single subreddit and generate report (use SUBREDDIT=name TOP=N)
single:
ifndef SUBREDDIT
	@echo "Error: SUBREDDIT is required"
	@echo "Usage: make single SUBREDDIT=ClaudeAI TOP=10"
	@exit 1
endif
	@START=$$(date -u -v-7d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d "7 days ago" +%Y-%m-%dT%H:%M:%SZ); \
	END=$$(date -u +%Y-%m-%dT%H:%M:%SZ); \
	echo "Fetching top $(TOP) posts from r/$(SUBREDDIT): $$START to $$END"; \
	$(MAKE) fetch START=$$START END=$$END SUBREDDIT=$(SUBREDDIT) TOP=$(TOP) MODE=single MAX_POSTS=$(MAX_POSTS) CONFIG=$(CONFIG)
	@$(MAKE) report CONFIG=$(CONFIG)

## report: Generate digest report using Claude Code (requires data in output/latest)
report:
	@if [ ! -f "output/latest/processed_posts.json" ]; then \
		echo "Error: No data found at output/latest/processed_posts.json"; \
		echo "Run 'make single SUBREDDIT=X' or 'make weekly' first."; \
		exit 1; \
	fi
	@echo "Generating digest report with Claude Code..."
	@START_TIME=$$(date +%s); \
	claude --print --model sonnet --verbose --dangerously-skip-permissions --output-format stream-json \
		"Read the files $(CURDIR)/output/latest/processed_posts.json, $(CURDIR)/agents/weekly_digest_agent.md, and $(CURDIR)/$(CONFIG), then generate the digest report following the agent instructions. Include the top $(TOP) posts in the report. Save it to $(CURDIR)/output/latest/report.md" \
		| $(PYTHON) scripts/format_progress.py; \
	END_TIME=$$(date +%s); \
	ELAPSED=$$((END_TIME - START_TIME)); \
	MINS=$$((ELAPSED / 60)); \
	SECS=$$((ELAPSED % 60)); \
	echo ""; \
	echo "=========================================="; \
	echo "Report generated: output/latest/report.md"; \
	echo "Time elapsed: $${MINS}m $${SECS}s"; \
	echo "=========================================="

## report-interactive: Generate report with full interactive Claude UI
report-interactive:
	@if [ ! -f "output/latest/processed_posts.json" ]; then \
		echo "Error: No data found at output/latest/processed_posts.json"; \
		echo "Run 'make single SUBREDDIT=X' or 'make weekly' first."; \
		exit 1; \
	fi
	@echo "Launching Claude Code interactively..."
	@claude "Read the files output/latest/processed_posts.json, agents/weekly_digest_agent.md, and $(CONFIG), then generate the digest report following the agent instructions and save it to output/latest/report.md"
	@echo ""
	@echo "=========================================="
	@echo "Report generated: output/latest/report.md"
	@echo "=========================================="

# ============================================================
# Help
# ============================================================

## help: Show this help message
help:
	@echo "AI Reddit Digest"
	@echo "================"
	@echo ""
	@echo "Usage:"
	@echo "  make <target> [START=...] [END=...]"
	@echo ""
	@echo "Targets:"
	@grep -E '^## ' Makefile | sed 's/## /  /'
	@echo ""
	@echo "Examples:"
	@echo "  make install"
	@echo "  make weekly"
	@echo "  make fetch START=2025-01-01T00:00:00Z END=2025-01-08T00:00:00Z"
	@echo "  make single SUBREDDIT=ClaudeAI TOP=10"
	@echo "  make weekly SUBREDDIT=LocalLLaMA TOP=5"
	@echo "  make weekly CONFIG=config.prod.yaml"
	@echo "  make weekly MAX_POSTS=100"
	@echo ""
