from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import curses

from farm_ng.canbus.canbus_pb2 import Twist2d
from farm_ng.core.event_client import EventClient
from farm_ng.core.event_service_pb2 import EventServiceConfig
from farm_ng.core.events_file_reader import proto_from_json_file
from numpy import clip

# NOTE: be careful with these values, they are in m/s and rad/s
MAX_LINEAR_VELOCITY_MPS = 0.5
MAX_ANGULAR_VELOCITY_RPS = 0.5
VELOCITY_INCREMENT = 0.05


def update_twist_with_key_press(twist: Twist2d, key: int):
    """Function to update the twist command based on the key pressed."""
    # Stop
    if key == ord(" "):
        twist.linear_velocity_x = 0.0
        twist.linear_velocity_y = 0.0
        twist.angular_velocity = 0.0

    # Forward / reverse
    if key == ord("w"):
        twist.linear_velocity_x += VELOCITY_INCREMENT
    elif key == ord("s"):
        twist.linear_velocity_x -= VELOCITY_INCREMENT

    # Left / right
    if key == ord("a"):
        twist.angular_velocity += VELOCITY_INCREMENT
    elif key == ord("d"):
        twist.angular_velocity -= VELOCITY_INCREMENT

    # Clip the velocities
    twist.linear_velocity_x = clip(
        twist.linear_velocity_x,
        -MAX_LINEAR_VELOCITY_MPS,
        MAX_LINEAR_VELOCITY_MPS,
    )
    twist.angular_velocity = clip(
        twist.angular_velocity,
        -MAX_ANGULAR_VELOCITY_RPS,
        MAX_ANGULAR_VELOCITY_RPS,
    )
    return twist


async def run(stdscr, service_config_path: Path):
    """Run the canbus service client with curses-based keyboard input."""
    stdscr.nodelay(True)  # non-blocking input
    stdscr.addstr(0, 0, "Vehicle Twist Control (w/s/a/d to move, space to stop, q to quit)")

    twist = Twist2d()
    config: EventServiceConfig = proto_from_json_file(service_config_path, EventServiceConfig())
    client: EventClient = EventClient(config)

    print(client.config)

    running = True
    while running:
        key = stdscr.getch()
        if key == ord("q"):
            running = False
        elif key != -1:  # valid key pressed
            twist = update_twist_with_key_press(twist, key)

        # Always send the current twist, even if no new key pressed
        stdscr.addstr(2, 0, f"lin: {twist.linear_velocity_x:.2f}, ang: {twist.angular_velocity:.2f}   ")
        await client.request_reply("/twist", twist)

        await asyncio.sleep(0.05)  # ~20 Hz command rate

    # stop vehicle on exit
    twist.linear_velocity_x = 0.0
    twist.angular_velocity = 0.0
    await client.request_reply("/twist", twist)


def main():
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="Send twist commands to control Amiga through the canbus service.",
    )
    parser.add_argument("--service-config", type=Path, required=True, help="The canbus service config.")
    args = parser.parse_args()

    curses.wrapper(lambda stdscr: asyncio.run(run(stdscr, args.service_config)))


if __name__ == "__main__":
    main()
