# CLAUDE.md

This file provides guidance for AI assistants (Claude and others) working in this repository.

## Project Overview

**Ambrotos** is a shared team calendar web application built with Python/Flask and powered by the Claude AI API. Team members log in and mark dates when they are unavailable. An AI chat interface accepts natural-language Danish input and automatically updates the calendar.

**Key features:**
- 14 pre-created users, all sharing the password `kodeordetersvært`
- Monthly/weekly calendar view showing each member's unavailable dates (color-coded per user)
- AI chat powered by `claude-opus-4-6` that parses Danish date expressions and adds/removes dates
- Click any calendar date or event to see who is unavailable; add/delete your own dates directly from the modal
- Delete a date by typing `slet <dato>` in the chat

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, Flask 3, Flask-SQLAlchemy, Flask-Login |
| Database | SQLite (file: `instance/calendar.db`) |
| AI | Anthropic Python SDK (`claude-opus-4-6`) |
| Frontend | Vanilla JS, FullCalendar v6 (CDN), custom CSS |
| Auth | Werkzeug password hashing |

## Repository Structure

```
ambrotos/
├── app.py               # Flask application, routes, DB models, AI chat endpoint
├── requirements.txt     # Python dependencies
├── .env.example         # Required environment variables (copy to .env)
├── .gitignore
├── CLAUDE.md
├── templates/
│   ├── base.html        # HTML shell (head, flash messages, script block)
│   ├── login.html       # Login form
│   └── index.html       # Main page (calendar + sidebar with legend + chat)
└── static/
    ├── css/style.css    # All styles — variables, layout, components
    └── js/app.js        # FullCalendar init, chat logic, modal, API calls
```

## Development Setup

### Prerequisites
- Python 3.11+
- An Anthropic API key (get one at https://console.anthropic.com)

### Installation

```bash
# Clone and enter the repo
cd ambrotos

# Create a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY=<your key>

# Run the app (creates DB and seeds 14 users on first start)
python app.py
```

Open http://localhost:5000 in your browser. Log in with any of the 14 usernames (e.g. `Anders`) and password `kodeordetersvært`.

### Users

The 14 pre-seeded users are:
`Anders`, `Birthe`, `Christian`, `Dorte`, `Erik`, `Freja`, `Gunnar`, `Helle`, `Ivan`, `Jette`, `Klaus`, `Lene`, `Mikkel`, `Nina`

Password for all: `kodeordetersvært`

## Key Files and Conventions

### `app.py`

- **Models**: `User` (id, username, password_hash, color) and `UnavailableDate` (user_id, date). A unique constraint prevents duplicate entries per user/date.
- **`init_db()`**: Called on startup; creates tables and seeds users if the DB is empty.
- **`GET /api/events`**: Returns all unavailable dates as FullCalendar-compatible event objects.
- **`POST /api/chat`**: Accepts `{ message: string }`, calls Claude, parses JSON response, writes to DB. Returns `{ response, added, deleted, already_exists, not_found }`.
- The Claude system prompt instructs the model to return **only valid JSON** — no markdown, no prose. The endpoint strips ` ``` ` fences defensively.
- Model used: `claude-opus-4-6` (no thinking, 1024 max tokens — date parsing is a simple structured extraction task).

### `static/js/app.js`

- **`initCalendar()`**: Sets up FullCalendar with Danish locale, fetches events via `fetchEvents()`, caches them in `allEvents`.
- **`showDateModal(dateStr)`**: Filters `allEvents` locally (no extra API call) to show who is unavailable on a given date. Provides delete/add buttons for the current user.
- **`sendChatMessage(text)`**: POSTs to `/api/chat`, shows typing indicator, displays AI response as a chat bubble, calls `refreshCalendar()` if any dates changed.
- All user-provided strings run through `escapeHtml()` before insertion into the DOM.

### `static/css/style.css`

Uses CSS custom properties (`--primary`, `--bg`, `--card`, etc.) defined in `:root`. Mobile-responsive at 768px breakpoint — the sidebar stacks below the calendar on narrow screens.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | **Yes** | Anthropic API key |
| `SECRET_KEY` | No | Flask session secret (use a long random string in production) |
| `FTP_HOST` | No | FTP server hostname (e.g., `ftp.jrgrafisk.dk`) |
| `FTP_USER` | No | FTP username |
| `FTP_PASS` | No | FTP password |
| `FTP_PATH` | No | Remote directory for backup (default: `/ambrotos`) |

## Git Workflow

### Branches
- `main` — stable code
- `claude/<description>-<session-id>` — AI-assisted feature branches

### Commit Messages
```
feat: add weekly view toggle to calendar
fix: prevent duplicate date insertion in chat handler
chore: update CLAUDE.md with user list
```

## Testing

No automated test suite yet. Manual testing checklist:

- [ ] Log in as each of several users, add different dates, verify calendar shows all entries with correct colors
- [ ] Type date expressions in various Danish formats: `"15. marts"`, `"d. 5/4"`, `"fra 1. til 3. juni"`, `"alle mandage i maj"`
- [ ] Delete a date via chat (`slet 15. marts`) and via the modal Slet button
- [ ] Click a date with multiple unavailable members — verify modal lists all
- [ ] Click a date you have no entry for — verify "Markér mig" button appears and works
- [ ] Resize browser to < 768px — verify sidebar stacks below calendar

## Common Pitfalls

- **DB path**: Flask-SQLAlchemy with SQLite creates the file in an `instance/` subdirectory by default when using `sqlite:///filename.db`. This directory is git-ignored.
- **Special characters in password**: `kodeordetersvært` contains `æ`. Werkzeug's `generate_password_hash` / `check_password_hash` handle UTF-8 correctly; no issues expected.
- **Claude JSON output**: On rare occasions the model may wrap its response in markdown code fences. `app.py` strips these defensively. If the model refuses or returns non-JSON, the chat endpoint falls back to a Danish error message.
- **FullCalendar locale**: The Danish locale is loaded via the `locales-all.global.min.js` CDN bundle. If offline, the calendar falls back to English.

## Updating This File

Keep CLAUDE.md current when:
- New routes or models are added to `app.py`
- The Claude model or prompt changes
- New environment variables are introduced
- Significant UI or workflow changes are made
