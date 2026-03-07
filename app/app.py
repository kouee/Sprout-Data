import paho.mqtt.client as mqtt
import requests
import json
import re
import time
import math
from datetime import datetime, timedelta, timezone

# InfluxDB configuration
INFLUXDB_URL = "http://influxdb:8086"
PAYLOAD_TIMEZONE = timezone(timedelta(hours=8))
STRING_FIELDS = {"timestamp", "water_level", "dosing_pump"}
KNOWN_DATABASES = set()


def escape_tag_component(value):
    return str(value).replace("\\", "\\\\").replace(",", "\\,").replace(" ", "\\ ").replace("=", "\\=")


def escape_field_string(value):
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def parse_payload_timestamp(timestamp_value):
    if not isinstance(timestamp_value, str):
        return None

    value = timestamp_value.strip()
    if not value:
        return None

    try:
        iso_value = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(iso_value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=PAYLOAD_TIMEZONE)
        return int(parsed.timestamp() * 1_000_000_000)
    except ValueError:
        pass

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S.%f",
    ]
    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt).replace(tzinfo=PAYLOAD_TIMEZONE)
            return int(parsed.timestamp() * 1_000_000_000)
        except ValueError:
            continue

    return None

def sanitize_topic_identifier(topic, lower=False):
    value = re.sub(r"[^a-zA-Z0-9_]", "_", str(topic).strip())
    value = re.sub(r"_+", "_", value).strip("_")
    if not value:
        value = "default_topic"
    return value.lower() if lower else value


def ensure_database(db_name):
    if db_name in KNOWN_DATABASES:
        return True

    try:
        response = requests.post(
            f"{INFLUXDB_URL}/query",
            params={"q": f'CREATE DATABASE "{db_name}"'},
            timeout=5
        )
        if response.status_code in [200, 201, 204]:
            KNOWN_DATABASES.add(db_name)
            print(f'InfluxDB database ready: "{db_name}"')
            return True

        print(f'InfluxDB DB creation failed for "{db_name}": {response.status_code} {response.text[:200]}')
        return False
    except Exception as e:
        print(f'InfluxDB DB creation failed for "{db_name}": {e}')
        return False


# Try to initialize InfluxDB connectivity on first connection
def initialize_influxdb():
    try:
        # Check query API readiness without writing points.
        response = requests.post(
            f"{INFLUXDB_URL}/query",
            params={"q": "SHOW DATABASES"},
            timeout=5
        )
        if response.status_code in [200, 201, 204]:
            print("InfluxDB query API initialized and ready")
            return True
        else:
            print(f"InfluxDB initialization query failed: {response.status_code} {response.text[:200]}")
            return False
    except Exception as e:
        print(f"InfluxDB initialization failed: {e}")
        return False

# Wait for InfluxDB to be ready
print("Waiting for InfluxDB...")
while True:
    try:
        response = requests.get(f"{INFLUXDB_URL}/ping", timeout=2)
        if response.status_code == 204:
            print("InfluxDB is responding")
            # Try to initialize
            if initialize_influxdb():
                break
    except Exception as e:
        print(f"Waiting for InfluxDB: {e}")
    time.sleep(3)

print("Connected to InfluxDB")

def on_message(client, userdata, message):
    topic = message.topic
    try:
        payload_str = message.payload.decode()
        print(f"[{topic}] Received: {repr(payload_str)}")
        data = json.loads(payload_str)
    except json.JSONDecodeError as e:
        print(f"[{topic}] Invalid JSON: {e}")
        return

    # Derive topic-specific measurement and database names.
    measurement = sanitize_topic_identifier(topic, lower=False)
    db_name = sanitize_topic_identifier(topic, lower=True)

    if not ensure_database(db_name):
        print(f'[{topic}] Skipping write because DB "{db_name}" is not ready')
        return

    # Extract fields and optional payload timestamp
    field_parts = []
    point_timestamp_ns = parse_payload_timestamp(data.get("timestamp"))

    for key, value in data.items():
        safe_key = re.sub(r'[^a-zA-Z0-9_]', '_', key)
        if not safe_key:
            continue

        if key == "timestamp":
            field_parts.append(f'{safe_key}="{escape_field_string(value)}"')
            continue

        if isinstance(value, (int, float)):
            numeric_value = float(value)
            if math.isfinite(numeric_value):
                field_parts.append(f"{safe_key}={numeric_value}")
        elif isinstance(value, str):
            try:
                numeric_value = float(value)
                if math.isfinite(numeric_value):
                    field_parts.append(f"{safe_key}={numeric_value}")
            except ValueError:
                if safe_key in STRING_FIELDS:
                    field_parts.append(f'{safe_key}="{escape_field_string(value)}"')
                else:
                    # Preserve non-numeric values without causing field-type conflicts.
                    raw_key = f"{safe_key}_raw"
                    field_parts.append(f'{raw_key}="{escape_field_string(value)}"')
        elif isinstance(value, bool):
            field_parts.append(f"{safe_key}={'true' if value else 'false'}")
    
    if not field_parts:
        print(f"[{topic}] No storable fields found; skipping write")
        return

    print(f"[{topic}] Prepared {len(field_parts)} field(s)")

    # Build line protocol
    # Format: measurement,tag=value field=value [timestamp]
    tags_part = f",topic={escape_tag_component(topic)}"
    fields_part = ",".join(field_parts)
    point = f"{measurement}{tags_part} {fields_part}"
    if point_timestamp_ns is not None:
        point = f"{point} {point_timestamp_ns}"

    # Write to InfluxDB
    try:
        headers = {"Content-Type": "text/plain"}
        response = requests.post(
            f"{INFLUXDB_URL}/write?db={db_name}",
            data=point,
            headers=headers,
            timeout=5
        )
        if response.status_code in [200, 201, 204]:
            ts_info = "payload timestamp" if point_timestamp_ns is not None else "server timestamp"
            print(f'[{topic}] Stored in db="{db_name}" measurement="{measurement}" using {ts_info}')
        else:
            print(f"[{topic}] Write failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[{topic}] Error: {e}")

# Setup MQTT client
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_message = on_message

# Connect to MQTT
print("Connecting to MQTT...")
while True:
    try:
        client.connect("mqtt-broker1", 1883, 60)
        print("Connected to MQTT broker")
        break
    except Exception as e:
        print(f"MQTT connection failed: {e}")
        time.sleep(5)

# Subscribe to all topics
client.subscribe("#", qos=1)
print("Subscribed to all topics (#)")

# Start MQTT loop
client.loop_forever()
