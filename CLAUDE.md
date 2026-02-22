# CLAUDE.md

This file provides guidance for AI assistants (Claude and others) working in this repository.

## Project Overview

**Ambrotos** is a shared team calendar web application built with Python/Flask. Team members log in and mark dates when they are unavailable. A natural-language Danish chat interface parses date expressions and automatically updates the calendar. Users can also create group events with attendance tracking and comments.

**Key features:**
- 13 pre-created users; admin users can create/edit/delete users via the admin panel
- Monthly/3-month/12-month calendar view showing each member's unavailable dates (colour-coded avatars per user)
- Chat interface accepts natural-language Danish input and adds/removes unavailable dates using local date parsing (no external AI)
- Danish public holidays displayed on the calendar
- Click any calendar date to see who is unavailable; add/delete your own dates directly from the modal
- Group events with title, description, attendance view, and threaded comments
- Admin panel for user management (`/admin`)
- iCalendar export at `/calendar.ics`
- Data backup/restore via a local JSON file and optional FTP upload

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, Flask 3, Flask-SQLAlchemy, Flask-Login |
| Database | SQLite (local dev) or PostgreSQL (production via `DATABASE_URL`) |
| Date parsing | `dateparser` library with custom Danish regex patterns |
| Frontend | Vanilla JS, FullCalendar v6 (CDN), custom CSS |
| Auth | Werkzeug password hashing |
| Production | Gunicorn, Render (or any WSGI host) |

## Repository Structure

```
ambrotos/
├── app.py               # Flask application, routes, DB models, date parsing
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variable template
├── .gitignore
├── CLAUDE.md
├── data/
│   └── calendar_backup.json  # Git-tracked backup (auto-updated on every write)
├── templates/
│   ├── base.html        # HTML shell (head, flash messages, script block)
│   ├── login.html       # Login form
│   ├── index.html       # Main page (calendar + sidebar with legend and upcoming events)
│   └── admin.html       # Admin panel (user management)
└── static/
    ├── css/style.css    # All styles — variables, layout, components
    └── js/app.js        # FullCalendar init, modal logic, group events, API calls
```

## Development Setup

### Prerequisites
- Python 3.11+

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
# Edit .env as needed (SECRET_KEY and FTP vars; ANTHROPIC_API_KEY is unused)

# Run the app (creates DB and seeds 13 users on first start)
python app.py
```

Open http://localhost:5000 in your browser. Log in with any of the 13 usernames and the seed password (`123` for a fresh install with no backup).

### Users

The 13 pre-seeded users are:
`Anders Badsberg`, `Rasmus Bjerg`, `Mikael`, `Martin Bach`, `Anders Busch`, `Kristian`, `Rasmus Borup`, `Kasper`, `Bjarne`, `Jakob`, `Mikkel`, `Johan`, `Martin Kjær`

Default seed password: `123` (existing deployments restore passwords from backup)

Admin users can manage all users at `/admin`.

## Key Files and Conventions

### `app.py`

- **Models**:
  - `User` (id, username, password_hash, color, is_admin)
  - `UnavailableDate` (user_id, date, created_at) — unique constraint per user/date
  - `GroupEvent` (id, title, description, date, end_date, created_by, created_at) — supports multi-day events
  - `EventComment` (event_id, user_id, text, is_hidden, created_at)
- **`init_db()`**: Called on startup; creates tables, restores from backup if available, seeds default users if DB is empty.
- **`parse_dates_from_message(message)`**: Extracts `date` objects from Danish natural-language strings using regex patterns and `dateparser`. Supports patterns like `"alle mandage i maj"`, `"fra 1. til 5. april"`, and arbitrary day lists.
- **`write_backup()`**: Serialises all DB data to `data/calendar_backup.json` and optionally pushes to FTP in a background thread. Called after every write operation.
- **`restore_from_backup()`**: On startup, downloads backup from FTP if no local file exists, then repopulates empty tables from JSON.

#### Routes

| Method | Path | Description |
|---|---|---|
| GET | `/` | Main calendar page (login required) |
| GET/POST | `/login` | Login form |
| GET | `/logout` | Logout |
| GET | `/calendar.ics` | iCalendar export of all events |
| GET | `/admin` | Admin panel (admin users only) |
| GET | `/api/events` | All unavailable dates + holidays + group events (FullCalendar format) |
| POST | `/api/chat` | Parse Danish date message; add/remove unavailable dates for current user |
| POST | `/api/unavailable/toggle` | Toggle a single date as unavailable for current user |
| GET | `/api/group-events` | Upcoming group events (next 6 months) |
| POST | `/api/group-events` | Create a group event (supports end_date for multi-day) |
| GET | `/api/group-events/<id>` | Event detail with attendance and comments |
| PUT | `/api/group-events/<id>` | Edit event (creator + admin) |
| DELETE | `/api/group-events/<id>` | Delete event (creator + admin) |
| POST | `/api/group-events/<id>/comments` | Add comment to event |
| DELETE | `/api/group-events/<id>/comments/<cid>` | Delete own comment |
| PUT | `/api/group-events/<id>/comments/<cid>/hide` | Hide/unhide comment (admin only) |
| GET | `/api/admin/users` | List all users (admin only) |
| POST | `/api/admin/users` | Create user (admin only) |
| PUT | `/api/admin/users/<id>` | Update user (admin only) |
| DELETE | `/api/admin/users/<id>` | Delete user (admin only) |

#### `POST /api/chat` behaviour

Accepts `{ message: string }`. Parses the Danish text locally:
- If the message starts with `slet` or `fjern`, matching dates are deleted.
- Otherwise, matching dates are added.
- Returns `{ response, added, deleted, already_exists, not_found }`.
- No external AI is called; date parsing uses `parse_dates_from_message()`.

### `static/js/app.js`

- **`initCalendar()`**: Sets up FullCalendar with Danish locale, month/3-month/12-month views. Fetches events via `fetchEvents()`, caches them in `allEvents`.
- **`renderUnavailCircles()`**: Injects colour-coded avatar circles into calendar day cells for unavailable members (hidden from FullCalendar's native event bars).
- **`showDateModal(dateStr)`**: Filters `allEvents` locally to show who is unavailable on a given date. Provides delete/add buttons for the current user.
- **`showEventDetailModal(eventId)`**: Fetches group event details and displays attendance (attending/not attending) and comments.
- **`toggleEventMode()`**: Enables "event creation mode" — clicking a day opens the event create modal instead of the date detail modal.
- All user-provided strings run through `escapeHtml()` before insertion into the DOM.

### `static/css/style.css`

Uses CSS custom properties (`--primary`, `--bg`, `--card`, etc.) defined in `:root`. Mobile-responsive at 768px breakpoint — the sidebar stacks below the calendar on narrow screens.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | No | Flask session secret (use a long random string in production) |
| `DATABASE_URL` | No | PostgreSQL connection URL (defaults to SQLite `instance/calendar.db`) |
| `FTP_HOST` | No | FTP server hostname for backup (e.g., `ftp.jrgrafisk.dk`) |
| `FTP_USER` | No | FTP username |
| `FTP_PASS` | No | FTP password |
| `FTP_PATH` | No | Remote directory for backup (default: `/ambrotos`) |

> **Note**: `ANTHROPIC_API_KEY` appears in `.env.example` as a historical artefact. The application no longer calls the Anthropic API.

## Git Workflow

### Branches
- `main` — stable code
- `claude/<description>-<session-id>` — AI-assisted feature branches

### Commit Messages
```
feat: add group events with attendance and comments
fix: prevent duplicate date insertion in chat handler
chore: update CLAUDE.md with current application state
```

## Testing

No automated test suite yet. Manual testing checklist:

- [ ] Log in as several users, add different dates, verify calendar shows all entries with correct colour-coded circles
- [ ] Type date expressions in various Danish formats: `"15. marts"`, `"d. 5/4"`, `"fra 1. til 3. juni"`, `"alle mandage i maj"`
- [ ] Delete a date via chat (`slet 15. marts`) and via the modal Slet button
- [ ] Click a date with multiple unavailable members — verify modal lists all
- [ ] Click a date you have no entry for — verify "Markér mig" button appears and works
- [ ] Create a group event using event-creation mode; verify it appears on calendar and in upcoming events list
- [ ] Open a group event modal, add a comment, verify it appears; delete the event as creator
- [ ] Log in as admin, open `/admin`, create/edit/delete a user
- [ ] Download `/calendar.ics` and import into a calendar application
- [ ] Resize browser to < 768px — verify sidebar stacks below calendar

## Common Pitfalls

- **DB path**: Flask-SQLAlchemy with SQLite creates the file in an `instance/` subdirectory by default when using `sqlite:///filename.db`. This directory is git-ignored.
- **DATABASE_URL on Render**: Render provides a `postgres://` URL; `app.py` automatically rewrites it to `postgresql://` for SQLAlchemy compatibility.
- **Backup restore on redeploy**: `restore_from_backup()` only populates *empty* tables, so a partial DB will not be overwritten. Drop and recreate the DB if data is inconsistent.
- **FTP upload is async**: `push_backup_to_ftp()` spawns a daemon thread; failures are logged to stdout but do not affect the HTTP response.
- **FullCalendar locale**: The Danish locale is loaded via the `locales-all.global.min.js` CDN bundle. If offline, the calendar falls back to English.

## Updating This File

Keep CLAUDE.md current when:
- New routes or models are added to `app.py`
- The date parsing logic or supported patterns change
- New environment variables are introduced
- Significant UI or workflow changes are made
