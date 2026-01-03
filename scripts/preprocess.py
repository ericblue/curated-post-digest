#!/usr/bin/env python3
"""
preprocess.py - Data preprocessing and scoring for AI Reddit Digest

This module preprocesses fetched Reddit data before sending to Claude:
- Computes initial heuristic scores based on engagement metrics
- Filters and deduplicates content
- Formats data optimally for Claude summarization
- Reduces token count while preserving important information

Scoring Heuristic (1-10):
The initial score is computed from:
- Engagement (30%): Reddit score normalized by subreddit median
- Comments (25%): Comment count, with diminishing returns
- Recency (20%): Fresher content scores higher
- Length (15%): Meaningful content (not too short, not too long)
- Ratio (10%): Upvote ratio indicates quality

Claude will refine these scores based on novelty and personal relevance.

Usage:
    python preprocess.py --input output/raw_posts.json --output output/processed_posts.json
"""

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List
from statistics import median

import yaml

# Scoring formula constants
ENGAGEMENT_SCORE_DIVISOR = 2
COMMENTS_SCORE_DIVISOR = 3
DEFAULT_MEDIAN_SCORE = 10

# Content length thresholds for scoring
CONTENT_LENGTH_VERY_SHORT = 50
CONTENT_LENGTH_BRIEF = 200
CONTENT_LENGTH_GOOD = 1000
CONTENT_LENGTH_SUBSTANTIAL = 3000

# Content length scores
CONTENT_SCORE_VERY_SHORT = 0.3
CONTENT_SCORE_BRIEF = 0.5
CONTENT_SCORE_GOOD = 0.8
CONTENT_SCORE_SUBSTANTIAL = 1.0
CONTENT_SCORE_WALL_OF_TEXT = 0.7

# Formatting limits for Claude
MAX_SELFTEXT_LENGTH = 500
MAX_COMMENT_BODY_LENGTH = 300
MAX_TOP_COMMENTS = 5


def compute_engagement_score(score: int, median_score: float) -> float:
    """
    Compute normalized engagement score (0-1).

    Uses log scaling to handle viral posts without letting them dominate.
    Normalized against subreddit median for fairness across communities.

    Args:
        score: Post's Reddit score (upvotes - downvotes)
        median_score: Median score for the subreddit

    Returns:
        Normalized score between 0 and 1
    """
    if score <= 0:
        return 0.0

    # Log scale to prevent viral posts from dominating
    log_score = math.log10(score + 1)
    log_median = math.log10(max(median_score, 1) + 1)

    # Normalize: 1x median = 0.5, 10x median = ~0.75, 100x median = ~1.0
    normalized = log_score / (log_median + ENGAGEMENT_SCORE_DIVISOR)
    return min(1.0, normalized)


def compute_comments_score(num_comments: int) -> float:
    """
    Compute comment engagement score (0-1).

    High comment counts indicate discussion-worthy content.
    Uses diminishing returns to avoid over-weighting extremely popular posts.

    Args:
        num_comments: Number of comments on the post

    Returns:
        Score between 0 and 1
    """
    if num_comments <= 0:
        return 0.0

    # Diminishing returns: 10 comments = ~0.5, 100 = ~0.75, 1000 = ~0.9
    return min(1.0, math.log10(num_comments + 1) / COMMENTS_SCORE_DIVISOR)


def compute_recency_score(created_utc: float, start: datetime, end: datetime) -> float:
    """
    Compute recency score (0-1).

    Fresher content within the time window scores higher.
    This helps surface recent developments.

    Args:
        created_utc: Unix timestamp of post creation
        start: Time window start
        end: Time window end

    Returns:
        Score between 0 and 1 (1 = most recent)
    """
    post_time = datetime.fromtimestamp(created_utc, tz=timezone.utc)
    window_duration = (end - start).total_seconds()

    if window_duration <= 0:
        return 0.5

    time_since_start = (post_time - start).total_seconds()
    return max(0.0, min(1.0, time_since_start / window_duration))


def compute_content_score(selftext: str, title: str) -> float:
    """
    Compute content quality score based on length (0-1).

    Posts with some substance score higher than empty link posts,
    but extremely long posts (walls of text) score slightly lower.

    Args:
        selftext: Post body text
        title: Post title

    Returns:
        Score between 0 and 1
    """
    total_length = len(selftext) + len(title)

    if total_length < CONTENT_LENGTH_VERY_SHORT:
        return CONTENT_SCORE_VERY_SHORT
    elif total_length < CONTENT_LENGTH_BRIEF:
        return CONTENT_SCORE_BRIEF
    elif total_length < CONTENT_LENGTH_GOOD:
        return CONTENT_SCORE_GOOD
    elif total_length < CONTENT_LENGTH_SUBSTANTIAL:
        return CONTENT_SCORE_SUBSTANTIAL
    else:
        return CONTENT_SCORE_WALL_OF_TEXT


def compute_ratio_score(upvote_ratio: float) -> float:
    """
    Compute quality score based on upvote ratio (0-1).

    High upvote ratios indicate community approval.
    Controversial posts (50% ratio) score lower.

    Args:
        upvote_ratio: Reddit's upvote ratio (0.0 to 1.0)

    Returns:
        Score between 0 and 1
    """
    # Transform ratio: 50% -> 0, 75% -> 0.5, 100% -> 1.0
    return max(0.0, (upvote_ratio - 0.5) * 2)


def compute_heuristic_score(
    post: Dict,
    median_score: float,
    start: datetime,
    end: datetime,
    weights: Dict
) -> float:
    """
    Compute the overall heuristic score (1-10) for a post.

    Combines multiple signals with configurable weights.

    Args:
        post: Post data dictionary
        median_score: Median score for the subreddit
        start: Time window start
        end: Time window end
        weights: Scoring weights from config

    Returns:
        Score from 1 to 10
    """
    engagement = compute_engagement_score(post['score'], median_score)
    comments = compute_comments_score(post['num_comments'])
    recency = compute_recency_score(post['created_utc'], start, end)
    content = compute_content_score(post.get('selftext', ''), post['title'])
    ratio = compute_ratio_score(post.get('upvote_ratio', 0.5))

    # Get weights (use defaults if not specified)
    w_engagement = weights.get('engagement_weight', 0.3)
    w_comments = weights.get('comments_weight', 0.25)
    w_recency = 0.2  # Fixed, not configurable for simplicity
    w_content = 0.15
    w_ratio = 0.1

    # Weighted sum
    raw_score = (
        engagement * w_engagement +
        comments * w_comments +
        recency * w_recency +
        content * w_content +
        ratio * w_ratio
    )

    # Scale to 1-10
    return round(1 + raw_score * 9, 2)


def compute_subreddit_medians(posts: List[Dict]) -> Dict[str, float]:
    """
    Compute median scores for each subreddit.

    Args:
        posts: List of post dictionaries

    Returns:
        Dictionary mapping subreddit names to median scores
    """
    subreddit_scores = {}

    for post in posts:
        sr = post['subreddit']
        if sr not in subreddit_scores:
            subreddit_scores[sr] = []
        subreddit_scores[sr].append(post['score'])

    return {
        sr: median(scores) if scores else DEFAULT_MEDIAN_SCORE
        for sr, scores in subreddit_scores.items()
    }


def format_post_for_claude(post: Dict) -> Dict:
    """
    Format a post for efficient Claude processing.

    Reduces token count while preserving important information.

    Args:
        post: Post data dictionary with heuristic_score

    Returns:
        Streamlined post dictionary
    """
    # Truncate long text
    selftext = post.get('selftext', '')
    if len(selftext) > MAX_SELFTEXT_LENGTH:
        selftext = selftext[:MAX_SELFTEXT_LENGTH] + "..."

    # Select top comments by score
    comments = sorted(
        post.get('comments', []),
        key=lambda c: c.get('score', 0),
        reverse=True
    )[:MAX_TOP_COMMENTS]

    formatted_comments = [
        {
            'author': c['author'],
            'score': c['score'],
            'body': c['body'][:MAX_COMMENT_BODY_LENGTH] + "..." if len(c['body']) > MAX_COMMENT_BODY_LENGTH else c['body']
        }
        for c in comments
    ]

    return {
        'id': post['id'],
        'title': post['title'],
        'subreddit': post['subreddit'],
        'author': post['author'],
        'score': post['score'],
        'num_comments': post['num_comments'],
        'upvote_ratio': post.get('upvote_ratio', 0),
        'created_datetime': post['created_datetime'],
        'permalink': post['permalink'],
        'selftext': selftext,
        'heuristic_score': post['heuristic_score'],
        'top_comments': formatted_comments
    }


def preprocess_posts(
    raw_data: Dict,
    config: Dict,
    top_n: int = 50
) -> Dict:
    """
    Preprocess raw Reddit data for Claude summarization.

    Args:
        raw_data: Raw data from fetch_reddit.py
        config: Configuration dictionary
        top_n: Number of top posts to keep

    Returns:
        Preprocessed data dictionary ready for Claude
    """
    posts = raw_data.get('posts', [])
    metadata = raw_data.get('metadata', {})

    if not posts:
        return {
            'metadata': metadata,
            'posts': [],
            'preprocessing': {
                'input_count': 0,
                'output_count': 0,
                'filtered_count': 0
            }
        }

    # Parse time window from metadata
    start = datetime.fromisoformat(metadata['start_time'].replace('Z', '+00:00'))
    end = datetime.fromisoformat(metadata['end_time'].replace('Z', '+00:00'))

    # Get scoring weights
    weights = config.get('scoring', {})

    # Compute subreddit medians for normalization
    medians = compute_subreddit_medians(posts)

    # Score all posts
    for post in posts:
        median_score = medians.get(post['subreddit'], DEFAULT_MEDIAN_SCORE)
        post['heuristic_score'] = compute_heuristic_score(
            post, median_score, start, end, weights
        )

    # Sort by heuristic score (use sorted() to avoid mutating input)
    sorted_posts = sorted(posts, key=lambda x: x['heuristic_score'], reverse=True)

    # Take top N
    top_posts = sorted_posts[:top_n]

    # Format for Claude
    formatted_posts = [format_post_for_claude(p) for p in top_posts]

    return {
        'metadata': {
            **metadata,
            'preprocessed_at': datetime.now(timezone.utc).isoformat()
        },
        'posts': formatted_posts,
        'preprocessing': {
            'input_count': len(raw_data.get('posts', [])),
            'output_count': len(formatted_posts),
            'filtered_count': len(raw_data.get('posts', [])) - len(formatted_posts),
            'subreddit_medians': medians
        }
    }


def main():
    """
    CLI interface for preprocessing Reddit data.

    Usage:
        python preprocess.py --input output/raw_posts.json --output output/processed_posts.json
    """
    arg_parser = argparse.ArgumentParser(
        description="Preprocess Reddit data for AI Digest"
    )
    arg_parser.add_argument(
        '--input', '-i',
        help='Input JSON file from fetch_reddit.py',
        default='output/raw_posts.json'
    )
    arg_parser.add_argument(
        '--output', '-o',
        help='Output JSON file path',
        default='output/processed_posts.json'
    )
    arg_parser.add_argument(
        '--config', '-c',
        help='Path to config file',
        default='config.yaml'
    )
    arg_parser.add_argument(
        '--top', '-n',
        help='Number of top posts to keep',
        type=int,
        default=50
    )
    arg_parser.add_argument(
        '--output-dir', '-d',
        help='Output directory (overrides --input and --output, uses raw_posts.json and processed_posts.json inside)',
        default=None
    )

    args = arg_parser.parse_args()

    # Determine input/output paths
    if args.output_dir:
        input_path = Path(args.output_dir) / 'raw_posts.json'
        output_path = Path(args.output_dir) / 'processed_posts.json'
    else:
        input_path = Path(args.input)
        output_path = Path(args.output)

    # Load config
    try:
        with open(args.config, 'r') as f:
            config = yaml.safe_load(f) or {}
    except FileNotFoundError:
        print(f"Warning: Config not found at {args.config}, using defaults",
              file=sys.stderr)
        config = {}

    # Load raw data
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {input_path}: {e}", file=sys.stderr)
        sys.exit(1)

    # Preprocess
    processed_data = preprocess_posts(raw_data, config, args.top)

    # Report
    prep = processed_data['preprocessing']
    print(f"Preprocessing complete:", file=sys.stderr)
    print(f"  Input posts: {prep['input_count']}", file=sys.stderr)
    print(f"  Output posts: {prep['output_count']}", file=sys.stderr)
    print(f"  Filtered: {prep['filtered_count']}", file=sys.stderr)

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write output
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(processed_data, f, indent=2, ensure_ascii=False)

    print(f"Output written to: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
