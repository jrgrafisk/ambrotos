import os
import json
from datetime import datetime, date

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'ambrotos-dev-secret-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///calendar.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Log venligst ind for at fortsætte.'

anthropic_client = Anthropic()  # Reads ANTHROPIC_API_KEY from environment

MEMBER_NAMES = [
    'Anders', 'Birthe', 'Christian', 'Dorte', 'Erik',
    'Freja', 'Gunnar', 'Helle', 'Ivan', 'Jette',
    'Klaus', 'Lene', 'Mikkel', 'Nina',
]

MEMBER_COLORS = [
    '#e53935', '#1e88e5', '#43a047', '#fb8c00', '#8e24aa',
    '#00acc1', '#f4511e', '#3949ab', '#00897b', '#c0ca33',
    '#ffb300', '#d81b60', '#6d4c41', '#546e7a',
]


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

    today = date.today()
    current_year = today.year

    system = f"""Du er en kalenderassistent for et dansk mødeplanlægningssystem.
Din opgave er at fortolke brugerens besked og udtrække datoer.

VIGTIGE REGLER:
- Dagens dato: {today.isoformat()} (år {current_year})
- Hvis brugeren skriver "slet [dato]" eller "fjern [dato]", skal den dato slettes
- Alle andre beskeder tilføjer datoer som "ikke tilgængelig"
- Understøt danske datoformater: "15. marts", "d. 15/3", "15-03-2025", "mandag den 3. juni", "2025-03-15" osv.
- Hvis intet år nævnes, brug {current_year} — eller {current_year + 1} hvis datoen allerede er passeret
- Perioder: "fra 1. til 5. marts" = alle dage inklusiv begge slutdatoer
- Lister: "5., 12. og 19. januar" = tre separate datoer
- Ugedage i en måned: "alle mandage i marts {current_year}" = alle mandage i den måned

SVAR KUN MED GYLDIG JSON (ingen forklarende tekst, ingen markdown):
{{
  "add_dates": ["YYYY-MM-DD"],
  "delete_dates": ["YYYY-MM-DD"],
  "response": "Bekræftelsesbesked på dansk til brugeren"
}}"""

    try:
        ai_msg = anthropic_client.messages.create(
            model='claude-opus-4-6',
            max_tokens=1024,
            system=system,
            messages=[{'role': 'user', 'content': message}],
        )
        raw = ai_msg.content[0].text.strip()

        # Strip markdown code fences if the model added them
        if raw.startswith('```'):
            lines = raw.splitlines()
            inner = lines[1:] if lines[0].startswith('```') else lines
            if inner and inner[-1].strip() == '```':
                inner = inner[:-1]
            raw = '\n'.join(inner).strip()

        parsed = json.loads(raw)
        added, deleted, already_exists, not_found = [], [], [], []

        for date_str in parsed.get('add_dates', []):
            try:
                d = datetime.strptime(date_str, '%Y-%m-%d').date()
                existing = UnavailableDate.query.filter_by(
                    user_id=current_user.id, date=d
                ).first()
                if existing:
                    already_exists.append(date_str)
                else:
                    db.session.add(UnavailableDate(user_id=current_user.id, date=d))
                    added.append(date_str)
            except ValueError:
                pass  # Skip unparseable dates

        for date_str in parsed.get('delete_dates', []):
            try:
                d = datetime.strptime(date_str, '%Y-%m-%d').date()
                existing = UnavailableDate.query.filter_by(
                    user_id=current_user.id, date=d
                ).first()
                if existing:
                    db.session.delete(existing)
                    deleted.append(date_str)
                else:
                    not_found.append(date_str)
            except ValueError:
                pass

        db.session.commit()

        return jsonify({
            'response': parsed.get('response', 'Forstået.'),
            'added': added,
            'deleted': deleted,
            'already_exists': already_exists,
            'not_found': not_found,
        })

    except json.JSONDecodeError:
        return jsonify({
            'response': 'Beklager, jeg forstod ikke svaret. Prøv at skrive dato(erne) igen.',
            'added': [],
            'deleted': [],
        })
    except Exception as e:
        app.logger.error(f"Chat error: {e}")
        return jsonify({'error': 'Der opstod en fejl. Prøv igen.'}), 500


# ── Database seed ──────────────────────────────────────────────────────────────

def init_db():
    with app.app_context():
        db.create_all()
        if User.query.count() == 0:
            password = 'kodeordetersvært'
            for i, name in enumerate(MEMBER_NAMES):
                user = User(username=name, color=MEMBER_COLORS[i])
                user.set_password(password)
                db.session.add(user)
            db.session.commit()
            print(f"✓ Oprettet {len(MEMBER_NAMES)} brugere")
            print(f"  Adgangskode for alle: '{password}'")
        else:
            print(f"✓ Database allerede initialiseret ({User.query.count()} brugere)")


if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
