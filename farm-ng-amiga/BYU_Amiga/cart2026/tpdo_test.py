import argparse
import asyncio
from pathlib import Path

from farm_ng.canbus.packet import AmigaTpdo1
from farm_ng.core.event_client import EventClient
from farm_ng.core.event_service_pb2 import EventServiceConfig
from farm_ng.core.events_file_reader import proto_from_json_file


async def main(service_config_path: Path) -> None:
    """Stream Amiga TPDO1 vehicle state messages."""

    # Load the service config
    config: EventServiceConfig = proto_from_json_file(service_config_path, EventServiceConfig())

    # Subscribe to the CAN bus stream
    async for event, message in EventClient(config).subscribe(config.subscriptions[0], decode=True):

        try:
            # Convert the raw CAN message to an AmigaTpdo1 object
            amiga_state = AmigaTpdo1.from_raw_canbus_message(message)

            print("\n###################\n")
            print(amiga_state)

        except Exception:
            # Ignore messages that are not AmigaTpdo1
            continue


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="Stream Amiga TPDO1 vehicle state from the CAN bus service."
    )

    parser.add_argument(
        "--service-config",
        type=Path,
        required=True,
        help="The CAN bus service config."
    )

    args = parser.parse_args()

    asyncio.run(main(args.service_config))