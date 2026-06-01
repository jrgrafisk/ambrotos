# Migration from Render to OVH VPS

This guide will help you migrate your Ambrotos calendar application from Render to an OVH VPS.

## Overview

**Current (Render):**
- Free tier web service with Gunicorn
- Free PostgreSQL database
- Automatic deployments from GitHub
- Environment variables managed in Render dashboard

**Target (OVH VPS):**
- Self-managed VPS with Docker
- PostgreSQL database in Docker container
- Nginx as reverse proxy with SSL
- Full control over configuration and data

## Prerequisites

1. **OVH VPS** - Purchase and provision an OVH VPS (any tier, Ubuntu 22.04 LTS recommended)
2. **Domain name** - Point your domain to the VPS IP address
3. **SSH access** - Root or sudo access to your VPS
4. **SSL certificate** - Free from Let's Encrypt (we'll set this up)

## Step 1: Prepare Your OVH VPS

### Connect to your VPS
```bash
ssh root@your-vps-ip-address
```

### Update system and install dependencies
```bash
# Update packages
apt update && apt upgrade -y

# Install Docker and Docker Compose
apt install -y docker.io docker-compose-plugin curl git

# Add your user to docker group (optional, to run docker without sudo)
usermod -aG docker $USER
newgrp docker

# Verify installation
docker --version
docker compose version
```

### Install Certbot for SSL certificates
```bash
apt install -y certbot python3-certbot-nginx
```

## Step 2: Clone Your Repository

```bash
# Clone your repository (replace with your actual repo URL)
git clone https://github.com/jrgrafisk/ambrotos.git /opt/ambrotos
cd /opt/ambrotos

# Check out the branch you want to deploy
git checkout main  # or your specific branch
```

## Step 3: Configure Environment

### Create .env file
```bash
# Copy the OVH template
cp .env.ovh .env

# Edit the .env file with your actual values
nano .env
```

Set these values in `.env`:
```
ANTHROPIC_API_KEY=your_actual_anthropic_api_key
SECRET_KEY=$(openssl rand -hex 32)  # Generate a new one
POSTGRES_PASSWORD=your_strong_password_here
FTP_HOST=ftp.jrgrafisk.dk
FTP_USER=your_ftp_username
FTP_PASS=your_ftp_password
FTP_PATH=/customers/5/2/d/jrgrafisk.dk/httpd.www/ambrotos
```

## Step 4: Database Migration from Render

### Option A: Export from Render and Import to OVH (Recommended)

1. **Export data from Render PostgreSQL:**
   - Go to Render dashboard → your PostgreSQL database
   - Use the "Connect" tab to find connection details
   - Export your data using pg_dump:
   ```bash
   # On your local machine or Render shell
   pg_dump -h your-render-db-host -U your-render-db-user -d ambrotos-db > ambrotos_backup.sql
   ```

2. **Copy the backup to your VPS:**
   ```bash
   # From your local machine
   scp ambrotos_backup.sql root@your-vps-ip:/opt/ambrotos/
   ```

3. **Start PostgreSQL container temporarily:**
   ```bash
   cd /opt/ambrotos
   docker compose up -d db
   ```

4. **Import the data:**
   ```bash
   # Wait 30 seconds for PostgreSQL to start
   sleep 30
   
   # Import the backup
   docker exec -i ambrotos-db psql -U ambrotos -d ambrotos < ambrotos_backup.sql
   ```

### Option B: Start Fresh (Lose existing data)

If you don't need to preserve existing data, simply start the containers and the app will create a fresh database:
```bash
docker compose up -d db
```

## Step 5: Start the Application

### Start all services
```bash
cd /opt/ambrotos
docker compose up -d
```

### Verify containers are running
```bash
docker compose ps
# Should show: web, db, and nginx containers running
```

### Check logs
```bash
# View web app logs
docker compose logs web

# View database logs
docker compose logs db

# View nginx logs
docker compose logs nginx
```

## Step 6: Set Up SSL with Let's Encrypt

### Temporarily stop Nginx in Docker
```bash
docker compose stop nginx
```

### Install SSL certificate
```bash
# Create SSL directory
mkdir -p /opt/ambrotos/ssl

# Get certificate (replace with your domain)
certbot certonly --standalone -d your-domain.com -d www.your-domain.com

# Copy certificate to your project
cp /etc/letsencrypt/live/your-domain.com/fullchain.pem /opt/ambrotos/ssl/
cp /etc/letsencrypt/live/your-domain.com/privkey.pem /opt/ambrotos/ssl/

# Set proper permissions
chmod 600 /opt/ambrotos/ssl/privkey.pem
```

### Restart Nginx
```bash
cd /opt/ambrotos
docker compose up -d nginx
```

### Set up automatic certificate renewal
```bash
# Test renewal
certbot renew --dry-run

# Add cron job for automatic renewal
crontab -e
```

Add this line to run renewal twice daily (it will only renew when near expiry):
```
0 */12 * * * /usr/bin/certbot renew --quiet --post-hook "docker compose -f /opt/ambrotos/docker-compose.yml restart nginx"
```

## Step 7: Configure Firewall

```bash
# Allow HTTP, HTTPS, and SSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 22/tcp

# Enable firewall
ufw enable

# Check status
ufw status
```

## Step 8: Run Pre-Deploy Script

Your app has a `pre_deploy.py` script that needs to run:
```bash
# Run it inside the web container
docker compose exec web python pre_deploy.py
```

## Step 9: Test Your Application

Visit `https://your-domain.com` in your browser. You should see the Ambrotos login screen.

## Step 10: Set Up Automatic Updates (Optional)

### Option A: Git Pull + Restart
```bash
# Create update script
cat > /opt/ambrotos/update.sh << 'EOF'
#!/bin/bash
cd /opt/ambrotos
git pull origin main
docker compose down
docker compose up -d --build
docker compose exec web python pre_deploy.py
EOF

chmod +x /opt/ambrotos/update.sh
```

### Option B: Watchtower for automatic Docker updates
```bash
# Create docker-compose.watchtower.yml
echo 'version: "3.8"
services:
  watchtower:
    image: containrrr/watchtower
    container_name: watchtower
    restart: unless-stopped
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    command: --interval 30 --cleanup
' > /opt/ambrotos/docker-compose.watchtower.yml

# Start watchtower
docker compose -f docker-compose.watchtower.yml up -d
```

## Step 11: Backup Strategy

### Database backups
```bash
# Create backup script
cat > /opt/ambrotos/backup.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
cd /opt/ambrotos

# Backup database
docker exec ambrotos-db pg_dump -U ambrotos -d ambrotos > backups/ambrotos_db_$DATE.sql

# Backup data directory
mkdir -p backups/data
tar -czf backups/data_$DATE.tar.gz data/

# Keep only last 7 backups
ls -t backups/ | tail -n +8 | xargs -I {} rm backups/{}
EOF

chmod +x /opt/ambrotos/backup.sh
mkdir -p /opt/ambrotos/backups

# Add to cron (daily at 2 AM)
crontab -e
```

Add this line:
```
0 2 * * * /opt/ambrotos/backup.sh
```

## Migration Checklist

- [ ] OVH VPS provisioned and accessible via SSH
- [ ] Docker and Docker Compose installed
- [ ] Repository cloned to VPS
- [ ] Environment variables configured in .env
- [ ] Database migrated from Render (or fresh start)
- [ ] Docker containers running (web, db, nginx)
- [ ] SSL certificate obtained and configured
- [ ] Firewall configured
- [ ] Pre-deploy script executed
- [ ] Application tested and working
- [ ] Domain DNS pointing to VPS IP
- [ ] Backup strategy in place
- [ ] Update strategy configured

## Troubleshooting

### "Connection refused" to database
```bash
# Check if db container is running
docker compose ps

# Check db logs
docker compose logs db

# Test connection manually
docker compose exec web python -c "import psycopg2; conn = psycopg2.connect('postgresql://ambrotos:your_password@db:5432/ambrotos'); print('Connected!'); conn.close()"
```

### Nginx 502 Bad Gateway
```bash
# Check nginx logs
docker compose logs nginx

# Test if web app is accessible directly
docker compose exec web curl -I http://localhost:8000

# Check if nginx can reach web
docker compose exec nginx curl -I http://web:8000
```

### SSL issues
```bash
# Check SSL configuration
docker compose exec nginx nginx -t

# Verify certificate files exist and are readable
ls -la /opt/ambrotos/ssl/
```

### Application errors
```bash
# Check web app logs
docker compose logs web

# View real-time logs
docker compose logs -f web
```

## Rollback Plan

If something goes wrong, you can quickly roll back:

1. **Stop all containers:**
   ```bash
   cd /opt/ambrotos
   docker compose down
   ```

2. **Restore from backup:**
   ```bash
   # Restore database
   docker compose up -d db
   sleep 30
   docker exec -i ambrotos-db psql -U ambrotos -d ambrotos < backups/ambrotos_db_LATEST.sql
   
   # Restart web
   docker compose up -d web
   ```

3. **Point DNS back to Render** (if you changed it)

## Performance Tips

1. **Increase Gunicorn workers** (in docker-compose.yml):
   ```yaml
   command: gunicorn --workers 4 --bind 0.0.0.0:8000 app:app
   ```

2. **Add more memory** to your VPS if you have many users

3. **Use a CDN** for static files if serving many users globally

## Cost Comparison

| Service | Render (Free) | OVH VPS (Entry) |
|---------|---------------|-----------------|
| Monthly Cost | $0 | ~€3.99-€9.99 |
| Database | Free PostgreSQL | Self-managed PostgreSQL |
| Control | Limited | Full control |
| Performance | Shared resources | Dedicated resources |
| Scalability | Limited | Can scale up |
| SSL | Automatic | Manual setup |

## Next Steps

1. **Monitor** your application logs
2. **Set up monitoring** (e.g., UptimeRobot for HTTP checks)
3. **Consider backups** to external storage (FTP, S3, etc.)
4. **Update regularly** to keep dependencies secure

---

## Quick Start Commands Summary

```bash
# 1. Connect to VPS
ssh root@your-vps-ip

# 2. Install dependencies
apt update && apt upgrade -y && apt install -y docker.io docker-compose-plugin certbot git

# 3. Clone repo
git clone https://github.com/jrgrafisk/ambrotos.git /opt/ambrotos
cd /opt/ambrotos

# 4. Configure
cp .env.ovh .env
nano .env  # Edit with your values

# 5. Start services
docker compose up -d

# 6. Get SSL
mkdir -p ssl
certbot certonly --standalone -d your-domain.com
cp /etc/letsencrypt/live/your-domain.com/fullchain.pem ssl/
cp /etc/letsencrypt/live/your-domain.com/privkey.pem ssl/
docker compose restart nginx

# 7. Done! Visit https://your-domain.com
```
