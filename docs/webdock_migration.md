# Migration til Webdock

Denne guide beskriver, hvordan du flytter Ambrotos fra en eksisterende host
(Render, cPanel el.lign.) til en **Webdock VPS** med Ubuntu + Gunicorn + Nginx
og PostgreSQL.

---

## Forudsætninger

- En [Webdock-konto](https://webdock.io) med en Ubuntu 22.04 LTS VPS
  (nano eller micro er rigeligt til Ambrotos — ~€5/md)
- SSH-adgang til serveren
- Domæne der peger på serveren (A-record → serverens IP)

---

## Trin 1 — Klargør serveren

```bash
# Log ind
ssh root@<SERVER-IP>

# Opdater systemet
apt update && apt upgrade -y

# Installer nødvendige pakker
apt install -y python3.11 python3.11-venv python3-pip \
               nginx git postgresql postgresql-contrib \
               certbot python3-certbot-nginx ufw

# Firewall: tillad SSH, HTTP og HTTPS
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw enable
```

---

## Trin 2 — Opret en databasebruger og database

```bash
# Skift til postgres-brugeren
sudo -u postgres psql
```

Inden i psql:

```sql
CREATE USER ambrotos WITH PASSWORD 'SKIFT_MEG';
CREATE DATABASE ambrotos_db OWNER ambrotos;
\q
```

Gem forbindelsesstrengen til senere:
```
postgresql://ambrotos:SKIFT_MEG@localhost/ambrotos_db
```

---

## Trin 3 — Opret en systembruger og klargør app-mappen

```bash
# Opret bruger (ingen login-shell)
adduser --disabled-password --gecos "" ambrotos

# Skift til den nye bruger
su - ambrotos
```

Resten af trin 3–5 udføres som `ambrotos`-brugeren:

```bash
# Klon repo
git clone https://github.com/<DIN-ORG>/ambrotos.git ~/ambrotos
cd ~/ambrotos

# Opret virtualenv og installer afhængigheder
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn psycopg2-binary
```

---

## Trin 4 — Sæt miljøvariabler

```bash
# Opret .env-fil (aldrig commit denne fil)
cp .env.example .env
nano .env
```

Udfyld mindst disse:

```dotenv
SECRET_KEY=<lang-tilfaeldig-streng>          # openssl rand -hex 32
DATABASE_URL=postgresql://ambrotos:SKIFT_MEG@localhost/ambrotos_db

# Valgfrit — FTP-backup
FTP_HOST=ftp.jrgrafisk.dk
FTP_USER=<ftp-bruger>
FTP_PASS=<ftp-adgangskode>
FTP_PATH=/ambrotos
```

---

## Trin 5 — Test at appen starter

```bash
source venv/bin/activate

# Opret tabeller og seed data (første opstart)
python app.py &
sleep 3
kill %1
```

Hvis der ikke kommer fejl, er databasen klar.

---

## Trin 6 — Opret Gunicorn systemd-service

Tilbage som `root`:

```bash
nano /etc/systemd/system/ambrotos.service
```

Indsæt:

```ini
[Unit]
Description=Ambrotos Gunicorn-service
After=network.target postgresql.service

[Service]
User=ambrotos
Group=ambrotos
WorkingDirectory=/home/ambrotos/ambrotos
EnvironmentFile=/home/ambrotos/ambrotos/.env
ExecStart=/home/ambrotos/ambrotos/venv/bin/gunicorn \
          --workers 2 \
          --bind unix:/run/ambrotos.sock \
          app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Aktiver og start servicen:

```bash
systemctl daemon-reload
systemctl enable --now ambrotos

# Tjek status
systemctl status ambrotos
```

---

## Trin 7 — Konfigurer Nginx

```bash
nano /etc/nginx/sites-available/ambrotos
```

Indsæt (skift `DOMÆNE.dk`):

```nginx
server {
    listen 80;
    server_name DOMÆNE.dk www.DOMÆNE.dk;

    location / {
        proxy_pass         http://unix:/run/ambrotos.sock;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /home/ambrotos/ambrotos/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

Aktiver og genstart:

```bash
ln -s /etc/nginx/sites-available/ambrotos /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

---

## Trin 8 — HTTPS med Let's Encrypt

```bash
certbot --nginx -d DOMÆNE.dk -d www.DOMÆNE.dk
```

Certbot opdaterer automatisk Nginx-konfigurationen og sætter auto-fornyelse op.

---

## Trin 9 — Migrer eksisterende data

### Fra Render

1. Download backupfilen fra Render-appens URL:
   ```
   https://<din-render-app>.onrender.com/api/backup/download
   ```
   — eller kopier `data/calendar_backup.json` fra dit lokale repo.

2. Upload filen til serveren:
   ```bash
   scp data/calendar_backup.json ambrotos@<SERVER-IP>:~/ambrotos/data/
   ```

3. Genstart servicen — `restore_from_backup()` kører automatisk ved opstart
   og genopfylder tomme tabeller fra JSON-filen:
   ```bash
   systemctl restart ambrotos
   ```

### Fra cPanel/SQLite

Samme fremgangsmåde som ovenfor — sørg for at `calendar_backup.json` er
opdateret (kald en hvilken som helst skrive-operation på den gamle server
for at trigge `write_backup()` først).

---

## Daglig drift

| Opgave | Kommando |
|---|---|
| Se app-logs | `journalctl -u ambrotos -f` |
| Genstart efter deploy | `systemctl restart ambrotos` |
| Opdater kode | `cd ~/ambrotos && git pull && systemctl restart ambrotos` |
| Tjek Nginx-fejl | `tail -f /var/log/nginx/error.log` |

---

## Fejlfinding

### 502 Bad Gateway
- Gunicorn-processen kørte ikke: `systemctl status ambrotos`
- Socket-sti i Nginx matcher ikke `ExecStart` i service-filen

### Statiske filer virker ikke
- Tjek at `alias`-stien i Nginx peger på den rigtige mappe
- Kør `nginx -t` for syntaksfejl

### Databaseforbindelsesfejl
- Tjek at `DATABASE_URL` i `.env` matcher brugernavn/adgangskode fra trin 2
- Bekræft PostgreSQL kører: `systemctl status postgresql`

### Certbot fejler
- Sørg for at DNS A-record er propageret til serverens IP inden du kører certbot
- Tjek med: `dig +short DOMÆNE.dk`
