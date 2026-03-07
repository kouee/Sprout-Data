# Sprout Data Stack (Raspberry Pi Setup)

This project runs a full IoT data pipeline with Docker:

- MQTT broker (Mosquitto) for incoming device messages
- Python app that subscribes to MQTT and writes to InfluxDB
- InfluxDB 1.8 for time-series storage
- Grafana for dashboards

The guide below is focused on deploying to a fresh Raspberry Pi system, from cloning the repo until data appears in Grafana.

## Architecture and Ports

- MQTT: `1883` (TCP)
- MQTT over WebSocket: `9001` (TCP)
- InfluxDB: `8086` (HTTP API)
- Grafana: `3000` (Web UI)

## Important Data Model Note

The app subscribes to all MQTT topics (`#`), and writes each topic into its own InfluxDB database.

Example:

- Topic: `project1/data`
- InfluxDB database: `project1_data`
- Measurement name: `project1_data`

So in Grafana, your database depends on which MQTT topic you publish to.

## 1. Prepare Raspberry Pi

Recommended:

- Raspberry Pi OS 64-bit
- Network access
- User with `sudo`

Update system packages:

```bash
sudo apt update && sudo apt upgrade -y
```

Install Git:

```bash
sudo apt install -y git
```

## 2. Install Docker and Docker Compose

Install Docker engine:

```bash
sudo apt install -y docker.io
```

Enable/start Docker:

```bash
sudo systemctl enable docker
sudo systemctl start docker
```

Allow current user to run Docker without `sudo`:

```bash
sudo usermod -aG docker $USER
```

Log out and log back in (or reboot) so group changes apply.

Install Docker Compose plugin:

```bash
sudo apt install -y docker-compose-plugin
```

Verify:

```bash
docker --version
docker compose version
```

## 3. Clone the Repository

```bash
git clone <YOUR_REPO_URL>
cd sprout-data
```

If your folder name is different, `cd` into that folder instead.

## 4. Build and Start Containers

Build images:

```bash
docker compose build
```

Start all services:

```bash
docker compose up -d
```

Check status:

```bash
docker compose ps
```

You should see these services running:

- `mqtt-broker1`
- `influxdb`
- `grafana`
- `sprout-data-app-1` (or similar app container name)

## 5. Confirm Logs and Health

Check app logs:

```bash
docker compose logs -f app
```

You should see lines similar to:

- `InfluxDB is responding`
- `Connected to MQTT broker`
- `Subscribed to all topics (#)`

Press `Ctrl+C` to stop following logs.

## 6. Publish Test MQTT Data

### Option A: Publish from the broker container (quickest)

```bash
docker exec mqtt-broker1 mosquitto_pub -h localhost -t project1/data -m '{"temperature":25.5,"humidity":60,"timestamp":"2026-03-07 12:00:00"}'
```

### Option B: Publish from another device/microcontroller

Use Raspberry Pi IP as MQTT host:

- Host: `<RASPBERRY_PI_IP>`
- Port: `1883`
- Topic: `project1/data`
- Payload example:

```json
{"temperature":25.5,"humidity":60}
```

## 7. Verify Data Reached InfluxDB

List databases:

```bash
docker exec influxdb influx -execute "SHOW DATABASES"
```

You should see `project1_data` after publishing to `project1/data`.

Query latest points:

```bash
docker exec influxdb influx -database project1_data -execute "SELECT * FROM project1_data LIMIT 5"
```

## 8. Open Grafana and Add Data Source

Open in browser:

```text
http://<RASPBERRY_PI_IP>:3000
```

Default login:

- Username: `admin`
- Password: `pass`

Create InfluxDB data source:

1. Go to `Connections` -> `Data sources` -> `Add data source`.
2. Choose `InfluxDB`.
3. Configure with InfluxQL settings:
   - Query Language: `InfluxQL`
   - URL: `http://influxdb:8086`
   - Database: `project1_data`
   - User: `user`
   - Password: `pass`
4. Click `Save & test`.

Create a dashboard panel:

1. `Dashboards` -> `New` -> `New dashboard` -> `Add visualization`.
2. Select the InfluxDB data source.
3. Choose measurement `project1_data`.
4. Select fields like `temperature`, `humidity`.
5. Visualization: `Time series`.
6. Save dashboard.

## 9. Run at Startup

All services use `restart: unless-stopped`, so they auto-restart with Docker daemon.

After reboot, verify:

```bash
docker compose ps
```

## Useful Commands

Start stack:

```bash
docker compose up -d
```

Stop stack:

```bash
docker compose down
```

View all logs:

```bash
docker compose logs -f
```

Restart one service:

```bash
docker compose restart app
```

## Troubleshooting

`docker: permission denied`

- Re-login after `usermod -aG docker $USER`, or run with `sudo` temporarily.

`docker compose` command not found

- Install plugin: `sudo apt install -y docker-compose-plugin`
- Then use `docker compose ...` (with space), not `docker-compose`.

Containers start but no data in Grafana

- Confirm MQTT messages are being published to the topic you expect.
- Check app logs: `docker compose logs -f app`
- Confirm database was created: `SHOW DATABASES`
- In Grafana data source, ensure `Database` matches topic-derived DB (for `project1/data`, use `project1_data`).

Cannot access Grafana from another device

- Use Pi LAN IP (not `localhost`): `http://<RASPBERRY_PI_IP>:3000`
- Make sure port `3000` is not blocked by firewall/network policy.
