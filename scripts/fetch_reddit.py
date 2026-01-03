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
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

import praw
import requests
from prawcore.exceptions import ResponseException, OAuthException

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from parse_time_window import get_time_window, load_config

# Content length limits
MAX_SELFTEXT_LENGTH = 2000
MAX_COMMENT_BODY_LENGTH = 1000
REDDIT_API_MAX_LIMIT = 100


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
            # Verify the client works by checking read_only status
            # Note: reddit.user.me() requires user login, but app-only auth is read-only
            if reddit.read_only:
                print("Authenticated with Reddit API (read-only mode)", file=sys.stderr)
            else:
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

    def _get_attr(self, obj: Any, key: str, default: Any = None) -> Any:
        """
        Get attribute from dict or PRAW object uniformly.

        Args:
            obj: Dict or PRAW object
            key: Attribute/key name
            default: Default value if not found

        Returns:
            The attribute value or default
        """
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    def _extract_post_data(self, post: Any, subreddit_name: str) -> Dict:
        """
        Extract relevant data from a Reddit post object.

        Args:
            post: PRAW Submission object or dict from JSON API
            subreddit_name: Name of the subreddit

        Returns:
            Normalized post data dictionary
        """
        get = lambda k, d=None: self._get_attr(post, k, d)

        author = get('author')
        author_str = str(author) if author else '[deleted]'

        created_utc = get('created_utc', 0)
        selftext = get('selftext', '') or ''
        link_flair = get('link_flair_text', '') or ''

        return {
            'id': get('id', ''),
            'title': get('title', ''),
            'author': author_str,
            'subreddit': subreddit_name,
            'score': get('score', 0),
            'upvote_ratio': get('upvote_ratio', 0),
            'num_comments': get('num_comments', 0),
            'created_utc': created_utc,
            'created_datetime': datetime.fromtimestamp(
                created_utc, tz=timezone.utc
            ).isoformat(),
            'url': get('url', ''),
            'permalink': f"https://reddit.com{get('permalink', '')}",
            'selftext': selftext[:MAX_SELFTEXT_LENGTH],
            'is_self': get('is_self', False),
            'link_flair_text': link_flair,
            'comments': []  # Will be populated later
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
            get = lambda k, d=None: self._get_attr(comment, k, d)

            # For PRAW objects, check if body attribute exists
            if not isinstance(comment, dict) and not hasattr(comment, 'body'):
                return None

            body = get('body', '')
            if not body or body in ('[deleted]', '[removed]'):
                return None

            author = get('author')
            author_str = str(author) if author else '[deleted]'

            return {
                'id': get('id', ''),
                'author': author_str,
                'body': body[:MAX_COMMENT_BODY_LENGTH],
                'score': get('score', 0),
                'created_utc': get('created_utc', 0),
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
                params = {'limit': min(REDDIT_API_MAX_LIMIT, self.max_posts)}
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
