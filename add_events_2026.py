"""
One-time script: Add the 2026 activity plan events to the database.
Run with:  python add_events_2026.py

Safe to re-run — skips events that already exist (same title + date).
"""

from datetime import date, datetime
from app import app, db, GroupEvent, write_backup

EVENTS = [
    {
        'title': 'Påskefrokost',
        'description': 'Fredag d. 13. marts 2026 – Budget: 7.000 kr.',
        'date': date(2026, 3, 13),
        'end_date': None,
        'created_by': 8,
    },
    {
        'title': 'Logearrangement',
        'description': 'Lørdag d. 23. maj 2026 – Budget: 7.000 kr.',
        'date': date(2026, 5, 23),
        'end_date': None,
        'created_by': 8,
    },
    {
        'title': 'Logearrangement',
        'description': 'Fredag d. 3. juli 2026 – Budget: 7.000 kr.',
        'date': date(2026, 7, 3),
        'end_date': None,
        'created_by': 8,
    },
    {
        'title': 'Logens årlige ferie',
        'description': 'Forlænget weekend uge 37 – tirsdag d. 8. til lørdag d. 12. september 2026. Budget: 20.000 kr.',
        'date': date(2026, 9, 8),
        'end_date': date(2026, 9, 12),
        'created_by': 8,
    },
    {
        'title': 'Julefrokost med Vandværksforeningen',
        'description': 'Fredag d. 6. november 2026 – Budget: 5.000 kr.',
        'date': date(2026, 11, 6),
        'end_date': None,
        'created_by': 8,
    },
    {
        'title': 'Jule/nytårs-hygge',
        'description': 'Søndag d. 27. december 2026 – Budget: 3.000 kr.',
        'date': date(2026, 12, 27),
        'end_date': None,
        'created_by': 8,
    },
    {
        'title': 'Generalforsamling 2027',
        'description': 'Fredag d. 29. til lørdag d. 30. januar 2027 – Budget: 10.000 kr.',
        'date': date(2027, 1, 29),
        'end_date': date(2027, 1, 30),
        'created_by': 8,
    },
]

with app.app_context():
    added = 0
    skipped = 0
    for ev in EVENTS:
        exists = GroupEvent.query.filter_by(title=ev['title'], date=ev['date']).first()
        if exists:
            print(f'  SKIP  {ev["date"]} – {ev["title"]}')
            skipped += 1
        else:
            ge = GroupEvent(
                title=ev['title'],
                description=ev['description'],
                date=ev['date'],
                end_date=ev['end_date'],
                created_by=ev['created_by'],
                created_at=datetime(2026, 3, 1, 12, 0, 0),
            )
            db.session.add(ge)
            print(f'  ADD   {ev["date"]} – {ev["title"]}')
            added += 1

    db.session.commit()
    print(f'\n✓ Færdig: {added} tilføjet, {skipped} sprunget over.')

    if added > 0:
        write_backup()
        print('✓ Backup opdateret.')
