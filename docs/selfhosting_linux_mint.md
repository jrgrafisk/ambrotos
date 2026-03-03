# Selfhosting på Linux Mint

Denne guide sætter din Linux Mint-maskine op som en hjemmeserver der kan køre
**Ambrotos** og andre tjenester som **Immich** — via Docker og Nginx Proxy Manager.

Arkitekturen er simpel:
```
Internet → Router (port 80/443) → Nginx Proxy Manager → [Ambrotos, Immich, ...]
```

Alt kører i Docker-containere, så tjenester er isolerede og nemme at opdatere.

---

## Del 1 — Klargør Linux Mint-maskinen

### 1.1 Statisk lokal IP

Giv serveren en fast lokal IP, så router-viderestillingen ikke falder ud.

Åbn **Network Manager** (systembakken) → din forbindelse → **Edit** →
fanen **IPv4**:

| Felt | Værdi (eksempel) |
|---|---|
| Method | Manual |
| Address | `192.168.1.100` |
| Netmask | `255.255.255.0` |
| Gateway | `192.168.1.1` (din routers IP) |
| DNS | `1.1.1.1, 8.8.8.8` |

Klik **Save** og genopret forbindelsen.

> Alternativt: Sæt en DHCP-reservation i routerens admin-panel baseret på
> maskinens MAC-adresse — det er renere og ændrer intet i Linux.

### 1.2 Aktiver SSH (valgfrit men anbefalet)

```bash
sudo apt install -y openssh-server
sudo systemctl enable --now ssh
```

Du kan nu styre serveren fra en anden maskine:
```bash
ssh bruger@192.168.1.100
```

### 1.3 Automatisk login + skærmskåner fra

Hvis maskinen ikke har et tastatur til daglig:

**Systemindstillinger → Login Window → Automatisk login → aktivér**

**Systemindstillinger → Screensaver → deaktivér**

---

## Del 2 — Installer Docker

```bash
# Fjern eventuelle gamle versioner
sudo apt remove -y docker docker-engine docker.io containerd runc

# Tilføj Dockers officielle repo
sudo apt install -y ca-certificates curl gnupg lsb-release
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Ubuntu-version Linux Mint er baseret på (Mint 21 → Ubuntu 22.04 "jammy")
echo "deb [arch=$(dpkg --print-architecture) \
  signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  jammy stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io \
                    docker-buildx-plugin docker-compose-plugin

# Tilføj din bruger til docker-gruppen (undgår sudo ved hvert kommando)
sudo usermod -aG docker $USER
newgrp docker

# Test
docker run --rm hello-world
```

> **Mint 21** → Ubuntu jammy. **Mint 22** → Ubuntu noble. Skift `jammy`
> til `noble` i repo-linjen hvis du bruger Mint 22.

---

## Del 3 — Dynamisk DNS

Din hjemme-IP skifter jævnligt. En DDNS-tjeneste holder et domænenavn
opdateret automatisk.

### 3.1 Vælg en DDNS-tjeneste

| Tjeneste | Pris | Eget domæne |
|---|---|---|
| **DuckDNS** | Gratis | Nej (fx `mitthold.duckdns.org`) |
| **Cloudflare** | Gratis | Ja (kræver eget domæne) |
| **No-IP** | Gratis (skal fornyes) | Valgfrit |

Nedenstående bruger **DuckDNS** (nemmest til at komme i gang).

### 3.2 DuckDNS-opsætning

1. Gå til [duckdns.org](https://www.duckdns.org) → log ind med Google/GitHub
2. Opret et subdomæne, fx `mitthold.duckdns.org`
3. Kopiér dit **token**

Opret opdaterings-scriptet:

```bash
mkdir -p ~/duckdns
nano ~/duckdns/duck.sh
```

Indsæt (erstat `DITTOKEN` og `DITSUBDOMÆNE`):

```bash
#!/bin/bash
echo url="https://www.duckdns.org/update?domains=DITSUBDOMÆNE&token=DITTOKEN&ip=" \
  | curl -k -o ~/duckdns/duck.log -K -
```

```bash
chmod +x ~/duckdns/duck.sh

# Kør hver 5. minut via cron
crontab -e
```

Tilføj nederst:
```
*/5 * * * * ~/duckdns/duck.sh >/dev/null 2>&1
```

### 3.3 Port-viderestilling i routeren

Log ind i routerens admin-panel (typisk `192.168.1.1`) og viderestil:

| Ekstern port | Intern IP | Intern port | Protokol |
|---|---|---|---|
| 80 | 192.168.1.100 | 80 | TCP |
| 443 | 192.168.1.100 | 443 | TCP |

> Fremgangsmåden varierer efter routermodel. Søg på
> `<din router model> port forwarding`.

---

## Del 4 — Nginx Proxy Manager

Nginx Proxy Manager (NPM) håndterer HTTPS-certifikater og videresender trafik
til de rigtige containere — alt via et browser-UI.

### 4.1 Opret mappe og compose-fil

```bash
mkdir -p ~/docker/nginx-proxy-manager
nano ~/docker/nginx-proxy-manager/compose.yml
```

```yaml
services:
  npm:
    image: jc21/nginx-proxy-manager:latest
    container_name: nginx-proxy-manager
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
      - "81:81"        # NPM's admin-UI
    volumes:
      - ./data:/data
      - ./letsencrypt:/etc/letsencrypt

networks:
  default:
    name: proxy
    external: true
```

### 4.2 Opret det delte Docker-netværk og start NPM

```bash
docker network create proxy

cd ~/docker/nginx-proxy-manager
docker compose up -d
```

### 4.3 Log ind i NPM

Åbn `http://192.168.1.100:81` i en browser.

Standard-login:
- E-mail: `admin@example.com`
- Kodeord: `changeme`

**Skift straks e-mail og kodeord** under Account → Change Password.

---

## Del 5 — Ambrotos

### 5.1 Opret mappe og hent kode

```bash
mkdir -p ~/docker/ambrotos
cd ~/docker/ambrotos
git clone https://github.com/<DIN-ORG>/ambrotos.git app
```

### 5.2 Miljøvariabler

```bash
cp app/.env.example app/.env
nano app/.env
```

```dotenv
SECRET_KEY=<lang-tilfaeldig-streng>   # openssl rand -hex 32
DATABASE_URL=postgresql://ambrotos:SKIFT_MEG@db/ambrotos_db

# Valgfrit — FTP-backup
FTP_HOST=ftp.jrgrafisk.dk
FTP_USER=<ftp-bruger>
FTP_PASS=<ftp-adgangskode>
FTP_PATH=/ambrotos
```

### 5.3 Docker Compose

```bash
nano ~/docker/ambrotos/compose.yml
```

```yaml
services:
  web:
    build: ./app
    container_name: ambrotos
    restart: unless-stopped
    env_file: ./app/.env
    volumes:
      - ./data:/app/data          # backup JSON
      - ./instance:/app/instance  # SQLite (bruges ikke med PostgreSQL)
    depends_on:
      db:
        condition: service_healthy
    networks:
      - proxy
      - internal

  db:
    image: postgres:16-alpine
    container_name: ambrotos_db
    restart: unless-stopped
    environment:
      POSTGRES_USER: ambrotos
      POSTGRES_PASSWORD: SKIFT_MEG
      POSTGRES_DB: ambrotos_db
    volumes:
      - ./pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ambrotos"]
      interval: 5s
      retries: 10
    networks:
      - internal

networks:
  proxy:
    external: true
  internal:
```

### 5.4 Start Ambrotos

```bash
cd ~/docker/ambrotos
docker compose up -d --build
```

### 5.5 Opret proxy-host i NPM

1. NPM → **Proxy Hosts** → **Add Proxy Host**
2. Udfyld:

| Felt | Værdi |
|---|---|
| Domain Names | `kalender.mitthold.duckdns.org` |
| Scheme | `http` |
| Forward Hostname | `ambrotos` (container-navn) |
| Forward Port | `8000` |
| Websockets Support | til |

3. Fanen **SSL** → **Request a new SSL Certificate** → **Force SSL** → **Save**

Ambrotos er nu tilgængeligt på `https://kalender.mitthold.duckdns.org`.

---

## Del 6 — Immich

Immich kræver sin egen PostgreSQL-instans og Redis — alt medfølger i den
officielle compose-fil.

### 6.1 Hent den officielle compose-fil

```bash
mkdir -p ~/docker/immich
cd ~/docker/immich

curl -L https://github.com/immich-app/immich/releases/latest/download/docker-compose.yml \
  -o compose.yml
curl -L https://github.com/immich-app/immich/releases/latest/download/example.env \
  -o .env
```

### 6.2 Tilpas .env

```bash
nano .env
```

Minimum at ændre:

```dotenv
# Sti til billedbiblioteket på din server
UPLOAD_LOCATION=/home/<DIT-BRUGERNAVN>/immich-bibliotek

# Stærkt kodeord til Immich's interne PostgreSQL
DB_PASSWORD=SKIFT_MEG_IMMICH
```

### 6.3 Tilføj proxy-netværk til Immich

```bash
nano compose.yml
```

Find `immich-server`-servicen og tilføj `proxy`-netværket:

```yaml
# Tilføj under immich-server:
    networks:
      - default
      - proxy

# Tilføj nederst i filen:
networks:
  default:
  proxy:
    external: true
```

### 6.4 Start Immich

```bash
cd ~/docker/immich
docker compose up -d
```

Første start tager et par minutter mens images hentes.

### 6.5 Opret proxy-host til Immich i NPM

| Felt | Værdi |
|---|---|
| Domain Names | `billeder.mitthold.duckdns.org` |
| Forward Hostname | `immich-server` |
| Forward Port | `2283` |
| Websockets Support | til |

SSL: **Request a new SSL Certificate** → **Force SSL** → **Save**.

Besøg `https://billeder.mitthold.duckdns.org` og opret admin-bruger.

---

## Del 7 — Opdateringer

### Ambrotos

```bash
cd ~/docker/ambrotos/app
git pull
cd ..
docker compose up -d --build
```

### Immich

```bash
cd ~/docker/immich
docker compose pull
docker compose up -d
```

### Nginx Proxy Manager

```bash
cd ~/docker/nginx-proxy-manager
docker compose pull
docker compose up -d
```

---

## Del 8 — Automatisk opstart efter genstart

Docker er allerede sat til at starte med systemet. Alle containere med
`restart: unless-stopped` starter automatisk igen.

Verificér:

```bash
sudo systemctl is-enabled docker   # → enabled
docker ps                          # vis kørende containere
```

---

## Del 9 — Backup

### Ambrotos-data

`~/docker/ambrotos/data/calendar_backup.json` indeholder al kalenderdata og
opdateres automatisk af appen. Den er lille nok til at ligge i git.

PostgreSQL-dump (kør fx ugentligt):

```bash
docker exec ambrotos_db pg_dump -U ambrotos ambrotos_db \
  > ~/backups/ambrotos_$(date +%F).sql
```

### Immich

Immich's egne [backup-anbefalinger](https://immich.app/docs/administration/backup-and-restore):

```bash
# Databasedump
docker exec immich_postgres pg_dumpall -U postgres \
  > ~/backups/immich_$(date +%F).sql

# Selve billederne — synkroniseres bedst med rsync til en ekstern disk:
rsync -av ~/immich-bibliotek/ /media/ekstern-disk/immich-backup/
```

---

## Tilføj en ny tjeneste (generelt mønster)

1. Opret `~/docker/<tjeneste>/compose.yml`
2. Tilføj containeren til `proxy`-netværket
3. Kør `docker compose up -d`
4. Tilføj en ny Proxy Host i NPM med det ønskede subdomæne
5. Anmod om SSL-certifikat

Eksempler på andre populære tjenester der følger dette mønster:
- **Vaultwarden** (Bitwarden-server)
- **Nextcloud** (fildeling)
- **Grafana + Prometheus** (overvågning)
- **Gitea** (privat git)
- **Paperless-ngx** (dokumenthåndtering)

---

## Fejlfinding

| Problem | Løsning |
|---|---|
| Port 80/443 svarer ikke udefra | Tjek port-viderestilling i routeren; tjek UFW |
| SSL-certifikat fejler | DNS er ikke propageret endnu; vent og prøv igen |
| Container starter ikke | `docker compose logs <service>` |
| Ambrotos kan ikke nå databasen | `docker network inspect proxy`; tjek `internal`-netværk |
| Immich meget langsom | Slå hardware-acceleration til i Immich-indstillinger |
| Dynamsik DNS opdateres ikke | `cat ~/duckdns/duck.log` — bør indeholde `OK` |
