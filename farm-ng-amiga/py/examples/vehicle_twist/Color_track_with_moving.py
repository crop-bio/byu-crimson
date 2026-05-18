from __future__ import annotations

import pyrealsense2 as rs
import argparse
import asyncio
from http import client
from pathlib import Path
from tracemalloc import start
import threading
import numpy as np
import cv2
import time
import sys

from farm_ng.canbus.canbus_pb2 import Twist2d
from farm_ng.core.event_client import EventClient
from farm_ng.core.event_service_pb2 import EventServiceConfig
from farm_ng.core.events_file_reader import proto_from_json_file
from numpy import clip


# NOTE: be careful with these values, they are in m/s and rad/s (For the Amiga movement)
MAX_LINEAR_VELOCITY_MPS = 0.25
MAX_ANGULAR_VELOCITY_RPS = 0.5
VELOCITY_INCREMENT = 0.05

# -----------------------------
# CONFIGURATION for the Camera 
# -----------------------------
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
FPS = 30

# -----------------------------
# Set limits/values
# -----------------------------

# Color tracking 
lower_yellow = np.array([20, 100, 100])
upper_yellow = np.array([35, 255, 255])
lower_purple = np.array([110, 75, 75])
upper_purple = np.array([130, 255, 255])
hs_low = lower_purple
hs_high = upper_purple
color_limits = (hs_low,hs_high)
Min_Area = 150

# Speed control
max_speed = 1
zero_line = 100

#Shared state between thread loop and asyncio loop 
speed = 0.0
speed_lock = threading.Lock()
camera_running = True


# SETUP REALSENSE
pipeline = rs.pipeline()
config = rs.config()


try:
    pipeline.start(config)
except RuntimeError as e:
    print("ERROR: Could not start RealSense pipeline")
    print(e)
    sys.exit(1)

print("RealSense started (non-blocking mode)")


#CAMERA THREAD
def camera_thread():
    global speed, camera_running

    try:
        while camera_running: 
            # Non-blocking frame grab
            frames = pipeline.poll_for_frames()

            if frames:
                color_frame = frames.get_color_frame()
                if not color_frame:
                    continue

                # Convert to NumPy array (zero-copy)
                image = np.asanyarray(color_frame.get_data())

                # Convert to HSV (Easier to track hue and works better in different lighting)

                im_hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

                # Create a mask of the correct color
                lower, upper = color_limits
                mask = cv2.inRange(im_hsv, lower, upper)

                # Filter our noise and remove small specks. (erase 2 times, then dilate 2 times)

                mask = cv2.erode(mask,None, iterations = 2)
                mask = cv2.dilate(mask, None, iterations = 2)

                # Find contours and only deal with the biggest one, then find the center

                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE) 
                
                '''
                RETR_EXTERNAL means that open cv will only return the outside of any blobs. Chain approx simple cleans up straight lines and stores more efficiently
                '''
                center = None
                local_speed= 0

                if contours:
                    # Get largest contour
                    largest = max(contours, key = cv2.contourArea)

                    # Ignore if the blob is small
                    if cv2.contourArea(largest) > Min_Area:  # change this value to detect bigger or smaller blobs
                        M = cv2.moments(largest)
                        '''
                        What this essentially does is says, Only make a list of moments and carry on processing if 
                        the detected largest blob is sufficiently large
                        '''


                        if M["m00"] != 0:
                            cx = M["m10"]/M["m00"]
                            cy = M["m01"]/M["m00"]
                            center = (int(cx), int(cy))
                            '''
                            Notes on using the output of cv2.moments:
                            - the output of moments is a dictionary. It contains the following values (plus more) with these keys:
                            m00 = area
                            m10 = sum of all x coordinates
                            m01 = sum of all y coordinates
                            - Since we are using a black and white pixel mask, each pixel contributes the same amount of area
                            (hence why we divide by the total number of pixels, and we don't have to multiply each pixel by its area)

                            '''

                            # Draw a circle over the centroid
                            # cv2.circle(image, center, 5, (0,0,255), -1)
                            # cv2.drawContours(image, [largest], -1, (0,255,0), 2)

                            # Use position to determine speed
                            # cv2.line(image, (0, zero_line), (FRAME_WIDTH, zero_line), (0, 0, 255), 2)# inputs are (what to draw on, pt 1, pt2 , color(B,G,R), thickness (px))
                            if center is not None:
                                local_speed = (cy-zero_line)/(FRAME_HEIGHT-zero_line)
                            else: local_speed = 0
                
                with speed_lock: 
                    speed = -1*local_speed

                print(f"Speed: {local_speed}, Centroid: {center}, Area: {cv2.contourArea(largest)}")
            
            #prevent cpu spinning
            time.sleep(0.001)
    
    finally:
        print("\nStopping realsense")
        pipeline.stop()



async def move(service_config_path: Path) -> None:
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

    print(f"Sending linear velocity: {twist.linear_velocity_x:.3f}, angular velocity: {twist.angular_velocity:.3f}")
    start = time.time()

    try:
        while True:
            with speed_lock:
                current_speed = speed
            twist.linear_velocity_x = clip(
                current_speed * MAX_LINEAR_VELOCITY_MPS,
                -MAX_LINEAR_VELOCITY_MPS,
               0
            )
            twist.angular_velocity = 0.0

            print(f"Sending linear velocity: {twist.linear_velocity_x:.3f}")
            await client.request_reply("/twist", twist)

            if time.time() - start > 300.0:
                break

            await asyncio.sleep(0.03)  # ~30 Hz control loop
    
    finally:
        camera_running = False
        twist.linear_velocity_x = 0.0
        print(f"Sending linear velocity: {twist.linear_velocity_x:.3f}")
        await client.request_reply("/twist", twist)


if __name__ == "__main__":

    cam_thread = threading.Thread(target=camera_thread, daemon=True)
    cam_thread.start()

    asyncio.run(move(service_config_path=Path("/mnt/managed_home/farm-ng-user-byu-crimson/farm-ng-amiga/py/examples/vehicle_twist/service_config.json")))

