# Migration til OVH VPS

Denne guide migrerer Ambrotos fra Render til din eksisterende OVH VPS
der allerede kører pedalpricer.cc med Nginx og PM2.

Ambrotos kører som en **systemd-service** (ingen Docker, samme mønster som
pedalpricer.cc men med systemd i stedet for PM2).

---

## Overblik

```
Internet → Nginx (port 80/443) → Gunicorn (port 8000) → Flask/Ambrotos
                                        ↕
                                  PostgreSQL (lokal)
```

---

## Del 1 — PostgreSQL

```bash
sudo apt update
sudo apt install -y postgresql postgresql-client
```

Opret database og bruger:

```bash
sudo -u postgres psql
```

```sql
CREATE USER ambrotos WITH PASSWORD 'SKIFT_MEG';
CREATE DATABASE ambrotos_db OWNER ambrotos;
\q
```

Test forbindelsen:

```bash
psql -U ambrotos -d ambrotos_db -h localhost -c "SELECT 1;"
```

---

## Del 2 — Applikation

### 2.1 Hent koden

```bash
cd /var/www
sudo git clone https://github.com/jrgrafisk/ambrotos.git ambrotos
sudo chown -R $USER:$USER /var/www/ambrotos
```

### 2.2 Python-miljø

```bash
cd /var/www/ambrotos
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt gunicorn psycopg2-binary
deactivate
```

### 2.3 Miljøvariabler

```bash
nano /var/www/ambrotos/.env
```

```dotenv
SECRET_KEY=<kør: python3 -c "import secrets; print(secrets.token_hex(32))">
DATABASE_URL=postgresql://ambrotos:SKIFT_MEG@localhost/ambrotos_db

# FTP-backup (valgfrit — brug dine eksisterende værdier fra Render)
FTP_HOST=ftp.jrgrafisk.dk
FTP_USER=<ftp-bruger>
FTP_PASS=<ftp-adgangskode>
FTP_PATH=/ambrotos
```

Beskyt filen:

```bash
chmod 600 /var/www/ambrotos/.env
```

---

## Del 3 — systemd-service

Opret service-filen:

```bash
sudo nano /etc/systemd/system/ambrotos.service
```

```ini
[Unit]
Description=Ambrotos Kalender
After=network.target postgresql.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/var/www/ambrotos
EnvironmentFile=/var/www/ambrotos/.env
ExecStart=/var/www/ambrotos/venv/bin/gunicorn \
    --workers 2 \
    --bind 127.0.0.1:8000 \
    --access-logfile /var/log/ambrotos/access.log \
    --error-logfile /var/log/ambrotos/error.log \
    app:app
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

Opret log-mappe og sæt rettigheder:

```bash
sudo mkdir -p /var/log/ambrotos
sudo chown www-data:www-data /var/log/ambrotos
sudo chown -R www-data:www-data /var/www/ambrotos
```

Aktivér og start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable ambrotos      # starter automatisk ved reboot
sudo systemctl start ambrotos
sudo systemctl status ambrotos      # bør vise "active (running)"
```

### Nyttige kommandoer (systemd vs PM2)

| Opgave | systemd | PM2 |
|---|---|---|
| Start | `sudo systemctl start ambrotos` | `pm2 start ambrotos` |
| Stop | `sudo systemctl stop ambrotos` | `pm2 stop ambrotos` |
| Genstart | `sudo systemctl restart ambrotos` | `pm2 restart ambrotos` |
| Status | `sudo systemctl status ambrotos` | `pm2 status` |
| Logs (live) | `sudo journalctl -u ambrotos -f` | `pm2 logs ambrotos` |
| Logs (seneste) | `sudo journalctl -u ambrotos -n 100` | `pm2 logs ambrotos --lines 100` |
| Start ved reboot | `sudo systemctl enable ambrotos` | `pm2 save && pm2 startup` |

---

## Del 4 — Nginx

Tilføj et nyt server-block. Find din eksisterende Nginx-konfigurationsmappe:

```bash
ls /etc/nginx/sites-available/
```

Opret ny konfiguration:

```bash
sudo nano /etc/nginx/sites-available/ambrotos
```

```nginx
server {
    listen 80;
    server_name ambrotos.jrgrafisk.dk;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}
```

Aktivér og test:

```bash
sudo ln -s /etc/nginx/sites-available/ambrotos /etc/nginx/sites-enabled/
sudo nginx -t                   # bør sige "syntax is ok"
sudo systemctl reload nginx
```

---

## Del 5 — SSL med Certbot

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d ambrotos.jrgrafisk.dk
```

Certbot opdaterer automatisk Nginx-konfigurationen og sætter auto-fornyelse op.

Test fornyelse:

```bash
sudo certbot renew --dry-run
```

---

## Del 6 — Data-migration

Data migreres via FTP-backuppen — ingen direkte SQL-export fra Render nødvendig.

### 6.1 Kør en backup på Render inden du skifter

Log ind på `https://ambrotos.onrender.com/admin` → klik **💾 Backup nu**.
Dette gemmer et tidsstemplet arkiv i `/ambrotos/manualbackup/` på FTP.

### 6.2 Gendan data på OVH

Når appen kører på OVH:

1. Gå til `https://ambrotos.jrgrafisk.dk/admin`
2. Klik **↩ Gendan fra backup**
3. Vælg den manuelle backup du netop lavede
4. Klik **Gendan**

Alternativt gendannes data automatisk ved første opstart hvis
`FTP_HOST`/`FTP_USER`/`FTP_PASS` er sat i `.env` — appen downloader
`calendar_backup.json` fra FTP og populerer den tomme database.

---

## Del 7 — DNS-skift

Find din OVH VPS's IP:

```bash
curl -4 ifconfig.me
```

Gå til din DNS-udbyder og opdater:

| Navn | Type | Værdi |
|---|---|---|
| `ambrotos.jrgrafisk.dk` | A | `<OVH VPS IP>` |

DNS-propagering tager typisk 5-30 minutter. Render fortsætter med at
fungere indtil propagering er sket, så der er ingen nedetid.

---

## Del 8 — Opdateringer fremover

```bash
cd /var/www/ambrotos
git pull
source venv/bin/activate
pip install -r requirements.txt   # kun ved nye dependencies
deactivate
sudo systemctl restart ambrotos
```

---

## Fejlfinding

| Problem | Løsning |
|---|---|
| Service starter ikke | `sudo journalctl -u ambrotos -n 50` |
| 502 Bad Gateway | Gunicorn kører ikke — tjek `systemctl status ambrotos` |
| DB-forbindelsesfejl | Tjek `DATABASE_URL` i `.env` og at PostgreSQL kører |
| SSL fejler | DNS er ikke propageret endnu — vent og prøv igen |
| Rettigheder | `sudo chown -R www-data:www-data /var/www/ambrotos` |
