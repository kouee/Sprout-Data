import paho.mqtt.client as mqtt
import time

# MQTT configuration
MQTT_HOST = "mqtt-broker1"
MQTT_PORT = 1883

# Connect to MQTT
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect(MQTT_HOST, MQTT_PORT, 60)

# Read the data file and send each line as MQTT message
with open('agrihub data.json', 'r') as f:
    for line in f:
        line = line.strip()
        if line:
            client.publish("project1/data", line)
            print(f"Sent: {line}")
            time.sleep(0.1)  # Small delay between messages

print("All data sent.")