import os
import re
import calendar as cal_module
from datetime import datetime, date, timedelta

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
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

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    color = db.Column(db.String(7), nullable=False, default='#1e88e5')
    unavailable_dates = db.relationship(
        'UnavailableDate', backref='user', lazy=True, cascade='all, delete-orphan'
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class UnavailableDate(db.Model):
    __tablename__ = 'unavailable_dates'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'date', name='unique_user_date'),
    )


class GroupEvent(db.Model):
    __tablename__ = 'group_events'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    date = db.Column(db.Date, nullable=False)
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    author = db.relationship('User')


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route('/')
@login_required
def index():
    users = User.query.order_by(User.username).all()
    return render_template('index.html', users=users)


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
    logout_user()
    return redirect(url_for('login'))


# ── API ────────────────────────────────────────────────────────────────────────

@app.route('/api/events')
@login_required
def get_events():
    all_dates = UnavailableDate.query.join(User).all()
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
    for e in GroupEvent.query.all():
        events.append({
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
        })

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

    added, deleted, already_exists, not_found = [], [], [], []

    for d in dates:
        existing = UnavailableDate.query.filter_by(user_id=current_user.id, date=d).first()
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
                db.session.add(UnavailableDate(user_id=current_user.id, date=d))
                added.append(d.isoformat())

    db.session.commit()

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
    data = request.get_json()
    date_str = data.get('date', '')
    try:
        d = date.fromisoformat(date_str)
    except (ValueError, TypeError):
        return jsonify({'error': 'Ugyldig dato'}), 400
    existing = UnavailableDate.query.filter_by(user_id=current_user.id, date=d).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({'action': 'removed', 'date': date_str})
    db.session.add(UnavailableDate(user_id=current_user.id, date=d))
    db.session.commit()
    return jsonify({'action': 'added', 'date': date_str})


@app.route('/api/group-events', methods=['GET'])
@login_required
def list_group_events():
    today = date.today()
    cutoff = today + timedelta(days=183)
    events = GroupEvent.query.filter(
        GroupEvent.date >= today,
        GroupEvent.date <= cutoff,
    ).order_by(GroupEvent.date).all()
    return jsonify([{
        'id': e.id,
        'title': e.title,
        'description': e.description,
        'date': e.date.isoformat(),
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
    if not title:
        return jsonify({'error': 'Titel mangler'}), 400
    try:
        d = date.fromisoformat(date_str)
    except (ValueError, TypeError):
        return jsonify({'error': 'Ugyldig dato'}), 400
    event = GroupEvent(title=title, description=description, date=d, created_by=current_user.id)
    db.session.add(event)
    db.session.commit()
    return jsonify({'id': event.id, 'title': event.title, 'date': event.date.isoformat()}), 201


@app.route('/api/group-events/<int:event_id>', methods=['GET'])
@login_required
def get_group_event(event_id):
    event = db.session.get(GroupEvent, event_id)
    if not event:
        return jsonify({'error': 'Ikke fundet'}), 404
    unavailable_ids = {
        ud.user_id for ud in UnavailableDate.query.filter_by(date=event.date).all()
    }
    all_users = User.query.order_by(User.id).all()
    return jsonify({
        'id': event.id,
        'title': event.title,
        'description': event.description,
        'date': event.date.isoformat(),
        'creator': event.creator.username,
        'created_by': event.created_by,
        'is_own': event.created_by == current_user.id,
        'attending': [
            {'id': u.id, 'username': u.username, 'color': u.color}
            for u in all_users if u.id not in unavailable_ids
        ],
        'not_attending': [
            {'id': u.id, 'username': u.username, 'color': u.color}
            for u in all_users if u.id in unavailable_ids
        ],
        'comments': [{
            'id': c.id,
            'text': c.text,
            'author': c.author.username,
            'author_color': c.author.color,
            'created_at': c.created_at.strftime('%d. %b %Y %H:%M'),
            'is_own': c.user_id == current_user.id,
        } for c in event.comments],
    })


@app.route('/api/group-events/<int:event_id>', methods=['DELETE'])
@login_required
def delete_group_event(event_id):
    event = db.session.get(GroupEvent, event_id)
    if not event:
        return jsonify({'error': 'Ikke fundet'}), 404
    if event.created_by != current_user.id:
        return jsonify({'error': 'Ikke tilladt'}), 403
    db.session.delete(event)
    db.session.commit()
    return jsonify({'deleted': True})


@app.route('/api/group-events/<int:event_id>/comments', methods=['POST'])
@login_required
def add_event_comment(event_id):
    event = db.session.get(GroupEvent, event_id)
    if not event:
        return jsonify({'error': 'Ikke fundet'}), 404
    data = request.get_json()
    text = data.get('text', '').strip()
    if not text:
        return jsonify({'error': 'Kommentar mangler'}), 400
    comment = EventComment(event_id=event_id, user_id=current_user.id, text=text)
    db.session.add(comment)
    db.session.commit()
    return jsonify({
        'id': comment.id,
        'text': comment.text,
        'author': current_user.username,
        'author_color': current_user.color,
        'created_at': comment.created_at.strftime('%d. %b %Y %H:%M'),
        'is_own': True,
    }), 201


# ── Database seed ──────────────────────────────────────────────────────────────

def init_db():
    with app.app_context():
        db.create_all()   # only creates tables that don't yet exist
        password = '123'
        if User.query.count() == 0:
            for i, name in enumerate(MEMBER_NAMES):
                user = User(username=name, color=MEMBER_COLORS[i])
                user.set_password(password)
                db.session.add(user)
            db.session.commit()
            print(f"✓ Oprettet {len(MEMBER_NAMES)} brugere")
            print(f"  Adgangskode for alle: '{password}'")
        else:
            db_type = 'PostgreSQL' if 'postgresql' in app.config['SQLALCHEMY_DATABASE_URI'] else 'SQLite'
            print(f"✓ Forbundet til {db_type} — {User.query.count()} brugere, data intakt")


# Run on every startup (gunicorn imports this module, so __name__ != '__main__').
# init_db() is idempotent — safe to call multiple times.
init_db()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
