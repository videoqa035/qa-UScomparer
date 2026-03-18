# qa-UScomparer

> **Compare two Jira ticket definitions side-by-side** using the [Atlassian Remote MCP server](https://developer.atlassian.com/platform/remote-mcp-server/) — with an automatic REST API fallback.

[![CI](https://github.com/e.videoqa035/qa-UScomparer/actions/workflows/ci.yml/badge.svg)](https://github.com/e.videoqa035/qa-UScomparer/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## What it does

`qa-uscomparer` fetches two Jira issues and produces a structured field-by-field diff showing:

| Legend | Meaning |
|--------|---------|
| ✅ equal | Field has the same value in both tickets |
| ⚠️ different | Field exists in both but values differ |
| ◀ only in A | Field exists only in the first ticket |
| ▶ only in B | Field exists only in the second ticket |

Compares: Summary, Description, Issue Type, Status, Priority, Assignee, Reporter, Labels, Components, Fix Versions, Story Points, Epic Link, Sprint, Due Date, Environment, and more.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  CLI (Click)  qa-uscomparer TICKET_A TICKET_B [options] │
└──────────────────────┬──────────────────────────────────┘
                       │
              ┌────────▼─────────┐
              │   JiraFetcher    │  async, normalises ADF → plain text
              └──┬────────────┬──┘
    MCP first    │            │  REST API fallback
    ┌────────────▼──┐    ┌────▼─────────────────────┐
    │AtlassianMCP   │    │  httpx → Jira REST v3    │
    │Client (SSE)   │    │  /rest/api/3/issue/{key} │
    └───────────────┘    └──────────────────────────┘
                       │
              ┌────────▼─────────┐
              │   Comparator     │  field diff → ComparisonResult
              └────────┬─────────┘
                       │
              ┌────────▼─────────┐
              │   Display        │  table / JSON / Markdown
              └──────────────────┘
```

---

## Requirements

- Python 3.11 or newer
- An Atlassian account with API access
  - **Jira Cloud** → [Atlassian API Token](https://id.atlassian.com/manage-profile/security/api-tokens) + your account email
  - **Jira Data Center / Server** → [Personal Access Token (PAT)](https://confluence.atlassian.com/enterprise/using-personal-access-tokens-1026032365.html) (no email needed)

---

## Installation

```bash
# 1. Clone
git clone https://github.com/e.videoqa035/qa-UScomparer.git
cd qa-UScomparer

# 2. Create a virtual environment (recommended)
python -m venv .venv && source .venv/bin/activate

# 3. Install
pip install -e .
```

---

## Configuration

Copy `.env.example` → `.env` and fill in your credentials:

```bash
cp .env.example .env
```

```dotenv
# Jira Cloud
ATLASSIAN_TOKEN=your_api_token_here
ATLASSIAN_EMAIL=your@email.com
JIRA_BASE_URL=https://your-org.atlassian.net

# Jira DC / Server (Bearer PAT, no email)
# ATLASSIAN_TOKEN=your_pat_here
# JIRA_BASE_URL=https://jira.yourcompany.com
```

> **Security note** – `.env` is in `.gitignore`. Never commit real credentials.

---

## Usage

### Basic comparison (interactive token prompt)

```bash
qa-uscomparer PROJ-101 PROJ-102
```

### With credentials from environment / .env

```bash
source .env
qa-uscomparer PROJ-101 PROJ-102
```

### Show only differences

```bash
qa-uscomparer PROJ-101 PROJ-102 --only-diff
```

### JSON output (machine-readable / CI)

```bash
qa-uscomparer PROJ-101 PROJ-102 --output json
```

### Markdown output (paste into GitHub / Jira comments)

```bash
qa-uscomparer PROJ-101 PROJ-102 --output markdown
```

### Compare a specific set of fields

```bash
qa-uscomparer PROJ-101 PROJ-102 --fields summary,status,priority,assignee
```

### All options

```
Usage: qa-uscomparer [OPTIONS] TICKET_A TICKET_B

  Compare the definitions of two Jira tickets using the Atlassian MCP server.

Options:
  --token TEXT               Atlassian Personal Access Token
  --email TEXT               Atlassian account email (Jira Cloud only)
  --base-url TEXT            Atlassian Remote MCP base URL  [default: https://mcp.atlassian.com]
  --jira-url TEXT            Jira instance base URL (REST API fallback)
  --output [table|json|markdown]  Output format  [default: table]
  --fields FIELD1,FIELD2,…  Comma-separated fields to compare
  --only-diff               Show only fields that differ
  -v, --verbose             Enable debug logging
  -h, --help                Show this message and exit.
  --version                 Show version and exit.
```

---

## Development

```bash
# Install dev dependencies
make dev

# Run tests
make test

# Run tests with HTML coverage report
make test-cov

# Lint + type check
make lint

# Auto-format
make format
```

---

## How token authentication works

| Jira edition | Mechanism | `--email` required? |
|--------------|-----------|---------------------|
| **Cloud** | `Authorization: Basic base64(email:token)` | ✅ Yes |
| **Data Center / Server** | `Authorization: Bearer <PAT>` | ❌ No |

The tool auto-selects the right scheme based on whether `--email` / `ATLASSIAN_EMAIL` is set.

---

## Troubleshooting

| Error | Likely cause | Fix |
|-------|-------------|-----|
| `Authentication failed (401)` | Wrong token/email | Check `.env`, regenerate token |
| `Issue 'PROJ-X' not found (404)` | Wrong key or no permission | Verify key and board access |
| `MCP connection failed` | Network / firewall | The tool auto-falls back to REST API if `JIRA_BASE_URL` is set |
| `JIRA_BASE_URL not set` | MCP failed and no fallback | Set `JIRA_BASE_URL` in `.env` |

---

## License

[MIT](LICENSE) © e.videoqa035
