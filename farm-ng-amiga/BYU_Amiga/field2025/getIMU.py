#!/usr/bin/env python3
import asyncio
import logging
import sys

from farm_ng.core.event_client import EventClient
from farm_ng.core.event_service_pb2 import EventServiceConfig, SubscribeRequest
from farm_ng.core.event_pb2 import Event

# -----------------------------
# CONFIGURATION
# -----------------------------
CONFIG = EventServiceConfig(
    name="oak0",
    host="localhost",
    port=50010
)

# Path for IMU data (adjust if your service uses a different path)
IMU_PATH = "/imu"
FILTER_PATH = "/filter"

# -----------------------------
# MAIN ASYNC FUNCTION
# -----------------------------
async def main():
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout
    )
    logger = logging.getLogger("imu_client")
    logger.info("Starting IMU client...")

    # Create client
    client = EventClient(CONFIG)

    # Create subscription request
    request = SubscribeRequest(
        uri=Event().uri.__class__(path=IMU_PATH, query=f"service_name={CONFIG.name}"),
        every_n=1  # get every IMU message
    )

    logger.info(f"Subscribing to IMU data on {IMU_PATH}...")

    # Subscribe and process incoming events
    async for event, payload in client.subscribe(request):
        # payload may be raw bytes or a protobuf message
        logger.info(f"Received event {event.uri.path}, sequence {event.sequence}, payload: {payload}")


# -----------------------------
# RUN
# -----------------------------
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("IMU client stopped by user.")
