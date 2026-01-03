#!/usr/bin/env python3
"""
fetch_reddit.py - Reddit content fetcher for AI Reddit Digest

This module fetches posts and comments from specified subreddits within a time window.
Uses PRAW (Python Reddit API Wrapper) for authenticated access, with RSS fallback.

Key features:
- Respects Reddit API rate limits
- Filters content by time window
- Normalizes data to consistent JSON format
- Handles both authenticated and unauthenticated modes

Usage:
    python fetch_reddit.py --start 2025-01-01T00:00:00Z --end 2025-01-08T00:00:00Z
    python fetch_reddit.py  # Uses defaults from config
    python fetch_reddit.py --subreddit ClaudeAI  # Single subreddit mode

Output:
    Writes JSON data to output/raw_posts.json
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

import praw
import requests
import yaml
from prawcore.exceptions import ResponseException, OAuthException

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from parse_time_window import get_time_window, load_config, format_timestamp_iso


class RedditFetcher:
    """
    Fetches Reddit posts and comments within a specified time window.

    Supports two modes:
    1. Authenticated (PRAW): Better rate limits, more data
    2. Unauthenticated (JSON API): More limited but no credentials needed
    """

    def __init__(self, config: dict):
        """
        Initialize the Reddit fetcher.

        Args:
            config: Configuration dictionary from config.yaml
        """
        self.config = config
        self.reddit_config = config.get('reddit', {})
        self.fetch_config = config.get('fetch', {})

        # Fetch settings with defaults
        self.max_posts = self.fetch_config.get('max_posts_per_subreddit', 50)
        self.max_comments = self.fetch_config.get('max_comments_per_post', 20)
        self.min_score = self.fetch_config.get('min_score', 5)
        self.rate_limit_delay = self.fetch_config.get('rate_limit_delay', 2)

        # Initialize Reddit client
        self.reddit = self._init_reddit_client()
        self.use_authenticated = self.reddit is not None

    def _init_reddit_client(self) -> Optional[praw.Reddit]:
        """
        Initialize PRAW Reddit client if credentials are available.

        Returns:
            praw.Reddit instance or None if credentials unavailable
        """
        client_id = self.reddit_config.get('client_id', '').strip()
        client_secret = self.reddit_config.get('client_secret', '').strip()
        user_agent = self.reddit_config.get('user_agent', 'AI-Reddit-Digest/1.0')

        if not client_id or not client_secret:
            print("No Reddit API credentials found, using unauthenticated mode",
                  file=sys.stderr)
            print("(Rate limits will be more restrictive)", file=sys.stderr)
            return None

        try:
            reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=user_agent
            )
            # Test the connection
            reddit.user.me()
            print("Authenticated with Reddit API", file=sys.stderr)
            return reddit
        except (ResponseException, OAuthException) as e:
            print(f"Warning: Reddit authentication failed: {e}", file=sys.stderr)
            print("Falling back to unauthenticated mode", file=sys.stderr)
            return None

    def _is_within_time_window(
        self,
        timestamp: float,
        start: datetime,
        end: datetime
    ) -> bool:
        """
        Check if a Unix timestamp falls within the time window.

        Args:
            timestamp: Unix timestamp
            start: Start datetime (UTC)
            end: End datetime (UTC)

        Returns:
            True if timestamp is within window
        """
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        return start <= dt <= end

    def _extract_post_data(self, post: Any, subreddit_name: str) -> Dict:
        """
        Extract relevant data from a Reddit post object.

        Args:
            post: PRAW Submission object or dict from JSON API
            subreddit_name: Name of the subreddit

        Returns:
            Normalized post data dictionary
        """
        # Handle both PRAW objects and dicts
        if isinstance(post, dict):
            return {
                'id': post.get('id', ''),
                'title': post.get('title', ''),
                'author': str(post.get('author', '[deleted]')),
                'subreddit': subreddit_name,
                'score': post.get('score', 0),
                'upvote_ratio': post.get('upvote_ratio', 0),
                'num_comments': post.get('num_comments', 0),
                'created_utc': post.get('created_utc', 0),
                'created_datetime': datetime.fromtimestamp(
                    post.get('created_utc', 0), tz=timezone.utc
                ).isoformat(),
                'url': post.get('url', ''),
                'permalink': f"https://reddit.com{post.get('permalink', '')}",
                'selftext': post.get('selftext', '')[:2000],  # Limit length
                'is_self': post.get('is_self', False),
                'link_flair_text': post.get('link_flair_text', ''),
                'comments': []  # Will be populated later
            }
        else:
            # PRAW Submission object
            return {
                'id': post.id,
                'title': post.title,
                'author': str(post.author) if post.author else '[deleted]',
                'subreddit': subreddit_name,
                'score': post.score,
                'upvote_ratio': post.upvote_ratio,
                'num_comments': post.num_comments,
                'created_utc': post.created_utc,
                'created_datetime': datetime.fromtimestamp(
                    post.created_utc, tz=timezone.utc
                ).isoformat(),
                'url': post.url,
                'permalink': f"https://reddit.com{post.permalink}",
                'selftext': (post.selftext or '')[:2000],
                'is_self': post.is_self,
                'link_flair_text': post.link_flair_text or '',
                'comments': []
            }

    def _extract_comment_data(self, comment: Any) -> Optional[Dict]:
        """
        Extract relevant data from a Reddit comment.

        Args:
            comment: PRAW Comment object or dict

        Returns:
            Normalized comment data dictionary or None if invalid
        """
        try:
            if isinstance(comment, dict):
                body = comment.get('body', '')
                if not body or body == '[deleted]' or body == '[removed]':
                    return None
                return {
                    'id': comment.get('id', ''),
                    'author': str(comment.get('author', '[deleted]')),
                    'body': body[:1000],  # Limit length
                    'score': comment.get('score', 0),
                    'created_utc': comment.get('created_utc', 0),
                }
            else:
                # PRAW Comment object
                if not hasattr(comment, 'body'):
                    return None
                body = comment.body
                if not body or body == '[deleted]' or body == '[removed]':
                    return None
                return {
                    'id': comment.id,
                    'author': str(comment.author) if comment.author else '[deleted]',
                    'body': body[:1000],
                    'score': comment.score,
                    'created_utc': comment.created_utc,
                }
        except AttributeError:
            return None

    def fetch_subreddit_posts_authenticated(
        self,
        subreddit_name: str,
        start: datetime,
        end: datetime
    ) -> List[Dict]:
        """
        Fetch posts from a subreddit using authenticated PRAW.

        Args:
            subreddit_name: Name of subreddit (without r/)
            start: Start datetime (UTC)
            end: End datetime (UTC)

        Returns:
            List of post dictionaries
        """
        posts = []
        subreddit = self.reddit.subreddit(subreddit_name)

        try:
            # Fetch recent posts (new + hot + top for better coverage)
            seen_ids = set()

            for listing in ['new', 'hot', 'top']:
                if listing == 'top':
                    submissions = subreddit.top(time_filter='week', limit=self.max_posts)
                elif listing == 'hot':
                    submissions = subreddit.hot(limit=self.max_posts)
                else:
                    submissions = subreddit.new(limit=self.max_posts)

                for post in submissions:
                    # Skip duplicates
                    if post.id in seen_ids:
                        continue
                    seen_ids.add(post.id)

                    # Check time window
                    if not self._is_within_time_window(post.created_utc, start, end):
                        continue

                    # Check minimum score
                    if post.score < self.min_score:
                        continue

                    post_data = self._extract_post_data(post, subreddit_name)

                    # Fetch top comments
                    try:
                        post.comments.replace_more(limit=0)  # Skip "load more"
                        comments = []
                        for comment in post.comments[:self.max_comments]:
                            comment_data = self._extract_comment_data(comment)
                            if comment_data:
                                comments.append(comment_data)
                        post_data['comments'] = comments
                    except Exception as e:
                        print(f"  Warning: Could not fetch comments for {post.id}: {e}",
                              file=sys.stderr)

                    posts.append(post_data)

                    # Rate limiting
                    time.sleep(self.rate_limit_delay)

                    if len(posts) >= self.max_posts:
                        break

        except Exception as e:
            print(f"Error fetching from r/{subreddit_name}: {e}", file=sys.stderr)

        return posts

    def fetch_subreddit_posts_unauthenticated(
        self,
        subreddit_name: str,
        start: datetime,
        end: datetime
    ) -> List[Dict]:
        """
        Fetch posts from a subreddit using Reddit's public JSON API.
        This is rate-limited but requires no credentials.

        Args:
            subreddit_name: Name of subreddit (without r/)
            start: Start datetime (UTC)
            end: End datetime (UTC)

        Returns:
            List of post dictionaries
        """
        posts = []
        headers = {
            'User-Agent': self.reddit_config.get('user_agent', 'AI-Reddit-Digest/1.0')
        }

        try:
            # Fetch from multiple listings for better coverage
            for listing in ['new', 'hot', 'top']:
                url = f"https://www.reddit.com/r/{subreddit_name}/{listing}.json"
                params = {'limit': min(100, self.max_posts)}
                if listing == 'top':
                    params['t'] = 'week'

                response = requests.get(url, headers=headers, params=params, timeout=30)
                response.raise_for_status()

                data = response.json()
                children = data.get('data', {}).get('children', [])

                seen_ids = {p['id'] for p in posts}

                for child in children:
                    post = child.get('data', {})

                    # Skip duplicates
                    if post.get('id') in seen_ids:
                        continue

                    # Check time window
                    created = post.get('created_utc', 0)
                    if not self._is_within_time_window(created, start, end):
                        continue

                    # Check minimum score
                    if post.get('score', 0) < self.min_score:
                        continue

                    post_data = self._extract_post_data(post, subreddit_name)

                    # For unauthenticated mode, skip deep comment fetching
                    # to avoid rate limits. Include basic comment info if available.
                    post_data['comments'] = []

                    posts.append(post_data)
                    seen_ids.add(post['id'])

                    if len(posts) >= self.max_posts:
                        break

                # Rate limiting between API calls
                time.sleep(self.rate_limit_delay)

        except requests.RequestException as e:
            print(f"Error fetching from r/{subreddit_name}: {e}", file=sys.stderr)

        return posts

    def fetch_all(
        self,
        subreddits: List[str],
        start: datetime,
        end: datetime
    ) -> Dict:
        """
        Fetch posts from all specified subreddits.

        Args:
            subreddits: List of subreddit names
            start: Start datetime (UTC)
            end: End datetime (UTC)

        Returns:
            Dictionary with metadata and posts
        """
        all_posts = []

        print(f"\nFetching posts from {len(subreddits)} subreddits...", file=sys.stderr)
        print(f"Time window: {start.isoformat()} to {end.isoformat()}", file=sys.stderr)
        print(f"Mode: {'Authenticated' if self.use_authenticated else 'Unauthenticated'}",
              file=sys.stderr)
        print("-" * 50, file=sys.stderr)

        for i, subreddit in enumerate(subreddits, 1):
            print(f"[{i}/{len(subreddits)}] Fetching r/{subreddit}...", file=sys.stderr)

            if self.use_authenticated:
                posts = self.fetch_subreddit_posts_authenticated(subreddit, start, end)
            else:
                posts = self.fetch_subreddit_posts_unauthenticated(subreddit, start, end)

            print(f"  Found {len(posts)} posts", file=sys.stderr)
            all_posts.extend(posts)

            # Additional rate limiting between subreddits
            if i < len(subreddits):
                time.sleep(self.rate_limit_delay)

        # Sort by score (descending) for easier processing
        all_posts.sort(key=lambda x: x['score'], reverse=True)

        print("-" * 50, file=sys.stderr)
        print(f"Total: {len(all_posts)} posts fetched", file=sys.stderr)

        return {
            'metadata': {
                'fetch_time': datetime.now(timezone.utc).isoformat(),
                'start_time': start.isoformat(),
                'end_time': end.isoformat(),
                'subreddits': subreddits,
                'total_posts': len(all_posts),
                'authenticated': self.use_authenticated
            },
            'posts': all_posts
        }


def main():
    """
    CLI interface for fetching Reddit content.

    Usage:
        python fetch_reddit.py --start 2025-01-01T00:00:00Z --end 2025-01-08T00:00:00Z
        python fetch_reddit.py --output custom_output.json
    """
    arg_parser = argparse.ArgumentParser(
        description="Fetch Reddit posts for AI Digest"
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
    arg_parser.add_argument(
        '--output', '-o',
        help='Output JSON file path',
        default='output/raw_posts.json'
    )
    arg_parser.add_argument(
        '--output-dir', '-d',
        help='Output directory (overrides --output, writes raw_posts.json inside)',
        default=None
    )
    arg_parser.add_argument(
        '--subreddit', '-r',
        help='Fetch from a single subreddit only (overrides config)',
        default=None
    )
    arg_parser.add_argument(
        '--max-posts', '-m',
        help='Maximum posts to fetch per subreddit (overrides config)',
        type=int,
        default=None
    )

    args = arg_parser.parse_args()

    # Load config
    config = load_config(args.config)

    # Override max_posts in config if CLI argument provided
    if args.max_posts is not None:
        if 'fetch' not in config:
            config['fetch'] = {}
        config['fetch']['max_posts_per_subreddit'] = args.max_posts

    # Get time window
    try:
        start, end = get_time_window(args.start, args.end, config)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Get subreddits - single subreddit flag overrides config
    if args.subreddit:
        subreddits = [args.subreddit]
        print(f"Single subreddit mode: r/{args.subreddit}", file=sys.stderr)
    else:
        subreddits = config.get('subreddits', [
            'MachineLearning', 'LocalLLaMA', 'ChatGPT', 'OpenAI'
        ])

    # Initialize fetcher and fetch
    fetcher = RedditFetcher(config)
    data = fetcher.fetch_all(subreddits, start, end)

    # Determine output path
    if args.output_dir:
        output_path = Path(args.output_dir) / 'raw_posts.json'
    else:
        output_path = Path(args.output)

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write output
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\nOutput written to: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
