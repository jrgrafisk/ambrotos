import os
import re
import json
import ftplib
import io
import threading
import secrets
import calendar as cal_module
from datetime import datetime, date, timedelta

from sqlalchemy import text as sa_text, inspect as sa_inspect

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import dateparser
from dateparser.search import search_dates
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'ambrotos-dev-secret-change-in-production')

# Support both PostgreSQL (Render) and SQLite (local dev).
# Render sets DATABASE_URL with the postgres:// scheme; SQLAlchemy requires postgresql://.
_db_url = os.environ.get('DATABASE_URL', 'sqlite:///calendar.db')
if _db_url.startswith('postgres://'):
    _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = _db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Log venligst ind for at fortsætte.'

MEMBER_NAMES = [
    'Anders Badsberg', 'Rasmus Bjerg', 'Mikael', 'Martin Bach',
    'Anders Busch', 'Kristian', 'Rasmus Borup', 'Kasper',
    'Bjarne', 'Jakob', 'Mikkel', 'Johan', 'Martin Kjær',
]

ADMIN_USERS = {'Kasper'}

MEMBER_COLORS = [
    '#e53935', '#1e88e5', '#43a047', '#fb8c00', '#8e24aa',
    '#00acc1', '#f4511e', '#3949ab', '#00897b', '#c0ca33',
    '#ffb300', '#d81b60', '#6d4c41',
]


# ── Danish date helpers ─────────────────────────────────────────────────────────

DANISH_MONTHS = {
    'januar': 1, 'jan': 1,
    'februar': 2, 'feb': 2,
    'marts': 3, 'mar': 3,
    'april': 4, 'apr': 4,
    'maj': 5,
    'juni': 6, 'jun': 6,
    'juli': 7, 'jul': 7,
    'august': 8, 'aug': 8,
    'september': 9, 'sep': 9,
    'oktober': 10, 'okt': 10,
    'november': 11, 'nov': 11,
    'december': 12, 'dec': 12,
}

DANISH_MONTH_NAMES = {
    1: 'januar', 2: 'februar', 3: 'marts', 4: 'april',
    5: 'maj', 6: 'juni', 7: 'juli', 8: 'august',
    9: 'september', 10: 'oktober', 11: 'november', 12: 'december',
}

DANISH_WEEKDAYS = {
    'mandag': 0, 'tirsdag': 1, 'onsdag': 2, 'torsdag': 3,
    'fredag': 4, 'lørdag': 5, 'lordag': 5, 'søndag': 6, 'sondag': 6,
}


def calculate_easter(year: int) -> date:
    """Calculate Easter Sunday using the Meeus/Jones/Butcher algorithm."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


HOLIDAY_DESCRIPTIONS = {
    'Nytårsdag':            'Det nye år begynder',
    'Skærtorsdag':          'Jesu sidste nadver med disciplene',
    'Langfredag':           'Mindes Jesu korsfæstelse og død',
    'Påskedag':             'Fejrer Jesu opstandelse fra de døde',
    '2. påskedag':          'Anden dag af påskefejringen',
    'Kristi Himmelfartsdag':'Jesus steg op til Himmelen, 39 dage efter påske',
    'Pinsedag':             'Helligåndens komme over apostlene, 50 dage efter påske',
    '2. pinsedag':          'Anden dag af pinsefejringen',
    'Grundlovsdag':         'Grundloven underskrevet 5. juni 1849',
    'Juleaften':            'Traditionel julefejring og familiemiddag',
    '1. juledag':           'Fejrer Jesu fødsel',
    '2. juledag':           'Anden dag af julefejringen',
}


def get_danish_holidays(year: int) -> list:
    """Return list of (date, name, description) tuples for Danish public holidays."""
    easter = calculate_easter(year)
    holidays = [
        (date(year, 1, 1),               'Nytårsdag'),
        (easter - timedelta(days=3),      'Skærtorsdag'),
        (easter - timedelta(days=2),      'Langfredag'),
        (easter,                          'Påskedag'),
        (easter + timedelta(days=1),      '2. påskedag'),
        (easter + timedelta(days=39),     'Kristi Himmelfartsdag'),
        (easter + timedelta(days=49),     'Pinsedag'),
        (easter + timedelta(days=50),     '2. pinsedag'),
        (date(year, 6, 5),               'Grundlovsdag'),
        (date(year, 12, 24),             'Juleaften'),
        (date(year, 12, 25),             '1. juledag'),
        (date(year, 12, 26),             '2. juledag'),
    ]
    return [(d, name, HOLIDAY_DESCRIPTIONS.get(name, '')) for d, name in sorted(holidays, key=lambda x: x[0])]


def parse_dates_from_message(message: str) -> list:
    """Extract date objects from a Danish natural-language message."""
    today = date.today()
    msg = message.lower().strip()

    # Pattern 1: "alle <ugedag>e i <måned> [år]"
    m = re.search(r'alle\s+(\w+)\s+i\s+(\w+)(?:\s+(\d{4}))?', msg)
    if m:
        wday_raw = m.group(1)
        wday = DANISH_WEEKDAYS.get(wday_raw) or DANISH_WEEKDAYS.get(wday_raw.rstrip('e'))
        month = DANISH_MONTHS.get(m.group(2))
        year = int(m.group(3)) if m.group(3) else today.year
        if wday is not None and month:
            _, n = cal_module.monthrange(year, month)
            return [date(year, month, d) for d in range(1, n + 1)
                    if date(year, month, d).weekday() == wday]

    # Pattern 2: "fra <d>. [m] til <d>. <m> [år]"
    m = re.search(r'fra\s+(\d+)\.?\s*(\w+)?\s+til\s+(\d+)\.?\s*(\w+)(?:\s+(\d{4}))?', msg)
    if m:
        start_d = int(m.group(1))
        start_mn = m.group(2)
        end_d = int(m.group(3))
        end_mn = m.group(4)
        year = int(m.group(5)) if m.group(5) else today.year
        end_month = DANISH_MONTHS.get(end_mn)
        start_month = DANISH_MONTHS.get(start_mn) if start_mn else end_month
        if start_month and end_month:
            start = date(year, start_month, start_d)
            end = date(year, end_month, end_d)
            cur, result = start, []
            while cur <= end:
                result.append(cur)
                cur += timedelta(days=1)
            return result

    # Pattern 3: list of days sharing one month — e.g. "5., 12. og 19. januar"
    months_in_msg = set()
    for name, num in DANISH_MONTHS.items():
        if re.search(r'\b' + re.escape(name) + r'\b', msg):
            months_in_msg.add(num)

    if len(months_in_msg) == 1:
        month = next(iter(months_in_msg))
        year_m = re.search(r'\b(\d{4})\b', msg)
        year = int(year_m.group(1)) if year_m else today.year
        day_nums = [int(d) for d in re.findall(r'\b(\d{1,2})\.', msg) if int(d) <= 31]
        result = []
        for day in day_nums:
            try:
                d = date(year, month, day)
                if d < today and not year_m:
                    d = date(year + 1, month, day)
                if d not in result:
                    result.append(d)
            except ValueError:
                pass
        if result:
            return sorted(result)

    # Fallback: dateparser.search.search_dates
    settings = {
        'LANGUAGES': ['da'],
        'PREFER_DATES_FROM': 'future',
        'RELATIVE_BASE': datetime.combine(today, datetime.min.time()),
    }
    found = search_dates(message, languages=['da'], settings=settings)
    if found:
        seen, result = set(), []
        for _, dt in found:
            d = dt.date()
            if d not in seen:
                seen.add(d)
                result.append(d)
        return result

    return []


def format_dates_danish(date_strings: list) -> str:
    """Format a list of ISO date strings into a readable Danish string."""
    if not date_strings:
        return ""
    dates_obj = [date.fromisoformat(s) for s in date_strings]
    formatted = [f"{d.day}. {DANISH_MONTH_NAMES[d.month]}" for d in dates_obj]
    if len(formatted) == 1:
        return formatted[0]
    return ", ".join(formatted[:-1]) + " og " + formatted[-1]


# ── Models ─────────────────────────────────────────────────────────────────────

class Team(db.Model):
    __tablename__ = 'teams'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    description = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class UserTeam(db.Model):
    __tablename__ = 'user_teams'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id', ondelete='CASCADE'), primary_key=True)
    is_team_admin = db.Column(db.Boolean, nullable=False, default=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    color = db.Column(db.String(7), nullable=False, default='#1e88e5')
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    unavailable_dates = db.relationship(
        'UnavailableDate', backref='user', lazy=True, cascade='all, delete-orphan'
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_team_admin_for(self, team_id: int) -> bool:
        """Returnerer True hvis brugeren er team-admin ELLER global super-admin."""
        if self.is_admin:
            return True
        ut = UserTeam.query.filter_by(user_id=self.id, team_id=team_id).first()
        return ut.is_team_admin if ut else False


class UnavailableDate(db.Model):
    __tablename__ = 'unavailable_dates'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)
    date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'date', name='unique_user_date'),
    )


class GroupEvent(db.Model):
    __tablename__ = 'group_events'
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    creator = db.relationship('User', backref='created_events')
    comments = db.relationship(
        'EventComment', backref='event', lazy=True,
        cascade='all, delete-orphan', order_by='EventComment.created_at',
    )


class EventComment(db.Model):
    __tablename__ = 'event_comments'
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('group_events.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    is_hidden = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    author = db.relationship('User')


class PasswordResetToken(db.Model):
    __tablename__ = 'password_reset_tokens'
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User')


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ── Data backup / restore / ICS ────────────────────────────────────────────────

BACKUP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'calendar_backup.json')


def write_backup():
    """Persist current calendar data to a git-tracked JSON file (version 2 format).
    Called after every write so a redeploy always finds the latest state."""
    try:
        os.makedirs(os.path.dirname(BACKUP_FILE), exist_ok=True)
        payload = {
            'version': 2,
            'exported_at': datetime.utcnow().isoformat(),
            'teams': [
                {'id': t.id, 'name': t.name, 'description': t.description or ''}
                for t in Team.query.order_by(Team.id).all()
            ],
            'user_teams': [
                {'user_id': ut.user_id, 'team_id': ut.team_id, 'is_team_admin': ut.is_team_admin}
                for ut in UserTeam.query.all()
            ],
            'users': [
                {
                    'id': u.id,
                    'username': u.username,
                    'password_hash': u.password_hash,
                    'color': u.color,
                    'is_admin': u.is_admin,
                }
                for u in User.query.order_by(User.id).all()
            ],
            'unavailable_dates': [
                {'user_id': ud.user_id, 'team_id': ud.team_id, 'date': ud.date.isoformat()}
                for ud in UnavailableDate.query.all()
            ],
            'group_events': [
                {
                    'id': e.id,
                    'team_id': e.team_id,
                    'title': e.title,
                    'description': e.description or '',
                    'date': e.date.isoformat(),
                    'end_date': e.end_date.isoformat() if e.end_date else None,
                    'created_by': e.created_by,
                    'created_at': e.created_at.isoformat(),
                }
                for e in GroupEvent.query.order_by(GroupEvent.id).all()
            ],
            'event_comments': [
                {
                    'event_id': c.event_id,
                    'user_id': c.user_id,
                    'text': c.text,
                    'is_hidden': c.is_hidden,
                    'created_at': c.created_at.isoformat(),
                }
                for c in EventComment.query.order_by(EventComment.id).all()
            ],
        }
        with open(BACKUP_FILE, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        push_backup_to_ftp()
    except Exception as exc:
        print(f'⚠ Backup write failed: {exc}')


def _ftp_ensure_dir(ftp, path):
    """Navigate into the given directory on the FTP server, creating it if needed."""
    dirs = [d for d in path.strip('/').split('/') if d]
    for d in dirs:
        try:
            ftp.cwd(d)
        except ftplib.error_perm:
            ftp.mkd(d)
            ftp.cwd(d)


def _push_backup_to_ftp():
    """Upload data/calendar_backup.json to FTP server.
    Runs in a background daemon thread — never blocks a request."""
    host = os.environ.get('FTP_HOST', '')
    user = os.environ.get('FTP_USER', '')
    passwd = os.environ.get('FTP_PASS', '')
    remote_dir = os.environ.get('FTP_PATH', '/ambrotos')
    if not host or not user or not passwd:
        return
    try:
        with open(BACKUP_FILE, 'rb') as f:
            file_data = f.read()

        ftp = ftplib.FTP_TLS(host, timeout=30)
        ftp.login(user, passwd)
        ftp.prot_p()  # Secure data connection

        _ftp_ensure_dir(ftp, remote_dir)
        ftp.storbinary('STOR calendar_backup.json', io.BytesIO(file_data))
        ftp.quit()
        print(f'✓ Backup pushed til FTP ({host}:{remote_dir}/calendar_backup.json)')
    except Exception as exc:
        print(f'⚠ FTP upload failed ({host}:{remote_dir}): {exc}')


def push_backup_to_ftp():
    """Non-blocking wrapper — spawns a daemon thread."""
    if os.environ.get('FTP_HOST') and os.environ.get('FTP_USER') and os.environ.get('FTP_PASS'):
        threading.Thread(target=_push_backup_to_ftp, daemon=True).start()


def _download_backup_from_ftp():
    """Download calendar_backup.json from FTP server into local data/ directory.
    Called once at startup if no local backup file exists."""
    host = os.environ.get('FTP_HOST', '')
    user = os.environ.get('FTP_USER', '')
    passwd = os.environ.get('FTP_PASS', '')
    remote_dir = os.environ.get('FTP_PATH', '/ambrotos')
    if not host or not user or not passwd:
        return
    try:
        ftp = ftplib.FTP_TLS(host, timeout=30)
        ftp.login(user, passwd)
        ftp.prot_p()
        ftp.cwd(remote_dir)

        os.makedirs(os.path.dirname(BACKUP_FILE), exist_ok=True)
        with open(BACKUP_FILE, 'wb') as f:
            ftp.retrbinary('RETR calendar_backup.json', f.write)
        ftp.quit()
        print(f'✓ Backup hentet fra FTP ({host}{remote_dir}/calendar_backup.json)')
    except Exception as exc:
        print(f'⚠ FTP download fejlede ({host}:{remote_dir}): {exc}')


def _try_use_best_backup():
    """Always try FTP. If both local and FTP backups exist, use the newer one."""
    host = os.environ.get('FTP_HOST', '')
    user = os.environ.get('FTP_USER', '')
    passwd = os.environ.get('FTP_PASS', '')
    if not host or not user or not passwd:
        print('ℹ FTP ikke konfigureret — bruger kun lokal backup')
        return

    remote_dir = os.environ.get('FTP_PATH', '/ambrotos')
    print(f'ℹ Forsøger FTP backup fra {host}:{remote_dir}/calendar_backup.json')

    # Read local backup timestamp if available
    local_ts = None
    if os.path.exists(BACKUP_FILE):
        try:
            with open(BACKUP_FILE, encoding='utf-8') as f:
                local_data = json.load(f)
            local_ts = local_data.get('exported_at', '')
        except Exception:
            pass

    # Download FTP version to a temp location
    ftp_file = BACKUP_FILE + '.ftp_tmp'
    try:
        ftp = ftplib.FTP_TLS(host, timeout=30)
        ftp.login(user, passwd)
        ftp.prot_p()
        ftp.cwd(remote_dir)
        os.makedirs(os.path.dirname(BACKUP_FILE), exist_ok=True)
        with open(ftp_file, 'wb') as f:
            ftp.retrbinary('RETR calendar_backup.json', f.write)
        ftp.quit()
    except Exception as exc:
        print(f'⚠ FTP download fejlede ({host}:{remote_dir}): {exc}')
        # Clean up temp file if partial
        if os.path.exists(ftp_file):
            os.remove(ftp_file)
        return

    # Compare timestamps — use FTP version if newer
    try:
        with open(ftp_file, encoding='utf-8') as f:
            ftp_data = json.load(f)
        ftp_ts = ftp_data.get('exported_at', '')

        if not local_ts or ftp_ts > local_ts:
            # FTP is newer (or no local) — replace local
            os.replace(ftp_file, BACKUP_FILE)
            print(f'✓ FTP backup er nyere — bruger FTP version ({ftp_ts})')
        else:
            os.remove(ftp_file)
            print(f'✓ Lokal backup er nyere — beholder lokal ({local_ts})')
    except Exception as exc:
        print(f'⚠ Kunne ikke sammenligne backups: {exc}')
        # If comparison fails but FTP file exists and no local, use FTP
        if not os.path.exists(BACKUP_FILE) and os.path.exists(ftp_file):
            os.replace(ftp_file, BACKUP_FILE)
        elif os.path.exists(ftp_file):
            os.remove(ftp_file)


def restore_from_backup():
    """Populate empty tables from the backup file.
    Runs on startup so a fresh DB after redeploy gets its data back.
    Always tries FTP and uses the newer backup (by exported_at timestamp).
    Handles both version 1 (single-team) and version 2 (multi-team) formats."""
    _try_use_best_backup()
    if not os.path.exists(BACKUP_FILE):
        return
    try:
        with open(BACKUP_FILE, encoding='utf-8') as f:
            data = json.load(f)

        version = data.get('version', 1)
        restored_any = False

        # ── Restore teams (version 2) ────────────────────────────────────────
        if version >= 2 and Team.query.count() == 0:
            team_id_map: dict[int, int] = {}
            for item in data.get('teams', []):
                t = Team(name=item['name'], description=item.get('description', ''))
                db.session.add(t)
                db.session.flush()
                team_id_map[item['id']] = t.id
            restored_any = bool(team_id_map)
        else:
            team_id_map = {t.id: t.id for t in Team.query.all()}

        # ── Restore users ───────────────────────────────────────────────────
        backup_users = data.get('users', [])
        if User.query.count() == 0:
            if backup_users:
                for item in backup_users:
                    u = User(
                        id=item['id'],
                        username=item['username'],
                        password_hash=item['password_hash'],
                        color=item['color'],
                        is_admin=item.get('is_admin', False),
                    )
                    db.session.add(u)
                db.session.flush()
                restored_any = True
            else:
                # Old backup format without users — seed defaults
                for i, name in enumerate(MEMBER_NAMES):
                    user = User(username=name, color=MEMBER_COLORS[i], is_admin=(name in ADMIN_USERS))
                    user.set_password('123')
                    db.session.add(user)
                db.session.flush()
                restored_any = True
                print('⚠ Backup mangler brugere — standardbrugere oprettet')

        valid_user_ids = {u.id for u in User.query.all()}

        # ── Restore user_teams (version 2) ──────────────────────────────────
        if version >= 2 and UserTeam.query.count() == 0:
            for item in data.get('user_teams', []):
                new_tid = team_id_map.get(item['team_id'])
                if new_tid and item['user_id'] in valid_user_ids:
                    db.session.add(UserTeam(
                        user_id=item['user_id'],
                        team_id=new_tid,
                        is_team_admin=item.get('is_team_admin', False),
                    ))
            restored_any = True

        # ── Restore unavailable_dates ────────────────────────────────────────
        if UnavailableDate.query.count() == 0:
            for item in data.get('unavailable_dates', []):
                if item['user_id'] not in valid_user_ids:
                    continue
                raw_tid = item.get('team_id')
                new_tid = team_id_map.get(raw_tid) if raw_tid else None
                db.session.add(UnavailableDate(
                    user_id=item['user_id'],
                    team_id=new_tid,
                    date=date.fromisoformat(item['date']),
                ))
            restored_any = True

        # ── Restore group_events (build old-id → new-id map for comments) ───
        id_map: dict[int, int] = {}
        if GroupEvent.query.count() == 0:
            for item in data.get('group_events', []):
                if item['created_by'] not in valid_user_ids:
                    continue
                raw_tid = item.get('team_id')
                new_tid = team_id_map.get(raw_tid) if raw_tid else None
                end_date_str = item.get('end_date')
                ev = GroupEvent(
                    team_id=new_tid,
                    title=item['title'],
                    description=item.get('description', ''),
                    date=date.fromisoformat(item['date']),
                    end_date=date.fromisoformat(end_date_str) if end_date_str else None,
                    created_by=item['created_by'],
                    created_at=datetime.fromisoformat(item.get('created_at', datetime.utcnow().isoformat())),
                )
                db.session.add(ev)
                db.session.flush()
                id_map[item['id']] = ev.id
            restored_any = True

        # ── Restore event_comments ───────────────────────────────────────────
        if EventComment.query.count() == 0 and id_map:
            for item in data.get('event_comments', []):
                new_eid = id_map.get(item['event_id'])
                if new_eid and item['user_id'] in valid_user_ids:
                    db.session.add(EventComment(
                        event_id=new_eid,
                        user_id=item['user_id'],
                        text=item['text'],
                        is_hidden=item.get('is_hidden', False),
                        created_at=datetime.fromisoformat(item.get('created_at', datetime.utcnow().isoformat())),
                    ))
            restored_any = True

        if restored_any:
            db.session.commit()
            print(f'✓ Data gendannet fra {BACKUP_FILE} (format v{version})')
            write_backup()  # Re-write to ensure latest format
    except Exception as exc:
        print(f'⚠ Backup restore fejlede: {exc}')


def _ics_escape(text: str) -> str:
    return text.replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n')


def _ics_fold(line: str) -> str:
    """Fold lines > 75 octets per RFC 5545."""
    encoded = line.encode('utf-8')
    if len(encoded) <= 75:
        return line
    result, chunk = [], b''
    for byte in encoded:
        chunk += bytes([byte])
        if len(chunk) == 75:
            result.append(chunk.decode('utf-8', errors='replace'))
            chunk = b''
    if chunk:
        result.append(chunk.decode('utf-8', errors='replace'))
    return '\r\n '.join(result)


def generate_ics(team=None) -> str:
    """Generate a RFC 5545 iCalendar string from current DB state, scoped to a team."""
    now_stamp = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    cal_name = team.name if team else 'Ambrotos'

    def vevent(uid, summary, dtstart, dtend, description='', categories=''):
        lines = [
            'BEGIN:VEVENT',
            f'UID:{uid}',
            f'DTSTAMP:{now_stamp}',
            f'DTSTART;VALUE=DATE:{dtstart}',
            f'DTEND;VALUE=DATE:{dtend}',
            f'SUMMARY:{_ics_escape(summary)}',
        ]
        if description:
            lines.append(f'DESCRIPTION:{_ics_escape(description)}')
        if categories:
            lines.append(f'CATEGORIES:{categories}')
        lines.append('END:VEVENT')
        return lines

    output = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        f'PRODID:-//Ambrotos//{_ics_escape(cal_name)}//DA',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        f'X-WR-CALNAME:{_ics_escape(cal_name)}',
        'X-WR-TIMEZONE:Europe/Copenhagen',
    ]

    events_q = GroupEvent.query.order_by(GroupEvent.date)
    if team:
        events_q = events_q.filter_by(team_id=team.id)
    for ev in events_q.all():
        last_day = ev.end_date if ev.end_date and ev.end_date > ev.date else ev.date
        nxt = (last_day + timedelta(days=1)).strftime('%Y%m%d')
        output += vevent(
            uid=f'ambrotos-event-{ev.id}@ambrotos',
            summary=ev.title,
            dtstart=ev.date.strftime('%Y%m%d'),
            dtend=nxt,
            description=ev.description or '',
            categories='GROUP-EVENT',
        )

    dates_q = UnavailableDate.query.join(User).order_by(UnavailableDate.date)
    if team:
        dates_q = dates_q.filter(UnavailableDate.team_id == team.id)
    for ud in dates_q.all():
        nxt = (ud.date + timedelta(days=1)).strftime('%Y%m%d')
        output += vevent(
            uid=f'ambrotos-unavail-{ud.user_id}-{ud.date.isoformat()}@ambrotos',
            summary=f'Utilgængelig: {ud.user.username}',
            dtstart=ud.date.strftime('%Y%m%d'),
            dtend=nxt,
            categories='UNAVAILABLE',
        )

    output.append('END:VCALENDAR')
    return '\r\n'.join(_ics_fold(ln) for ln in output) + '\r\n'


# ── Helpers ────────────────────────────────────────────────────────────────────

from functools import wraps


def get_current_team_id():
    """Henter aktivt team-id fra session. Auto-select første team hvis intet er valgt."""
    if not current_user.is_authenticated:
        return None
    tid = session.get('current_team_id')
    if tid:
        # Valider at brugeren stadig er med i det team (eller er super-admin)
        if current_user.is_admin or UserTeam.query.filter_by(user_id=current_user.id, team_id=tid).first():
            return tid
        session.pop('current_team_id', None)
    # Auto-select: find brugerens første team
    if current_user.is_admin:
        t = Team.query.order_by(Team.id).first()
    else:
        ut = UserTeam.query.filter_by(user_id=current_user.id).order_by(UserTeam.joined_at).first()
        t = db.session.get(Team, ut.team_id) if ut else None
    if t:
        session['current_team_id'] = t.id
        return t.id
    return None


def get_current_team():
    tid = get_current_team_id()
    return db.session.get(Team, tid) if tid else None


def admin_required(f):
    """Kræver global super-admin rettighed (User.is_admin)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return jsonify({'error': 'Ikke tilladt'}), 403
        return f(*args, **kwargs)
    return decorated


def team_admin_required(f):
    """Kræver team-admin rettighed (UserTeam.is_team_admin) eller super-admin for aktivt team."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'error': 'Ikke tilladt'}), 403
        tid = get_current_team_id()
        if not tid or not current_user.is_team_admin_for(tid):
            return jsonify({'error': 'Kræver team-admin rettigheder'}), 403
        return f(*args, **kwargs)
    return decorated


def user_stats(user_id: int, team_id: int = None) -> dict:
    """Compute 12-month stats for a user, optionally scoped to a team."""
    cutoff = date.today() - timedelta(days=365)
    events_q = GroupEvent.query.filter(GroupEvent.date >= cutoff)
    unavail_q = UnavailableDate.query.filter(
        UnavailableDate.user_id == user_id,
        UnavailableDate.date >= cutoff,
    )
    created_q = GroupEvent.query.filter(
        GroupEvent.created_by == user_id,
        GroupEvent.date >= cutoff,
    )
    if team_id:
        events_q = events_q.filter(GroupEvent.team_id == team_id)
        unavail_q = unavail_q.filter(UnavailableDate.team_id == team_id)
        created_q = created_q.filter(GroupEvent.team_id == team_id)
    recent_events = events_q.all()
    user_unavail = {ud.date for ud in unavail_q.all()}
    kan_ikke = sum(1 for e in recent_events if e.date in user_unavail)
    return {
        'events_created': created_q.count(),
        'kan_deltage':    len(recent_events) - kan_ikke,
        'kan_ikke':       kan_ikke,
        'unavail_days':   len(user_unavail),
    }


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route('/select-team/<int:team_id>', methods=['POST'])
@login_required
def select_team(team_id):
    ut = UserTeam.query.filter_by(user_id=current_user.id, team_id=team_id).first()
    if not ut and not current_user.is_admin:
        return jsonify({'error': 'Ingen adgang til dette team'}), 403
    session['current_team_id'] = team_id
    return jsonify({'team_id': team_id})


@app.route('/api/teams')
@login_required
def list_user_teams():
    if current_user.is_admin:
        teams = Team.query.order_by(Team.name).all()
    else:
        team_ids = [ut.team_id for ut in UserTeam.query.filter_by(user_id=current_user.id).all()]
        teams = Team.query.filter(Team.id.in_(team_ids)).order_by(Team.name).all()
    current_tid = get_current_team_id()
    return jsonify([{
        'id': t.id,
        'name': t.name,
        'is_current': t.id == current_tid,
    } for t in teams])


@app.route('/')
@login_required
def index():
    team = get_current_team()
    if not team:
        flash('Ingen teams tilgængelige. Kontakt en administrator.', 'error')
        return render_template('index.html', users=[], current_team=None, user_teams=[], is_team_admin=False)
    team_user_ids = [ut.user_id for ut in UserTeam.query.filter_by(team_id=team.id).all()]
    users = User.query.filter(User.id.in_(team_user_ids)).order_by(User.username).all()
    if current_user.is_admin:
        user_teams = Team.query.order_by(Team.name).all()
    else:
        ut_rows = UserTeam.query.filter_by(user_id=current_user.id).all()
        user_teams = [db.session.get(Team, ut.team_id) for ut in ut_rows]
    return render_template('index.html',
        users=users,
        current_team=team,
        user_teams=user_teams,
        is_team_admin=current_user.is_team_admin_for(team.id),
    )


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user, remember=True)
            return redirect(request.args.get('next') or url_for('index'))

        flash('Forkert brugernavn eller adgangskode.', 'error')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    session.pop('current_team_id', None)
    logout_user()
    return redirect(url_for('login'))


# ── Password reset ─────────────────────────────────────────────────────────────

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    prt = PasswordResetToken.query.filter_by(token=token, used=False).first()
    if not prt or prt.expires_at < datetime.utcnow():
        flash('Linket er ugyldigt eller udløbet.', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        password = request.form.get('password', '').strip()
        confirm  = request.form.get('confirm', '').strip()
        if not password or len(password) < 4:
            flash('Adgangskoden skal være mindst 4 tegn.', 'error')
            return render_template('reset_password.html', token=token)
        if password != confirm:
            flash('Adgangskoderne er ikke ens.', 'error')
            return render_template('reset_password.html', token=token)
        prt.user.set_password(password)
        prt.used = True
        db.session.commit()
        write_backup()
        flash('Adgangskoden er skiftet. Log ind med din nye kode.', 'success')
        return redirect(url_for('login'))

    return render_template('reset_password.html', token=token, username=prt.user.username)


# ── API ────────────────────────────────────────────────────────────────────────

@app.route('/calendar.ics')
@login_required
def serve_ics():
    from flask import Response
    team = get_current_team()
    filename = f"{team.name.lower().replace(' ', '_')}.ics" if team else 'ambrotos.ics'
    return Response(
        generate_ics(team),
        mimetype='text/calendar; charset=utf-8',
        headers={'Content-Disposition': f'inline; filename="{filename}"'},
    )


@app.route('/api/events')
@login_required
def get_events():
    team = get_current_team()
    if not team:
        return jsonify([])
    all_dates = UnavailableDate.query.filter_by(team_id=team.id).join(User).all()
    events = []
    for d in all_dates:
        events.append({
            'id': f"{d.user_id}-{d.date.isoformat()}",
            'title': d.user.username,
            'start': d.date.isoformat(),
            'color': d.user.color,
            'textColor': '#ffffff',
            'extendedProps': {
                'userId': d.user_id,
                'username': d.user.username,
                'isOwn': d.user_id == current_user.id,
                'isHoliday': False,
            },
        })

    # Add Danish public holidays for current year ± 1
    today = date.today()
    for year in range(today.year - 1, today.year + 3):
        for holiday_date, holiday_name, holiday_desc in get_danish_holidays(year):
            events.append({
                'id': f"holiday-{holiday_date.isoformat()}",
                'title': holiday_name,
                'start': holiday_date.isoformat(),
                'color': '#c0392b',
                'textColor': '#ffffff',
                'extendedProps': {
                    'isHoliday': True,
                    'holidayName': holiday_name,
                    'holidayDescription': holiday_desc,
                },
            })

    # Add group events
    for e in GroupEvent.query.filter_by(team_id=team.id).all():
        ev_data = {
            'id': f"gevent-{e.id}",
            'title': e.title,
            'start': e.date.isoformat(),
            'color': '#7c3aed',
            'textColor': '#ffffff',
            'extendedProps': {
                'isHoliday': False,
                'isGroupEvent': True,
                'eventId': e.id,
            },
        }
        if e.end_date and e.end_date > e.date:
            ev_data['end'] = (e.end_date + timedelta(days=1)).isoformat()
        events.append(ev_data)

    return jsonify(events)


@app.route('/api/chat', methods=['POST'])
@login_required
def chat():
    data = request.get_json()
    message = data.get('message', '').strip()
    if not message:
        return jsonify({'error': 'Tom besked'}), 400

    is_delete = message.lower().startswith(('slet ', 'fjern '))
    parse_text = re.sub(r'^(slet|fjern)\s+', '', message, flags=re.IGNORECASE).strip()

    dates = parse_dates_from_message(parse_text)

    if not dates:
        return jsonify({
            'response': (
                'Jeg forstod ikke hvilken dato du mente. '
                'Prøv fx "15. marts", "fra 1. til 5. april" eller "alle mandage i maj".'
            ),
            'added': [], 'deleted': [], 'already_exists': [], 'not_found': [],
        })

    team = get_current_team()
    if not team:
        return jsonify({'error': 'Intet team valgt'}), 400

    added, deleted, already_exists, not_found = [], [], [], []

    for d in dates:
        existing = UnavailableDate.query.filter_by(user_id=current_user.id, team_id=team.id, date=d).first()
        if is_delete:
            if existing:
                db.session.delete(existing)
                deleted.append(d.isoformat())
            else:
                not_found.append(d.isoformat())
        else:
            if existing:
                already_exists.append(d.isoformat())
            else:
                db.session.add(UnavailableDate(user_id=current_user.id, team_id=team.id, date=d))
                added.append(d.isoformat())

    db.session.commit()

    if added or deleted:
        write_backup()

    if is_delete:
        if deleted:
            response = f"Slettet: {format_dates_danish(deleted)}."
            if not_found:
                response += f" Ikke fundet: {format_dates_danish(not_found)}."
        else:
            response = f"Ingen af de nævnte datoer ({format_dates_danish(not_found)}) var markeret som utilgængelig."
    else:
        if added:
            response = f"Du er nu markeret som utilgængelig: {format_dates_danish(added)}."
            if already_exists:
                response += f" Allerede markeret: {format_dates_danish(already_exists)}."
        else:
            response = f"Alle nævnte datoer var allerede markeret som utilgængelig."

    return jsonify({
        'response': response,
        'added': added,
        'deleted': deleted,
        'already_exists': already_exists,
        'not_found': not_found,
    })


@app.route('/api/unavailable/toggle', methods=['POST'])
@login_required
def toggle_unavailable():
    team = get_current_team()
    if not team:
        return jsonify({'error': 'Intet team valgt'}), 400
    data = request.get_json()
    date_str = data.get('date', '')
    try:
        d = date.fromisoformat(date_str)
    except (ValueError, TypeError):
        return jsonify({'error': 'Ugyldig dato'}), 400
    existing = UnavailableDate.query.filter_by(user_id=current_user.id, team_id=team.id, date=d).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        write_backup()
        return jsonify({'action': 'removed', 'date': date_str})
    db.session.add(UnavailableDate(user_id=current_user.id, team_id=team.id, date=d))
    db.session.commit()
    write_backup()
    return jsonify({'action': 'added', 'date': date_str})


@app.route('/api/group-events', methods=['GET'])
@login_required
def list_group_events():
    team = get_current_team()
    if not team:
        return jsonify([])
    today = date.today()
    cutoff = today + timedelta(days=183)
    events = GroupEvent.query.filter(
        GroupEvent.team_id == team.id,
        db.or_(
            GroupEvent.date >= today,
            db.and_(GroupEvent.end_date.isnot(None), GroupEvent.end_date >= today),
        ),
        GroupEvent.date <= cutoff,
    ).order_by(GroupEvent.date).all()
    return jsonify([{
        'id': e.id,
        'title': e.title,
        'description': e.description,
        'date': e.date.isoformat(),
        'end_date': e.end_date.isoformat() if e.end_date else None,
        'creator': e.creator.username,
        'created_by': e.created_by,
        'comment_count': len(e.comments),
    } for e in events])


@app.route('/api/group-events', methods=['POST'])
@login_required
def create_group_event():
    data = request.get_json()
    title = data.get('title', '').strip()
    description = data.get('description', '').strip()
    date_str = data.get('date', '')
    end_date_str = data.get('end_date', '')
    if not title:
        return jsonify({'error': 'Titel mangler'}), 400
    try:
        d = date.fromisoformat(date_str)
    except (ValueError, TypeError):
        return jsonify({'error': 'Ugyldig dato'}), 400
    end_d = None
    if end_date_str:
        try:
            end_d = date.fromisoformat(end_date_str)
            if end_d <= d:
                end_d = None
        except (ValueError, TypeError):
            pass
    team = get_current_team()
    if not team:
        return jsonify({'error': 'Intet team valgt'}), 400
    event = GroupEvent(title=title, description=description, date=d, end_date=end_d,
                       created_by=current_user.id, team_id=team.id)
    db.session.add(event)
    db.session.commit()
    write_backup()
    return jsonify({'id': event.id, 'title': event.title, 'date': event.date.isoformat()}), 201


@app.route('/api/group-events/<int:event_id>', methods=['GET'])
@login_required
def get_group_event(event_id):
    team = get_current_team()
    event = db.session.get(GroupEvent, event_id)
    if not event or (team and event.team_id != team.id):
        return jsonify({'error': 'Ikke fundet'}), 404

    # Collect all dates in the event range for attendance check
    last_day = event.end_date if event.end_date and event.end_date > event.date else event.date
    event_dates = set()
    d = event.date
    while d <= last_day:
        event_dates.add(d)
        d += timedelta(days=1)

    # Only users in this team count for attendance
    team_user_ids = {ut.user_id for ut in UserTeam.query.filter_by(team_id=event.team_id).all()} if event.team_id else None
    unavail_query = UnavailableDate.query.filter(UnavailableDate.date.in_(event_dates))
    if event.team_id:
        unavail_query = unavail_query.filter_by(team_id=event.team_id)
    unavailable_ids = {ud.user_id for ud in unavail_query.all()}
    if team_user_ids is not None:
        all_users = User.query.filter(User.id.in_(team_user_ids)).order_by(User.id).all()
    else:
        all_users = User.query.order_by(User.id).all()
    can_edit = event.created_by == current_user.id or current_user.is_team_admin_for(event.team_id or 0)

    # Filter hidden comments for non-team-admins
    is_team_admin = current_user.is_team_admin_for(event.team_id or 0)
    comments = []
    for c in event.comments:
        if c.is_hidden and not is_team_admin:
            continue
        comments.append({
            'id': c.id,
            'text': c.text,
            'author': c.author.username,
            'author_color': c.author.color,
            'created_at': c.created_at.strftime('%d. %b %Y %H:%M'),
            'is_own': c.user_id == current_user.id,
            'is_hidden': c.is_hidden,
        })

    return jsonify({
        'id': event.id,
        'title': event.title,
        'description': event.description,
        'date': event.date.isoformat(),
        'end_date': event.end_date.isoformat() if event.end_date else None,
        'creator': event.creator.username,
        'created_by': event.created_by,
        'is_own': event.created_by == current_user.id,
        'can_edit': can_edit,
        'attending': [
            {'id': u.id, 'username': u.username, 'color': u.color}
            for u in all_users if u.id not in unavailable_ids
        ],
        'not_attending': [
            {'id': u.id, 'username': u.username, 'color': u.color}
            for u in all_users if u.id in unavailable_ids
        ],
        'comments': comments,
    })


@app.route('/api/group-events/<int:event_id>', methods=['DELETE'])
@login_required
def delete_group_event(event_id):
    event = db.session.get(GroupEvent, event_id)
    if not event or (event.team_id and event.team_id != get_current_team_id()):
        return jsonify({'error': 'Ikke fundet'}), 404
    if event.created_by != current_user.id and not current_user.is_team_admin_for(event.team_id or 0):
        return jsonify({'error': 'Ikke tilladt'}), 403
    db.session.delete(event)
    db.session.commit()
    write_backup()
    return jsonify({'deleted': True})


@app.route('/api/group-events/<int:event_id>', methods=['PUT'])
@login_required
def update_group_event(event_id):
    event = db.session.get(GroupEvent, event_id)
    if not event or (event.team_id and event.team_id != get_current_team_id()):
        return jsonify({'error': 'Ikke fundet'}), 404
    if event.created_by != current_user.id and not current_user.is_team_admin_for(event.team_id or 0):
        return jsonify({'error': 'Ikke tilladt'}), 403
    data = request.get_json()
    if 'title' in data:
        title = data['title'].strip()
        if not title:
            return jsonify({'error': 'Titel mangler'}), 400
        event.title = title
    if 'description' in data:
        event.description = data['description'].strip()
    if 'date' in data:
        try:
            event.date = date.fromisoformat(data['date'])
        except (ValueError, TypeError):
            return jsonify({'error': 'Ugyldig startdato'}), 400
    if 'end_date' in data:
        if data['end_date']:
            try:
                end_d = date.fromisoformat(data['end_date'])
                event.end_date = end_d if end_d > event.date else None
            except (ValueError, TypeError):
                return jsonify({'error': 'Ugyldig slutdato'}), 400
        else:
            event.end_date = None
    db.session.commit()
    write_backup()
    return jsonify({
        'id': event.id, 'title': event.title,
        'date': event.date.isoformat(),
        'end_date': event.end_date.isoformat() if event.end_date else None,
    })


@app.route('/api/group-events/<int:event_id>/comments', methods=['POST'])
@login_required
def add_event_comment(event_id):
    event = db.session.get(GroupEvent, event_id)
    if not event or (event.team_id and event.team_id != get_current_team_id()):
        return jsonify({'error': 'Ikke fundet'}), 404
    data = request.get_json()
    text = data.get('text', '').strip()
    if not text:
        return jsonify({'error': 'Kommentar mangler'}), 400
    comment = EventComment(event_id=event_id, user_id=current_user.id, text=text)
    db.session.add(comment)
    db.session.commit()
    write_backup()
    return jsonify({
        'id': comment.id,
        'text': comment.text,
        'author': current_user.username,
        'author_color': current_user.color,
        'created_at': comment.created_at.strftime('%d. %b %Y %H:%M'),
        'is_own': True,
        'is_hidden': False,
    }), 201


@app.route('/api/group-events/<int:event_id>/comments/<int:comment_id>', methods=['DELETE'])
@login_required
def delete_event_comment(event_id, comment_id):
    comment = db.session.get(EventComment, comment_id)
    if not comment or comment.event_id != event_id:
        return jsonify({'error': 'Ikke fundet'}), 404
    if comment.user_id != current_user.id:
        return jsonify({'error': 'Ikke tilladt'}), 403
    db.session.delete(comment)
    db.session.commit()
    write_backup()
    return jsonify({'deleted': True})


@app.route('/api/group-events/<int:event_id>/comments/<int:comment_id>/hide', methods=['PUT'])
@login_required
@team_admin_required
def hide_event_comment(event_id, comment_id):
    comment = db.session.get(EventComment, comment_id)
    if not comment or comment.event_id != event_id:
        return jsonify({'error': 'Ikke fundet'}), 404
    data = request.get_json()
    comment.is_hidden = bool(data.get('hidden', True))
    db.session.commit()
    write_backup()
    return jsonify({'id': comment.id, 'is_hidden': comment.is_hidden})


# ── Admin routes ───────────────────────────────────────────────────────────────

@app.route('/admin')
@login_required
def admin_panel():
    if not current_user.is_admin:
        flash('Ingen adgang.', 'error')
        return redirect(url_for('index'))
    team = get_current_team()
    if team:
        team_user_ids = [ut.user_id for ut in UserTeam.query.filter_by(team_id=team.id).all()]
        users = User.query.filter(User.id.in_(team_user_ids)).order_by(User.id).all()
    else:
        users = User.query.order_by(User.id).all()
    tid = team.id if team else None
    stats = {u.id: user_stats(u.id, tid) for u in users}
    teams = Team.query.order_by(Team.name).all()
    teams_json = [{'id': t.id, 'name': t.name, 'description': t.description or ''} for t in teams]
    all_users = User.query.order_by(User.username).all()
    return render_template('admin.html', users=users, stats=stats, teams=teams,
                           teams_json=teams_json, current_team=team, all_users=all_users)


@app.route('/api/admin/users', methods=['GET'])
@login_required
@admin_required
def admin_list_users():
    team = get_current_team()
    if team:
        team_user_ids = [ut.user_id for ut in UserTeam.query.filter_by(team_id=team.id).all()]
        users = User.query.filter(User.id.in_(team_user_ids)).order_by(User.id).all()
    else:
        users = User.query.order_by(User.id).all()
    tid = team.id if team else None
    return jsonify([{
        'id': u.id,
        'username': u.username,
        'color': u.color,
        'is_admin': u.is_admin,
        **user_stats(u.id, tid),
    } for u in users])


@app.route('/api/admin/users', methods=['POST'])
@login_required
@admin_required
def admin_create_user():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    color    = data.get('color', '#1e88e5').strip()
    if not username or not password:
        return jsonify({'error': 'Navn og adgangskode er påkrævet'}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Brugernavn er allerede i brug'}), 400
    u = User(username=username, color=color)
    u.set_password(password)
    db.session.add(u)
    db.session.flush()
    # Add new user to current team if one is active
    tid = get_current_team_id()
    if tid:
        db.session.add(UserTeam(user_id=u.id, team_id=tid, is_team_admin=False))
    db.session.commit()
    write_backup()
    return jsonify({'id': u.id, 'username': u.username, 'color': u.color}), 201


@app.route('/api/admin/users/<int:user_id>', methods=['PUT'])
@login_required
@admin_required
def admin_update_user(user_id):
    u = db.session.get(User, user_id)
    if not u:
        return jsonify({'error': 'Ikke fundet'}), 404
    data = request.get_json()
    if 'username' in data:
        new_name = data['username'].strip()
        if not new_name:
            return jsonify({'error': 'Navn må ikke være tomt'}), 400
        existing = User.query.filter_by(username=new_name).first()
        if existing and existing.id != user_id:
            return jsonify({'error': 'Brugernavn er allerede i brug'}), 400
        u.username = new_name
    if 'color' in data:
        u.color = data['color']
    if 'password' in data and data['password'].strip():
        u.set_password(data['password'].strip())
    if 'is_admin' in data:
        u.is_admin = bool(data['is_admin'])
    db.session.commit()
    write_backup()
    return jsonify({'id': u.id, 'username': u.username, 'color': u.color, 'is_admin': u.is_admin})


@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@login_required
@admin_required
def admin_delete_user(user_id):
    if user_id == current_user.id:
        return jsonify({'error': 'Du kan ikke slette din egen konto'}), 400
    u = db.session.get(User, user_id)
    if not u:
        return jsonify({'error': 'Ikke fundet'}), 404
    db.session.delete(u)
    db.session.commit()
    write_backup()
    return jsonify({'deleted': True})


# ── Password reset admin endpoint ──────────────────────────────────────────────

@app.route('/api/admin/users/<int:user_id>/reset-token', methods=['POST'])
@login_required
@admin_required
def admin_generate_reset_token(user_id):
    u = db.session.get(User, user_id)
    if not u:
        return jsonify({'error': 'Ikke fundet'}), 404
    # Invalidate any existing unused tokens for this user
    PasswordResetToken.query.filter_by(user_id=user_id, used=False).update({'used': True})
    token = secrets.token_urlsafe(32)
    prt = PasswordResetToken(
        token=token,
        user_id=user_id,
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )
    db.session.add(prt)
    db.session.commit()
    reset_url = url_for('reset_password', token=token, _external=True)
    return jsonify({'reset_url': reset_url, 'username': u.username})


# ── Admin team management routes ────────────────────────────────────────────────

@app.route('/api/admin/teams', methods=['GET'])
@login_required
@admin_required
def admin_list_teams():
    teams = Team.query.order_by(Team.name).all()
    return jsonify([{
        'id': t.id,
        'name': t.name,
        'description': t.description,
        'member_count': UserTeam.query.filter_by(team_id=t.id).count(),
    } for t in teams])


@app.route('/api/admin/teams', methods=['POST'])
@login_required
@admin_required
def admin_create_team():
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Teamnavn er påkrævet'}), 400
    if Team.query.filter_by(name=name).first():
        return jsonify({'error': 'Teamnavn er allerede i brug'}), 400
    t = Team(name=name, description=data.get('description', '').strip())
    db.session.add(t)
    db.session.commit()
    write_backup()
    return jsonify({'id': t.id, 'name': t.name}), 201


@app.route('/api/admin/teams/<int:team_id>', methods=['PUT'])
@login_required
@admin_required
def admin_update_team(team_id):
    t = db.session.get(Team, team_id)
    if not t:
        return jsonify({'error': 'Ikke fundet'}), 404
    data = request.get_json()
    if 'name' in data:
        name = data['name'].strip()
        if not name:
            return jsonify({'error': 'Navn må ikke være tomt'}), 400
        existing = Team.query.filter_by(name=name).first()
        if existing and existing.id != team_id:
            return jsonify({'error': 'Teamnavn er allerede i brug'}), 400
        t.name = name
    if 'description' in data:
        t.description = data['description'].strip()
    db.session.commit()
    write_backup()
    return jsonify({'id': t.id, 'name': t.name, 'description': t.description})


@app.route('/api/admin/teams/<int:team_id>', methods=['DELETE'])
@login_required
@admin_required
def admin_delete_team(team_id):
    t = db.session.get(Team, team_id)
    if not t:
        return jsonify({'error': 'Ikke fundet'}), 404
    if Team.query.count() <= 1:
        return jsonify({'error': 'Kan ikke slette det eneste team'}), 400
    db.session.delete(t)
    db.session.commit()
    write_backup()
    return jsonify({'deleted': True})


@app.route('/api/admin/teams/<int:team_id>/members', methods=['GET'])
@login_required
@admin_required
def admin_list_team_members(team_id):
    t = db.session.get(Team, team_id)
    if not t:
        return jsonify({'error': 'Ikke fundet'}), 404
    members = UserTeam.query.filter_by(team_id=team_id).all()
    return jsonify([{
        'user_id': m.user_id,
        'username': db.session.get(User, m.user_id).username,
        'color': db.session.get(User, m.user_id).color,
        'is_team_admin': m.is_team_admin,
    } for m in members])


@app.route('/api/admin/teams/<int:team_id>/members', methods=['POST'])
@login_required
@admin_required
def admin_add_team_member(team_id):
    t = db.session.get(Team, team_id)
    if not t:
        return jsonify({'error': 'Ikke fundet'}), 404
    data = request.get_json()
    user_id = data.get('user_id')
    u = db.session.get(User, user_id) if user_id else None
    if not u:
        return jsonify({'error': 'Bruger ikke fundet'}), 404
    if UserTeam.query.filter_by(user_id=user_id, team_id=team_id).first():
        return jsonify({'error': 'Bruger er allerede i dette team'}), 400
    db.session.add(UserTeam(user_id=user_id, team_id=team_id,
                             is_team_admin=bool(data.get('is_team_admin', False))))
    db.session.commit()
    write_backup()
    return jsonify({'user_id': user_id, 'team_id': team_id}), 201


@app.route('/api/admin/teams/<int:team_id>/members/<int:user_id>', methods=['DELETE'])
@login_required
@admin_required
def admin_remove_team_member(team_id, user_id):
    ut = UserTeam.query.filter_by(user_id=user_id, team_id=team_id).first()
    if not ut:
        return jsonify({'error': 'Ikke fundet'}), 404
    db.session.delete(ut)
    db.session.commit()
    write_backup()
    return jsonify({'deleted': True})


@app.route('/api/admin/teams/<int:team_id>/members/<int:user_id>', methods=['PUT'])
@login_required
@admin_required
def admin_set_team_admin(team_id, user_id):
    ut = UserTeam.query.filter_by(user_id=user_id, team_id=team_id).first()
    if not ut:
        return jsonify({'error': 'Ikke fundet'}), 404
    data = request.get_json()
    ut.is_team_admin = bool(data.get('is_team_admin', False))
    db.session.commit()
    write_backup()
    return jsonify({'user_id': user_id, 'team_id': team_id, 'is_team_admin': ut.is_team_admin})


# ── Database seed ──────────────────────────────────────────────────────────────

def migrate_db():
    """Add new columns to existing tables (idempotent)."""
    inspector = sa_inspect(db.engine)
    with db.engine.begin() as conn:
        if inspector.has_table('group_events'):
            cols = {c['name'] for c in inspector.get_columns('group_events')}
            if 'end_date' not in cols:
                conn.execute(sa_text("ALTER TABLE group_events ADD COLUMN end_date DATE"))
            if 'team_id' not in cols:
                conn.execute(sa_text("ALTER TABLE group_events ADD COLUMN team_id INTEGER REFERENCES teams(id)"))
        if inspector.has_table('event_comments'):
            cols = {c['name'] for c in inspector.get_columns('event_comments')}
            if 'is_hidden' not in cols:
                conn.execute(sa_text(
                    "ALTER TABLE event_comments ADD COLUMN is_hidden BOOLEAN DEFAULT 0 NOT NULL"
                ))
        if inspector.has_table('unavailable_dates'):
            cols = {c['name'] for c in inspector.get_columns('unavailable_dates')}
            if 'team_id' not in cols:
                conn.execute(sa_text("ALTER TABLE unavailable_dates ADD COLUMN team_id INTEGER REFERENCES teams(id)"))


def _migrate_to_teams():
    """Engangsmigration: tildel alle eksisterende rækker til et default 'Ambrotos' team."""
    if Team.query.count() > 0:
        return  # Already migrated
    ambrotos = Team(name='Ambrotos', description='Standard team')
    db.session.add(ambrotos)
    db.session.flush()
    for user in User.query.all():
        if not UserTeam.query.filter_by(user_id=user.id, team_id=ambrotos.id).first():
            db.session.add(UserTeam(
                user_id=user.id,
                team_id=ambrotos.id,
                is_team_admin=user.is_admin,
            ))
    db.session.execute(
        sa_text("UPDATE unavailable_dates SET team_id = :tid WHERE team_id IS NULL"),
        {'tid': ambrotos.id},
    )
    db.session.execute(
        sa_text("UPDATE group_events SET team_id = :tid WHERE team_id IS NULL"),
        {'tid': ambrotos.id},
    )
    db.session.commit()
    print('✓ Migreret til multi-team: Ambrotos team oprettet')


def init_db():
    with app.app_context():
        db.create_all()   # only creates tables that don't yet exist
        migrate_db()      # add new columns to existing tables

        # Try to restore from backup first (includes users if available)
        restore_from_backup()

        # Fallback: seed default users only if no users exist (fresh install, no backup)
        if User.query.count() == 0:
            for i, name in enumerate(MEMBER_NAMES):
                user = User(username=name, color=MEMBER_COLORS[i], is_admin=(name in ADMIN_USERS))
                user.set_password('123')
                db.session.add(user)
            db.session.commit()
            print(f"✓ Oprettet {len(MEMBER_NAMES)} standardbrugere (ingen backup fundet)")
        else:
            db_type = 'PostgreSQL' if 'postgresql' in app.config['SQLALCHEMY_DATABASE_URI'] else 'SQLite'
            print(f"✓ Forbundet til {db_type} — {User.query.count()} brugere, data intakt")

        # Migrate existing single-team data to multi-team structure
        _migrate_to_teams()


# Run on every startup (gunicorn imports this module, so __name__ != '__main__').
# init_db() is idempotent — safe to call multiple times.
init_db()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
