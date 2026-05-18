import asyncio
import logging
from farm_ng.core.event_client import EventClient
from farm_ng.core.event_service_pb2 import EventServiceConfig

CONFIG = EventServiceConfig(
    name="oak0",
    host="localhost",
    port=50010
)

async def list_uris():
    client = EventClient(CONFIG)
    uris = await client.list_uris()
    print("Available URIs on the server:")
    for uri in uris:
        print(uri.path)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(list_uris())
