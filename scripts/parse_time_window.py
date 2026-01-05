#!/usr/bin/env python3
"""
parse_time_window.py - Time window parsing and validation utilities

This module handles all time-related operations for the AI Reddit Digest:
- Parsing ISO-8601 timestamps from CLI args or config
- Computing default time windows (last N days)
- Normalizing all timestamps to UTC
- Validating time ranges

Usage:
    from parse_time_window import get_time_window
    start, end = get_time_window(start_arg, end_arg, config)
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional

import yaml
from dateutil import parser as date_parser
from dateutil.tz import tzutc

# Time window defaults and limits
DEFAULT_DAYS = 7
CLOCK_SKEW_BUFFER_HOURS = 1
LARGE_WINDOW_WARNING_DAYS = 90


def parse_iso_timestamp(timestamp_str: str) -> datetime:
    """
    Parse an ISO-8601 formatted timestamp string into a UTC datetime.

    Handles various ISO formats:
    - 2025-01-01T00:00:00Z
    - 2025-01-01T00:00:00+00:00
    - 2025-01-01 (assumes midnight UTC)

    Args:
        timestamp_str: ISO-8601 formatted timestamp string

    Returns:
        datetime object normalized to UTC

    Raises:
        ValueError: If the timestamp cannot be parsed
    """
    try:
        dt = date_parser.parse(timestamp_str)
        # If no timezone info, assume UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        # Convert to UTC
        return dt.astimezone(timezone.utc)
    except Exception as e:
        raise ValueError(f"Cannot parse timestamp '{timestamp_str}': {e}")


def get_default_time_window(days: int = DEFAULT_DAYS) -> Tuple[datetime, datetime]:
    """
    Get the default time window: last N days ending now.

    Args:
        days: Number of days to look back (default: 7)

    Returns:
        Tuple of (start_datetime, end_datetime) in UTC
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    return start, end


def validate_time_window(start: datetime, end: datetime) -> None:
    """
    Validate that a time window is sensible.

    Args:
        start: Start datetime
        end: End datetime

    Raises:
        ValueError: If the time window is invalid
    """
    if start >= end:
        raise ValueError(f"Start time ({start}) must be before end time ({end})")

    now = datetime.now(timezone.utc)
    if end > now + timedelta(hours=CLOCK_SKEW_BUFFER_HOURS):
        raise ValueError(f"End time ({end}) cannot be in the future")

    # Warn if window is very large
    window_days = (end - start).days
    if window_days > LARGE_WINDOW_WARNING_DAYS:
        print(f"Warning: Large time window ({window_days} days). This may take a while.",
              file=sys.stderr)


def get_time_window(
    start_arg: Optional[str] = None,
    end_arg: Optional[str] = None,
    config: Optional[dict] = None
) -> Tuple[datetime, datetime]:
    """
    Determine the time window for fetching Reddit content.

    Priority order:
    1. CLI arguments (start_arg, end_arg)
    2. Config file values (config['time_window']['start'], config['time_window']['end'])
    3. Default: last N days (from config['time_window']['default_days'] or 7)

    Args:
        start_arg: Optional start timestamp from CLI
        end_arg: Optional end timestamp from CLI
        config: Optional config dictionary

    Returns:
        Tuple of (start_datetime, end_datetime) in UTC
    """
    config = config or {}
    time_config = config.get('time_window', {})
    default_days = time_config.get('default_days', DEFAULT_DAYS)

    # Determine start time
    start = None
    if start_arg:
        start = parse_iso_timestamp(start_arg)
    elif time_config.get('start'):
        start = parse_iso_timestamp(time_config['start'])

    # Determine end time
    end = None
    if end_arg:
        end = parse_iso_timestamp(end_arg)
    elif time_config.get('end'):
        end = parse_iso_timestamp(time_config['end'])

    # Apply defaults if needed
    if start is None and end is None:
        # Both missing: use default window
        start, end = get_default_time_window(default_days)
    elif start is None:
        # Only end provided: go back default_days from end
        start = end - timedelta(days=default_days)
    elif end is None:
        # Only start provided: go forward default_days from start (or to now)
        end = min(start + timedelta(days=default_days), datetime.now(timezone.utc))

    # Validate
    validate_time_window(start, end)

    return start, end


def format_timestamp(dt: datetime) -> str:
    """
    Format a datetime as a human-readable string.

    Args:
        dt: datetime object

    Returns:
        Formatted string like "2025-01-01 00:00 UTC"
    """
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def format_timestamp_iso(dt: datetime) -> str:
    """
    Format a datetime as ISO-8601.

    Args:
        dt: datetime object

    Returns:
        ISO-8601 formatted string
    """
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def format_date_range(start: datetime, end: datetime) -> str:
    """
    Format a date range for display in reports.

    Args:
        start: Start datetime
        end: End datetime

    Returns:
        Formatted string like "2025-01-01 -> 2025-01-08"
    """
    return f"{start.strftime('%Y-%m-%d')} -> {end.strftime('%Y-%m-%d')}"


def load_config(config_path: str = "config.yaml") -> dict:
    """
    Load configuration from YAML file.

    Args:
        config_path: Path to config file

    Returns:
        Configuration dictionary
    """
    try:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        print(f"Warning: Config file not found at {config_path}, using defaults",
              file=sys.stderr)
        return {}


def validate_config(config: dict) -> None:
    """
    Validate configuration values.

    Checks for:
    - Scoring weights that sum to approximately 1.0
    - Valid numeric ranges for thresholds and scores
    - Invalid or missing critical values

    Args:
        config: Configuration dictionary to validate

    Raises:
        ValueError: If configuration is invalid
    """
    # Validate scoring weights (only heuristic scoring, not Claude-assessed)
    scoring = config.get('scoring', {})
    weight_sum = (
        scoring.get('engagement_weight', 0.3) +
        scoring.get('comments_weight', 0.25) +
        scoring.get('recency_weight', 0.2) +
        scoring.get('content_weight', 0.15) +
        scoring.get('ratio_weight', 0.1)
    )
    # Note: novelty_weight and relevance_weight are Claude-assessed, not part of heuristic

    if abs(weight_sum - 1.0) > 0.1:  # Allow 10% tolerance
        print(f"Warning: Heuristic scoring weights sum to {weight_sum:.2f}, expected ~1.0",
              file=sys.stderr)

    # Validate content thresholds
    thresholds = config.get('content_thresholds', {})
    for key in ['very_short', 'brief', 'good', 'substantial']:
        value = thresholds.get(key)
        if value is not None and value < 0:
            raise ValueError(f"content_thresholds.{key} must be positive, got {value}")

    # Ensure thresholds are in ascending order
    if all(key in thresholds for key in ['very_short', 'brief', 'good', 'substantial']):
        if (thresholds['very_short'] >= thresholds['brief'] or
            thresholds['brief'] >= thresholds['good'] or
            thresholds['good'] >= thresholds['substantial']):
            raise ValueError("content_thresholds must be in ascending order")

    # Validate content scores are between 0 and 1
    scores = config.get('content_scores', {})
    for key, value in scores.items():
        if not 0 <= value <= 1:
            raise ValueError(f"content_scores.{key} must be between 0 and 1, got {value}")

    # Validate formatting limits
    formatting = config.get('formatting', {})
    for key in ['max_selftext_length', 'max_comment_body_length', 'max_top_comments']:
        value = formatting.get(key)
        if value is not None and value < 0:
            raise ValueError(f"formatting.{key} must be positive, got {value}")

    # Validate fetch settings
    fetch = config.get('fetch', {})
    if fetch.get('max_posts_per_subreddit', 0) < 0:
        raise ValueError("fetch.max_posts_per_subreddit must be positive")
    if fetch.get('max_comments_per_post', 0) < 0:
        raise ValueError("fetch.max_comments_per_post must be positive")
    if fetch.get('min_score', 0) < 0:
        raise ValueError("fetch.min_score must be positive")
    if fetch.get('rate_limit_delay', 0) < 0:
        raise ValueError("fetch.rate_limit_delay must be positive")

    # Validate subreddits list
    subreddits = config.get('subreddits', [])
    if not isinstance(subreddits, list):
        raise ValueError("subreddits must be a list")

    # Check for duplicate subreddits (case-insensitive)
    seen = set()
    duplicates = []
    for sub in subreddits:
        sub_lower = sub.lower()
        if sub_lower in seen:
            duplicates.append(sub)
        seen.add(sub_lower)

    if duplicates:
        print(f"Warning: Duplicate subreddits found (case-insensitive): {duplicates}",
              file=sys.stderr)


def main():
    """
    CLI interface for testing time window parsing.

    Usage:
        python parse_time_window.py --start 2025-01-01T00:00:00Z --end 2025-01-08T00:00:00Z
        python parse_time_window.py  # Uses defaults from config
    """
    arg_parser = argparse.ArgumentParser(
        description="Parse and validate time windows for AI Reddit Digest"
    )
    arg_parser.add_argument(
        '--start', '-s',
        help='Start timestamp (ISO-8601 format)',
        default=None
    )
    arg_parser.add_argument(
        '--end', '-e',
        help='End timestamp (ISO-8601 format)',
        default=None
    )
    arg_parser.add_argument(
        '--config', '-c',
        help='Path to config file',
        default='config.yaml'
    )

    args = arg_parser.parse_args()

    # Load config
    config = load_config(args.config)

    try:
        # Get time window
        start, end = get_time_window(args.start, args.end, config)

        # Output results
        print(f"Time Window:")
        print(f"  Start: {format_timestamp(start)}")
        print(f"  End:   {format_timestamp(end)}")
        print(f"  Range: {format_date_range(start, end)}")
        print(f"  Duration: {(end - start).days} days")
        print()
        print(f"ISO Format (for scripting):")
        print(f"  START={format_timestamp_iso(start)}")
        print(f"  END={format_timestamp_iso(end)}")

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
