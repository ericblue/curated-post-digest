# Curated Post Digest

A local-first system that curates and summarizes discussions from multiple platforms on any topic you choose, using Claude Code.

> **Note:** Version 1.0 currently supports Reddit only. Future versions will add support for Twitter/X, LinkedIn, and other platforms. See [Roadmap](#roadmap) below.
>
> **Customization:** Configure `config.yaml` with your interests and sources. The example configuration focuses on AI topics, but you can adapt it for any subject matter—technology, science, finance, gaming, or any other area of interest.

## Quick Start

```bash
# Clone the repository (or navigate to your project directory)
git clone https://github.com/ericblue/curated-post-digest.git
cd curated-post-digest

# Install dependencies
pip install -r requirements.txt

# Fetch last 7 days of posts and generate digest (automatic)
make weekly
```

The `make weekly` command automatically:
1. Fetches posts from configured subreddits
2. Preprocesses and scores the posts
3. Generates the digest report using Claude Code

The report will be saved to `output/latest/report.md`.

## How It Works

1. **Fetch**: Python scripts pull posts from your configured sources (subreddits, hashtags, etc.)
2. **Preprocess**: Posts are scored by engagement, comments, recency, and relevance to your interests
3. **Summarize**: Claude Code reads the data and generates a personalized digest tailored to your topics

No separate API key needed - Claude Code handles the summarization directly.

### Technical Documentation

For detailed technical information about the system architecture, data flow, scoring algorithms, and Claude Code integration, see [docs/TECHNICAL.md](docs/TECHNICAL.md).

The technical documentation includes:
- System architecture and component diagrams
- Detailed flow diagrams for each phase (Fetch, Preprocess, Digest)
- Scoring algorithm explanations with visualizations
- Data structure specifications
- Claude Code integration patterns
- Performance considerations and error handling

## Usage

### Fetch Data

```bash
# Last 7 days (all subreddits)
make weekly

# Last 24 hours
make daily

# Last 30 days
make monthly

# Custom date range
make fetch START=2025-01-01T00:00:00Z END=2025-01-08T00:00:00Z
```

### Single Subreddit Mode

Fetch top posts from just one subreddit:

```bash
# Top 10 posts from r/ClaudeAI (last 7 days)
make single SUBREDDIT=ClaudeAI TOP=10

# Top 5 posts from r/LocalLLaMA
make single SUBREDDIT=LocalLLaMA TOP=5

# Combine with time windows
make weekly SUBREDDIT=MachineLearning TOP=15
make daily SUBREDDIT=OpenAI TOP=5
```

The `TOP` parameter controls how many posts to include (default: 50).

### Output Archives

Each run creates a timestamped directory to preserve history:

```
output/
├── 2025-01-15_103045_weekly_all/
│   ├── raw_posts.json
│   └── processed_posts.json
├── 2025-01-16_142230_single_ClaudeAI/
│   ├── raw_posts.json
│   └── processed_posts.json
└── latest -> 2025-01-16_142230_single_ClaudeAI/
```

The `latest` symlink always points to the most recent run, so you can always find the current data at `output/latest/processed_posts.json`.

### Generate Digest

The digest is **automatically generated** when you run `make weekly`, `make daily`, `make monthly`, or `make single`. The report will be saved to `output/latest/report.md`.

If you need to regenerate the report from existing data:

```bash
# Regenerate report from output/latest/processed_posts.json
make report
```

## Configuration

Edit `config.yaml` to customize for your topics of interest:

```yaml
# Subreddits to monitor (example: AI topics)
subreddits:
  - MachineLearning
  - LocalLLaMA
  - ChatGPT
  - ClaudeAI
  - OpenAI

# Your interests (for relevance scoring)
# Customize these to match your areas of interest
interests:
  - Large Language Models
  - AI agents
  - Open source AI tools
  - Practical experimentation
```

**Example configurations for other topics:**

**Technology/Programming:**
```yaml
subreddits:
  - programming
  - webdev
  - rust
  - golang
interests:
  - Systems programming
  - Web development frameworks
  - Performance optimization
```

**Science:**
```yaml
subreddits:
  - science
  - physics
  - chemistry
  - biology
interests:
  - Recent research findings
  - Experimental methods
  - Scientific breakthroughs
```

**Finance:**
```yaml
subreddits:
  - investing
  - stocks
  - cryptocurrency
  - personalfinance
interests:
  - Market analysis
  - Investment strategies
  - Financial planning
```

## Project Structure

```
curated-post-digest/
├── Makefile                    # make weekly, make daily, etc.
├── config.yaml                 # Subreddits and settings
├── requirements.txt            # Python dependencies
├── agents/
│   └── weekly_digest_agent.md  # Claude's instructions
├── scripts/
│   ├── fetch_reddit.py         # Reddit data collection
│   ├── preprocess.py           # Scoring and filtering
│   └── parse_time_window.py    # Time utilities
└── output/
    ├── latest/                 # Symlink to most recent run
    ├── 2025-01-15_weekly_all/  # Archived runs with timestamps
    │   ├── raw_posts.json      # Fetched data
    │   ├── processed_posts.json # Scored data (input for Claude)
    │   └── report.md           # Final digest
    └── ...
```

## Reddit API (Optional)

Works without credentials (rate-limited). For better limits, add to `config.yaml`:

```yaml
reddit:
  client_id: "your_id"
  client_secret: "your_secret"
```

Get credentials at: https://www.reddit.com/prefs/apps

## Roadmap

**Version 1.0 (Current):** Reddit support only
- ✅ Fetch posts from multiple subreddits
- ✅ Score and rank by engagement, recency, and relevance
- ✅ Generate personalized summaries for any topic
- ✅ Fully customizable interests and sources

**Future Versions:**
- 🔜 Twitter/X integration
- 🔜 LinkedIn posts and discussions
- 🔜 Cross-platform deduplication
- 🔜 Unified scoring across platforms
- 🔜 Additional platforms (Hacker News, GitHub Discussions, etc.)
- 🔜 Topic-specific agent templates

## Automation & Email Delivery

The system currently runs manually via `make` commands. For automated scheduling and email delivery options, see [docs/SCHEDULING_AND_EMAIL.md](docs/SCHEDULING_AND_EMAIL.md).

This guide covers:
- **Scheduling options**: LaunchAgent (recommended for Mac), Cron, or Python-based schedulers
- **Email delivery**: macOS `mail` command, SMTP (Gmail), or external services
- **Configuration examples**: Ready-to-use config snippets
- **Security best practices**: How to handle credentials safely

The documentation provides recommendations and examples without requiring implementation, so you can choose the approach that best fits your needs.

## License

MIT License - see LICENSE file

## Version History

**1.0.0** - 2025-12-30 - Initial release

* Reddit integration with multi-subreddit support
* Engagement-based scoring and ranking system
* Relevance scoring based on customizable interests
* Claude Code integration for digest generation
* Single subreddit mode for focused digests
* Timestamped output archives with symlink support
* Comprehensive configuration system
* Technical documentation and automation guides

## About

**Created by [Eric Blue](https://about.ericblue.com)**

Curated Post Digest is a local-first system that curates and summarizes discussions from multiple platforms on any topic you choose, using Claude Code. It provides a portable, tool-agnostic approach to staying informed about topics that matter to you.

This project addresses the challenge of information overload by providing intelligent curation and summarization of content from platforms like Reddit, with plans to expand to Twitter/X, LinkedIn, and other platforms.
