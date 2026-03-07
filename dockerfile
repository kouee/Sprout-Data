# Use the official Mosquitto base image
FROM eclipse-mosquitto:latest

# Copy custom configuration to the container
COPY mosquitto.conf /mosquitto/config/mosquitto.conf

# Expose ports (optional, for clarity)
EXPOSE 1883 9001