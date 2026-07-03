# Deploying TerraLens on Proxmox (LXC)

This guide turns the repository into an always-on, LAN-hosted monitoring
appliance running in a Proxmox **LXC container**. The whole stack is Docker
Compose, so the container just needs Docker with nesting enabled.

## 1. Create the LXC container

Recommended sizing for the full stack (API + PostGIS + web + schedulers):

| Resource | Minimum | Comfortable |
| --- | --- | --- |
| Cores | 2 | 4 |
| RAM | 4 GB | 8 GB |
| Disk | 32 GB | 64+ GB (metric archive + imagery grow over time) |

In the Proxmox UI (or `pct create`):

- Template: **Debian 12** or **Ubuntu 24.04** standard template.
- **Unprivileged container: yes** (keep the default).
- Under **Options → Features**, enable **nesting** and **keyctl** — Docker
  needs both inside an unprivileged LXC:

```bash
pct set <ctid> --features nesting=1,keyctl=1
```

- Give the container a static IP or a DHCP reservation — the web console
  and API are addressed by this IP on your LAN.

Storage note: prefer a rootfs on local-lvm/ZFS with room to grow; the
Postgres and imagery volumes live inside the container's Docker storage.

## 2. Install Docker inside the container

```bash
apt update && apt install -y curl git
curl -fsSL https://get.docker.com | sh
```

If `docker run hello-world` fails on an unprivileged container, re-check
that nesting and keyctl are enabled and restart the container.

## 3. Configure and start the stack

```bash
git clone https://github.com/p3nicillin/Terralens.git
cd Terralens
cp .env.example .env
```

Edit `.env` for LAN hosting (replace `192.168.1.50` with the container IP):

```bash
# Publish on all interfaces so other LAN devices can reach the appliance
BIND_HOST=0.0.0.0
# The browser needs the API by the container's address
VITE_API_URL=http://192.168.1.50:8000/api/v1
CORS_ORIGINS=["http://192.168.1.50:8080"]
ALLOWED_HOSTS=["192.168.1.50","localhost","127.0.0.1"]
# Generate real secrets even on a LAN
SECRET_KEY=<paste output of: openssl rand -hex 32>
POSTGRES_PASSWORD=<paste output of: openssl rand -hex 16>
# No-login appliance mode (trusted network only)
LOCAL_MODE=true
```

Then:

```bash
docker compose up --build -d
```

Open `http://<container-ip>:8080`. With `LOCAL_MODE=true` the console signs
itself in as the auto-provisioned local operator — no credentials needed.
Set `LOCAL_MODE=false` if the appliance is ever exposed beyond your trusted
network, and front it with TLS (Caddy/Traefik/nginx) at that point.

## 4. What runs autonomously

Once the containers are healthy the platform operates hands-off:

- **Watch-area ingestion** — the scheduler searches new Sentinel-2 imagery
  for every active watch area (including the built-in whole-planet Global
  set) and runs the vegetation/burn-change detector on qualifying pairs.
- **Learning tick (every 5 min)** — live NOAA SWPC space-weather readings
  are archived locally; adaptive per-metric baselines are learned from that
  archive; hourly statistical forecasts are issued and later scored against
  what actually happened (see the **Insights** page).
- **Imagery harvest (every 15 min)** — the latest SDO, SOHO/LASCO, GOES
  SUVI, and DSCOVR EPIC frames are archived to the `imagery_data` volume,
  deduplicated by content hash (see the **Space Gallery** page).

## 5. Operations

Health and metrics:

- `http://<container-ip>:8000/health/ready` — API + database readiness
- `http://<container-ip>:8000/metrics` — Prometheus metrics

Start on boot: set the LXC to start at boot (`pct set <ctid> --onboot 1`);
Compose services use `restart: unless-stopped`, so Docker brings the stack
back automatically — no extra systemd unit is required.

Updating:

```bash
git pull && docker compose up --build -d
```

Backups — two Docker volumes hold all durable state:

```bash
docker compose exec postgres pg_dump -U earth earth_monitor | gzip > terralens-$(date +%F).sql.gz
docker run --rm -v earth-monitor_imagery_data:/data -v "$PWD:/backup" alpine tar czf /backup/imagery-$(date +%F).tar.gz /data
```

Proxmox-level `vzdump` backups/snapshots of the container also capture
everything if you prefer whole-appliance backups.

## 6. Storage growth expectations

- Metric archive: ~5 metrics at 1–5 min cadence ≈ a few MB per month;
  pruned automatically after `LEARNING_RETENTION_DAYS` (default 365).
- Imagery: bounded at `IMAGERY_MAX_CAPTURES_PER_SOURCE` (default 400)
  frames per source; with nine sources this stays in the low GB range.
- Sentinel-2 observations are metadata rows only (no rasters stored).
