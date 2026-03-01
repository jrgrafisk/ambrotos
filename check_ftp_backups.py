#!/usr/bin/env python3
"""
Diagnostik: Hent alle backup-filer fra FTP og vis indhold.
Kør med: python check_ftp_backups.py
"""
import ftplib
import io
import json
import os
import sys

FTP_HOST = os.environ.get('FTP_HOST', 'ftp.jrgrafisk.dk')
FTP_USER = os.environ.get('FTP_USER', '')
FTP_PASS = os.environ.get('FTP_PASS', '')
FTP_PATH = os.environ.get('FTP_PATH', '/customers/5/2/d/jrgrafisk.dk/httpd.www/ambrotos')

if not FTP_USER or not FTP_PASS:
    print("Angiv FTP-credentials:")
    FTP_USER = input("  FTP_USER: ").strip()
    FTP_PASS = input("  FTP_PASS: ").strip()

FILES = [
    'calendar_backup.json',
    'calendar_backup_1.json',
    'calendar_backup_2.json',
    'calendar_backup_3.json',
]

print(f"\n→ Forbinder til {FTP_HOST}:{FTP_PATH} ...\n")
try:
    ftp = ftplib.FTP_TLS(FTP_HOST, timeout=30)
    ftp.login(FTP_USER, FTP_PASS)
    ftp.prot_p()
    ftp.cwd(FTP_PATH)
except Exception as e:
    print(f"FTP-fejl: {e}")
    sys.exit(1)

backups = {}
for fname in FILES:
    buf = io.BytesIO()
    try:
        ftp.retrbinary(f'RETR {fname}', buf.write)
        buf.seek(0)
        data = json.loads(buf.read().decode('utf-8'))
        backups[fname] = data
        ud = data.get('unavailable_dates', [])
        ge = data.get('group_events', [])
        users = data.get('users', [])
        ts = data.get('exported_at', '?')
        print(f"✓ {fname}")
        print(f"    exported_at:     {ts}")
        print(f"    brugere:         {len(users)}")
        print(f"    unavailable:     {len(ud)}")
        print(f"    group events:    {len(ge)}")
        print()
    except ftplib.error_perm:
        print(f"  (filen {fname} findes ikke på FTP)\n")
    except Exception as e:
        print(f"  Fejl ved {fname}: {e}\n")

ftp.quit()

if not backups:
    print("Ingen backup-filer fundet på FTP.")
    sys.exit(1)

# Find nyeste backup (mest unavailable dates eller nyeste timestamp)
best = max(backups.items(), key=lambda x: (
    len(x[1].get('unavailable_dates', [])),
    x[1].get('exported_at', '')
))
best_name, best_data = best
print(f"─────────────────────────────────────────")
print(f"Anbefalet backup: {best_name}")
print(f"  ({len(best_data.get('unavailable_dates',[]))} unavailable dates, {best_data.get('exported_at','?')})")
print()

# Gem den anbefalede backup lokalt
save = input("Gem denne backup lokalt som data/calendar_backup.json? [j/n]: ").strip().lower()
if save == 'j':
    os.makedirs('data', exist_ok=True)
    with open('data/calendar_backup.json', 'w', encoding='utf-8') as f:
        json.dump(best_data, f, ensure_ascii=False, indent=2)
    print("✓ Gemt. Start appen igen for at gendanne data.")
    print()
    print("Unavailable dates i den valgte backup:")
    for ud in sorted(best_data.get('unavailable_dates', []), key=lambda x: x['date']):
        print(f"  user_id={ud['user_id']}  {ud['date']}")
