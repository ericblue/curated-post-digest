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


def get_default_time_window(days: int = 7) -> Tuple[datetime, datetime]:
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
    if end > now + timedelta(hours=1):  # Allow 1 hour buffer for clock skew
        raise ValueError(f"End time ({end}) cannot be in the future")

    # Warn if window is very large (> 90 days)
    window_days = (end - start).days
    if window_days > 90:
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
    default_days = time_config.get('default_days', 7)

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
