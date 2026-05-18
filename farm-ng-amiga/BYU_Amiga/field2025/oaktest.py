import cv2
import numpy as np
import os
import time

from farm_ng.core.event_client import EventClient
from farm_ng.core.event_pb2 import Event

def save_depth_image(event: Event, save_dir: str):
    # The event payload is a serialized protobuf message of AmigaCameraImage
    # We need to import the AmigaCameraImage protobuf definition
    from farm_ng.amiga.proto import camera_pb2

    image_msg = camera_pb2.AmigaCameraImage()
    image_msg.ParseFromString(event.payload)

    # Check for depth data
    if image_msg.depth_image_data:
        # Decode depth image (assumed 16-bit PNG)
        depth_image = cv2.imdecode(
            np.frombuffer(image_msg.depth_image_data, dtype=np.uint8),
            cv2.IMREAD_UNCHANGED
        )

        if depth_image is None:
            print("Failed to decode depth image")
            return

        # Save depth image as PNG
        timestamp = int(time.time() * 1000)
        filename = os.path.join(save_dir, f"depth_{timestamp}.png")
        cv2.imwrite(filename, depth_image)
        print(f"Saved depth image: {filename}")
    else:
        print("No depth data found in message")

def main():
    # Create save directory for depth images
    save_dir = "depth_images"
    os.makedirs(save_dir, exist_ok=True)

    # Connect to EventClient (default localhost:50052)
    client = EventClient()

    # The Amiga camera topic — adjust this if needed
    topic = "amiga/camera/image"

    print(f"Subscribing to topic '{topic}' for depth images...")

    try:
        for event in client.subscribe(topic):
            save_depth_image(event, save_dir)

    except KeyboardInterrupt:
        print("\nExiting...")

if __name__ == "__main__":
    main()
