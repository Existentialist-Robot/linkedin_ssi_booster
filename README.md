# LinkedIn SSI Booster — Buffer API Integration

Automates LinkedIn post generation and scheduling via Claude AI + Buffer API
to systematically grow your Social Selling Index (SSI) score.

## How it works

1. **Content calendar** — 4 weeks of topics mapped to your 4 SSI components
2. **Claude AI** — generates authentic LinkedIn posts in your voice
3. **Buffer API** — schedules posts to LinkedIn at Tue/Wed/Fri 4 PM EST
4. **Content curator** — fetches AI/GovTech news and creates ideas for curation posts
5. **SSI tracker** — weekly report with specific actions per component

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env and add your keys:
#   BUFFER_API_KEY  → https://publish.buffer.com/settings/api
#   ANTHROPIC_API_KEY → https://console.anthropic.com
```

## Usage

```bash
# Generate + preview week 1 posts (dry run — no API calls to Buffer)
python main.py --generate --week 1 --dry-run

# Generate + schedule week 1 posts to Buffer
python main.py --generate --schedule --week 1

# Curate AI news and push as Buffer ideas (for review before publishing)
python main.py --curate --dry-run
python main.py --curate

# Print weekly SSI action report
python main.py --report
```

## SSI Component Mapping

| Component            | Current | Target | Strategy |
|----------------------|---------|--------|----------|
| Establish brand      | 10.46   | 25     | 3x/week posting via Buffer |
| Find right people    | 9.47    | 20     | Connect with commenters, join groups |
| Engage with insights | 11.00   | 25     | Curated posts + daily commenting |
| Build relationships  | 11.85   | 25     | Reply to all comments, DM connections |
| **Total**            | **43**  | **95** | |

## File Structure

```
linkedin_ssi_booster/
├── main.py                    # CLI entry point
├── content_calendar.py        # 4-week topic plan
├── scheduler.py               # Buffer post scheduling logic
├── requirements.txt
├── .env.example
└── services/
    ├── buffer_service.py      # Buffer GraphQL API client
    ├── claude_service.py      # Anthropic API — post generation
    ├── content_curator.py     # RSS feed scraper + summariser
    └── ssi_tracker.py         # SSI report + action items
```

## Get your API keys

- **Buffer API key**: https://publish.buffer.com/settings/api → Generate API Key
- **Anthropic API key**: https://console.anthropic.com → API Keys
- **Track your SSI**: https://linkedin.com/sales/ssi
