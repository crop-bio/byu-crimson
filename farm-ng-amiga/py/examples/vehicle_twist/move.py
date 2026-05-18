from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import cv2
from farm_ng.canbus.canbus_pb2 import Twist2d
from farm_ng.core.event_client import EventClient
from farm_ng.core.event_service_pb2 import EventServiceConfig
from farm_ng.core.events_file_reader import proto_from_json_file
from numpy import clip
import time

# NOTE: be careful with these values, they are in m/s and rad/s
MAX_LINEAR_VELOCITY_MPS = 0.5
MAX_ANGULAR_VELOCITY_RPS = 0.5
VELOCITY_INCREMENT = 0.05

async def main(service_config_path: Path) -> None:
    """Run the canbus service client.

    Args:
        service_config_path (Path): The path to the canbus service config.
    """
    # Initialize the command to send
    twist = Twist2d() 
    config: EventServiceConfig = proto_from_json_file(service_config_path, EventServiceConfig())
    client: EventClient = EventClient(config)

    twist.linear_velocity_x = 0.0
    twist.linear_velocity_y = 0.0
    twist.angular_velocity = 0.0

    twist.linear_velocity_x = 0.25
    twist.angular_velocity = 0.0
    print(f"Sending linear velocity: {twist.linear_velocity_x:.3f}, angular velocity: {twist.angular_velocity:.3f}")
    start = time.time()
    while True:
        await client.request_reply("/twist", twist)   
        if time.time() - start > 2.0:
            break 
    twist.linear_velocity_x = 0.0
    print(f"Sending linear velocity: {twist.linear_velocity_x:.3f}, angular velocity: {twist.angular_velocity:.3f}")
    await client.request_reply("/twist", twist)  

if __name__ == "__main__":

    asyncio.run(main(service_config_path=Path("/mnt/managed_home/farm-ng-user-byu-crimson/farm-ng-amiga/py/examples/vehicle_twist/service_config.json")))
