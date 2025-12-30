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
#   make fetch SUBREDDIT=LocalLLaMA TOP=5
#
# After fetching, run Claude Code to generate the digest.
#

.PHONY: all install fetch clean help daily weekly monthly single

# Default target
all: help

# Virtual environment directory
VENV_DIR ?= venv

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

# Top posts count (default 50 for preprocessing, override with TOP=N)
TOP ?= 50

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
	$(PYTHON) scripts/fetch_reddit.py $(TIME_ARGS) $(SUBREDDIT_ARG) --output-dir $(OUTPUT_DIR)
	@echo ""
	@echo "Preprocessing posts..."
	$(PYTHON) scripts/preprocess.py --top $(TOP) --output-dir $(OUTPUT_DIR)
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

## daily: Fetch last 24 hours
daily:
	@START=$$(date -u -v-1d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d "1 day ago" +%Y-%m-%dT%H:%M:%SZ); \
	END=$$(date -u +%Y-%m-%dT%H:%M:%SZ); \
	echo "Fetching daily data: $$START to $$END"; \
	$(MAKE) fetch START=$$START END=$$END MODE=daily SUBREDDIT=$(SUBREDDIT) TOP=$(TOP)

## weekly: Fetch last 7 days
weekly:
	@START=$$(date -u -v-7d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d "7 days ago" +%Y-%m-%dT%H:%M:%SZ); \
	END=$$(date -u +%Y-%m-%dT%H:%M:%SZ); \
	echo "Fetching weekly data: $$START to $$END"; \
	$(MAKE) fetch START=$$START END=$$END MODE=weekly SUBREDDIT=$(SUBREDDIT) TOP=$(TOP)

## monthly: Fetch last 30 days
monthly:
	@START=$$(date -u -v-30d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d "30 days ago" +%Y-%m-%dT%H:%M:%SZ); \
	END=$$(date -u +%Y-%m-%dT%H:%M:%SZ); \
	echo "Fetching monthly data: $$START to $$END"; \
	$(MAKE) fetch START=$$START END=$$END MODE=monthly SUBREDDIT=$(SUBREDDIT) TOP=$(TOP)

## single: Fetch top posts from a single subreddit (use SUBREDDIT=name TOP=N)
single:
ifndef SUBREDDIT
	@echo "Error: SUBREDDIT is required"
	@echo "Usage: make single SUBREDDIT=ClaudeAI TOP=10"
	@exit 1
endif
	@START=$$(date -u -v-7d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d "7 days ago" +%Y-%m-%dT%H:%M:%SZ); \
	END=$$(date -u +%Y-%m-%dT%H:%M:%SZ); \
	echo "Fetching top $(TOP) posts from r/$(SUBREDDIT): $$START to $$END"; \
	$(MAKE) fetch START=$$START END=$$END SUBREDDIT=$(SUBREDDIT) TOP=$(TOP) MODE=single

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
	@echo ""
