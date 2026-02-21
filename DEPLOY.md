# Deployment på cPanel (jrgrafisk.dk)

Denne guide antager at dit webhotel bruger cPanel med **"Setup Python App"**
(kræver Phusion Passenger — de fleste moderne cPanel-hosts understøtter det).

---

## Trin 1 — Upload filer

Upload hele projektmappen til din server, f.eks. via:

- **cPanel File Manager** → opret mappen `ambrotos/` under `public_html/` og upload alle filer
- **FTP** (FileZilla el.lign.) til samme placering

Resulterende struktur på serveren:
```
~/public_html/ambrotos/
├── app.py
├── passenger_wsgi.py
├── requirements.txt
├── static/
├── templates/
└── ...
```

---

## Trin 2 — Opret Python App i cPanel

1. Log ind i cPanel → find **"Setup Python App"** (under Software)
2. Klik **"Create Application"**
3. Udfyld felterne:

| Felt | Værdi |
|---|---|
| Python version | **3.11** (eller nyeste tilgængelige) |
| Application root | `public_html/ambrotos` |
| Application URL | Vælg domæne + evt. understi, f.eks. `jrgrafisk.dk` eller `jrgrafisk.dk/kalender` |
| Application startup file | `passenger_wsgi.py` |
| Application Entry point | `application` |

4. Klik **"Create"**

---

## Trin 3 — Installer afhængigheder

Når appen er oprettet viser cPanel en kommando-linje du kan køre i terminalen.
Den ligner:

```bash
source /home/BRUGER/virtualenvs/ambrotos/bin/activate
```

Klik på det lille terminal-ikon i Setup Python App (eller brug SSH) og kør:

```bash
cd ~/public_html/ambrotos
pip install -r requirements.txt
```

---

## Trin 4 — Sæt miljøvariabler

Stadig i **Setup Python App**, rul ned til **"Environment variables"** og tilføj:

| Name | Value |
|---|---|
| `ANTHROPIC_API_KEY` | Din API-nøgle fra console.anthropic.com |
| `SECRET_KEY` | En lang tilfældig streng, f.eks. `openssl rand -hex 32` |

Klik **"Save"**.

---

## Trin 5 — Genstart og test

Klik **"Restart"** i Setup Python App.

Besøg din URL (f.eks. `https://jrgrafisk.dk/kalender`) — siden bør vise login-skærmen.

> **Første opstart**: Databasen og alle 14 brugere oprettes automatisk.
> Log ind med f.eks. `Anders` og adgangskoden `kodeordetersvært`.

---

## Fejlfinding

### Siden viser "500 Internal Server Error"
- Tjek **cPanel → Error Logs** (under Metrics/Logs)
- Mest sandsynlig årsag: `ANTHROPIC_API_KEY` er ikke sat korrekt

### "ModuleNotFoundError"
- Pip-pakker er ikke installeret i det rigtige virtualenv
- Kør `pip install -r requirements.txt` igen via terminal i cPanel

### Database-fejl
- Sørg for at mappen `~/public_html/ambrotos/` er skrivbar
- Flask opretter automatisk `instance/calendar.db` første gang

### Appen opdateres ikke efter fil-ændringer
- Klik **"Restart"** i Setup Python App
- Passenger indlæser koden ved genstart

---

## Vigtig note om delt hosting

cPanel shared hosting har typisk:
- **Timeouts på 30–60 sek** — Claude API-kaldet tager normalt 2–5 sek, så det er fint
- **Begrænsninger på parallelle requests** — tilstrækkeligt til en intern holdkalender

Hvis du har mange samtidige brugere, kan en VPS (DigitalOcean, Hetzner) evt. give bedre ydeevne.
