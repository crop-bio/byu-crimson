print("Running imports")

import pyrealsense2 as rs
import numpy as np
import cv2
import time
import sys

print("imports successful")

# -----------------------------
# CONFIGURATION
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
zero_line = FRAME_HEIGHT-100



# -----------------------------
# SETUP REALSENSE
# -----------------------------
pipeline = rs.pipeline()
config = rs.config()

# config.enable_stream(
#     rs.stream.color,
#     FRAME_WIDTH,
#     FRAME_HEIGHT,
#     rs.format.bgr8,
#     FPS
# )

try:
    pipeline.start(config)
except RuntimeError as e:
    print("ERROR: Could not start RealSense pipeline")
    print(e)
    sys.exit(1)

print("RealSense started (non-blocking mode)")

# -----------------------------
# MAIN LOOP
# -----------------------------
try:
    while True:
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
            speed = 0

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
                            speed = -(cy-zero_line)/(zero_line)
                        else: speed = 0

                       










            # Display image
            # cv2.putText(
            #                 image,
            #                 f"Speed: {speed}",
            #                 (475, FRAME_HEIGHT-50),
            #                 cv2.FONT_HERSHEY_SIMPLEX,
            #                 .8,
            #                 (0,255,255),
            #                 2
            #             )

            # Use position to determine speed
            # cv2.line(image, (0, zero_line), (FRAME_WIDTH, zero_line), (0, 0, 255), 2)# inputs are (what to draw on, pt 1, pt2 , color(B,G,R), thickness (px))

            

            # cv2.imshow("RealSense Color (Non-Blocking)", image)
            # cv2.imshow("Mask", mask)

            print(f"Speed: {speed}, Centroid: {center}")
        

        # Exit on ESC
        # if cv2.waitKey(1) & 0xFF == 27:
        #     break

        # Prevent CPU spin
        time.sleep(0.001)

finally:
    print("\nStopping RealSense...")
    pipeline.stop()
    # cv2.destroyAllWindows()