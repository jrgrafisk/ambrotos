#!/usr/bin/env python3
"""Pre-deploy backup script.

Run by Render as preDeployCommand before each deploy.
Takes a live snapshot of the PostgreSQL database and uploads it to FTP
as calendar_backup.json so restore_from_backup() picks it up on startup.

Also saves a timestamped archive copy under /ambrotos/predeploy/.
"""

import ftplib
import io
import json
import os
import sys
from datetime import datetime

DATABASE_URL = os.environ.get('DATABASE_URL', '')
FTP_HOST     = os.environ.get('FTP_HOST', '')
FTP_USER     = os.environ.get('FTP_USER', '')
FTP_PASS     = os.environ.get('FTP_PASS', '')
FTP_PATH     = os.environ.get('FTP_PATH', '/ambrotos')


def _ftp_ensure_dir(ftp, path):
    dirs = [d for d in path.strip('/').split('/') if d]
    for d in dirs:
        try:
            ftp.cwd(d)
        except ftplib.error_perm:
            ftp.mkd(d)
            ftp.cwd(d)


def _fetch_postgres(url):
    import psycopg2
    import psycopg2.extras
    conn_url = url.replace('postgres://', 'postgresql://', 1) if url.startswith('postgres://') else url
    conn = psycopg2.connect(conn_url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def _iso(val):
        if val is None:
            return None
        return val.isoformat() if hasattr(val, 'isoformat') else str(val)

    cur.execute("SELECT id, name, COALESCE(description, '') AS description FROM teams ORDER BY id")
    teams = [dict(r) for r in cur.fetchall()]

    cur.execute("SELECT user_id, team_id, COALESCE(is_team_admin, false) AS is_team_admin FROM user_teams")
    user_teams = [{'user_id': r['user_id'], 'team_id': r['team_id'], 'is_team_admin': bool(r['is_team_admin'])} for r in cur.fetchall()]

    cur.execute("SELECT id, username, password_hash, color, COALESCE(is_admin, false) AS is_admin FROM users ORDER BY id")
    users = [{'id': r['id'], 'username': r['username'], 'password_hash': r['password_hash'], 'color': r['color'], 'is_admin': bool(r['is_admin'])} for r in cur.fetchall()]

    cur.execute("SELECT user_id, team_id, date FROM unavailable_dates")
    unavailable = [{'user_id': r['user_id'], 'team_id': r['team_id'], 'date': _iso(r['date'])} for r in cur.fetchall()]

    cur.execute("""
        SELECT id, team_id, title, COALESCE(description, '') AS description,
               date, end_date, created_by, organizer1_id, organizer2_id, created_at
        FROM group_events ORDER BY id
    """)
    events = [{
        'id':            r['id'],
        'team_id':       r['team_id'],
        'title':         r['title'],
        'description':   r['description'],
        'date':          _iso(r['date']),
        'end_date':      _iso(r['end_date']),
        'created_by':    r['created_by'],
        'organizer1_id': r['organizer1_id'],
        'organizer2_id': r['organizer2_id'],
        'created_at':    _iso(r['created_at']),
    } for r in cur.fetchall()]

    cur.execute("""
        SELECT event_id, user_id, text, COALESCE(is_hidden, false) AS is_hidden, created_at
        FROM event_comments ORDER BY id
    """)
    comments = [{'event_id': r['event_id'], 'user_id': r['user_id'], 'text': r['text'],
                 'is_hidden': bool(r['is_hidden']), 'created_at': _iso(r['created_at'])}
                for r in cur.fetchall()]

    cur.close()
    conn.close()
    return teams, user_teams, users, unavailable, events, comments


def _fetch_sqlite(db_path):
    import sqlite3
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT id, name, COALESCE(description, '') FROM teams ORDER BY id")
    teams = [{'id': r[0], 'name': r[1], 'description': r[2]} for r in cur.fetchall()]

    cur.execute("SELECT user_id, team_id, is_team_admin FROM user_teams")
    user_teams = [{'user_id': r[0], 'team_id': r[1], 'is_team_admin': bool(r[2])} for r in cur.fetchall()]

    cur.execute("SELECT id, username, password_hash, color, is_admin FROM users ORDER BY id")
    users = [{'id': r[0], 'username': r[1], 'password_hash': r[2], 'color': r[3], 'is_admin': bool(r[4])} for r in cur.fetchall()]

    cur.execute("SELECT user_id, team_id, date FROM unavailable_dates")
    unavailable = [{'user_id': r[0], 'team_id': r[1], 'date': r[2]} for r in cur.fetchall()]

    cur.execute("""
        SELECT id, team_id, title, COALESCE(description, ''), date, end_date,
               created_by, organizer1_id, organizer2_id, created_at
        FROM group_events ORDER BY id
    """)
    events = [{'id': r[0], 'team_id': r[1], 'title': r[2], 'description': r[3],
               'date': r[4], 'end_date': r[5], 'created_by': r[6],
               'organizer1_id': r[7], 'organizer2_id': r[8], 'created_at': r[9]}
              for r in cur.fetchall()]

    cur.execute("SELECT event_id, user_id, text, is_hidden, created_at FROM event_comments ORDER BY id")
    comments = [{'event_id': r[0], 'user_id': r[1], 'text': r[2],
                 'is_hidden': bool(r[3]), 'created_at': r[4]}
                for r in cur.fetchall()]

    cur.close()
    conn.close()
    return teams, user_teams, users, unavailable, events, comments


def main():
    # ── Fetch from DB ────────────────────────────────────────────────────────
    if DATABASE_URL and not DATABASE_URL.startswith('sqlite'):
        try:
            teams, user_teams, users, unavailable, events, comments = _fetch_postgres(DATABASE_URL)
        except Exception as exc:
            print(f'⚠ Kunne ikke forbinde til PostgreSQL: {exc}')
            sys.exit(1)
    elif DATABASE_URL.startswith('sqlite:///'):
        db_path = DATABASE_URL.replace('sqlite:///', '')
        if not os.path.isabs(db_path):
            db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', db_path)
        if not os.path.exists(db_path):
            print('ℹ Ingen lokal SQLite-DB fundet — springer pre-deploy backup over')
            sys.exit(0)
        teams, user_teams, users, unavailable, events, comments = _fetch_sqlite(db_path)
    else:
        print('ℹ Ingen DATABASE_URL — springer pre-deploy backup over')
        sys.exit(0)

    if not users:
        print('ℹ DB er tom — ingen pre-deploy backup nødvendig')
        sys.exit(0)

    if not FTP_HOST or not FTP_USER or not FTP_PASS:
        print('⚠ FTP ikke konfigureret — kan ikke uploade pre-deploy backup')
        sys.exit(1)

    # ── Build payload ────────────────────────────────────────────────────────
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    payload = {
        'version': 2,
        'exported_at': datetime.utcnow().isoformat(),
        'pre_deploy': True,
        'teams':            teams,
        'user_teams':       user_teams,
        'users':            users,
        'unavailable_dates': unavailable,
        'group_events':     events,
        'event_comments':   comments,
    }
    file_data = json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')

    # ── Upload to FTP ────────────────────────────────────────────────────────
    try:
        ftp = ftplib.FTP_TLS(FTP_HOST, timeout=60)
        ftp.login(FTP_USER, FTP_PASS)
        ftp.prot_p()

        # Main backup — picked up by restore_from_backup() on startup
        ftp.cwd('/')
        _ftp_ensure_dir(ftp, FTP_PATH)
        ftp.storbinary('STOR calendar_backup.json', io.BytesIO(file_data))
        print(f'✓ Pre-deploy backup → {FTP_PATH}/calendar_backup.json')

        # Timestamped archive copy
        archive_dir = FTP_PATH.rstrip('/') + '/predeploy'
        ftp.cwd('/')
        _ftp_ensure_dir(ftp, archive_dir)
        ftp.storbinary(f'STOR {timestamp}.json', io.BytesIO(file_data))
        print(f'✓ Arkivkopi → {archive_dir}/{timestamp}.json')

        ftp.quit()
        print(f'✓ Pre-deploy backup fuldført ({len(users)} brugere, '
              f'{len(events)} events, {len(user_teams)} teammedlemskaber)')
    except Exception as exc:
        print(f'⚠ Pre-deploy FTP-upload fejlede: {exc}')
        sys.exit(1)


if __name__ == '__main__':
    main()
