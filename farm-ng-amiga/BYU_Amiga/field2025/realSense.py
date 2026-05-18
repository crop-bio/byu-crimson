import pyrealsense2 as rs
import numpy as np
import cv2

def capture_realsense_image(output_filename="realsense_image.png"):
    # Configure the pipeline
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)

    # Start streaming
    pipeline.start(config)

    try:
        for count in range(5):
            # Wait for a coherent frame: sometimes the first frames are not good
            for _ in range(5):
                frames = pipeline.wait_for_frames()
                color_frame = frames.get_color_frame()

            if not color_frame:
                raise RuntimeError("Could not capture color frame from RealSense camera.")

            # Convert image to numpy array
            color_image = np.asanyarray(color_frame.get_data())

            # Save image to file
            cv2.imwrite(output_filename, color_image)
            print(f"Image saved to {output_filename}")

    finally:
        # Stop streaming
        pipeline.stop()


if __name__ == "__main__":
    capture_realsense_image("test_capture.png")


'''
import pyrealsense2 as rs
import numpy as np
import cv2
import os
import time
from datetime import datetime

class RealSenseCamera():
    """A class defining a real sense camera"""
    def __init__(self, res = [1280, 720], serial=None):
        # Configure color stream
        self.pipeline = rs.pipeline()
        config = rs.config()
        if serial: 
            config.enable_device(serial)

        config.enable_stream(rs.stream.color, res[0], res[1], rs.format.bgr8, 30)
        config.enable_stream(rs.stream.depth, res[0], res[1], rs.format.z16, 30)

        # Start streaming
        self.pipeline.start(config)
        self.take_picture(save_path="captures/firstpic.png",picType="color")
        time.sleep(0.5)


    def take_picture(self, save_path="captures/image5.png", picType="color"):
        
        try:
        # Wait a few frames so auto-exposure can settle
            while True:
                frames = self.pipeline.wait_for_frames()
                dict = {"color":frames.get_color_frame(), "depth":frames.get_depth_frame()}
                pict_frame = dict.get(picType)
                if pict_frame:
                    break
            # Convert to numpy (16-bit depth)
            color_image = np.asanyarray(pict_frame.get_data())
            # Save raw depth as 16-bit PNG
            cv2.imwrite(save_path, color_image)
            print(f"Color image saved to {save_path}")

        except:
            print("Something went wrong. But there is no built-in error detection. Good luck!")

    def capture_realsense_images(self,save_dir="captures", pict_type="color"):
        self.type = pict_type
        # Ensure the directory exists
        os.makedirs(save_dir, exist_ok=True)
        if "color" in self.type:
            try:
                print("Capturing images every 1 second. Press 'q' in the window to quit.")

                counter = 0
                while True:
                    frames = self.pipeline.wait_for_frames()
                    color_frame = frames.get_color_frame()
                    if not color_frame:
                        continue

                    # Convert to numpy
                    color_image = np.asanyarray(color_frame.get_data())

                    # Show image in window
                    cv2.imshow("RealSense Capture (press 'q' to quit)", color_image)

                    # Save image with incrementing file name
                    filename = os.path.join(save_dir, f"image_{counter:04d}.png")
                    cv2.imwrite(filename, color_image)
                    print(f"Saved {filename}")
                    counter += 1

                    # Wait 1 second or until key press
                    key = cv2.waitKey(1000) & 0xFF
                    if key == ord('q'):
                        print("Exiting capture loop.")
                        break

            finally:
                self.pipeline.stop()
                cv2.destroyAllWindows()

        elif "depth" in self.type:
            
            try:
                print("Capturing depth images every 1 second. Press 'q' in the window to quit.")

                counter = 0
                while True:
                    frames = self.pipeline.wait_for_frames()
                    depth_frame = frames.get_depth_frame()
                    if not depth_frame:
                        continue

                    # Convert to numpy (16-bit depth)
                    depth_image = np.asanyarray(depth_frame.get_data())

                    # Save depth image as 16-bit PNG
                    filename = os.path.join(save_dir, f"depth_{counter:04d}.png")
                    cv2.imwrite(filename, depth_image)
                    print(f"Saved raw depth {filename}")

                    # Also create a color-mapped preview for display
                    depth_colormap = cv2.applyColorMap(
                        cv2.convertScaleAbs(depth_image, alpha=0.03),
                        cv2.COLORMAP_JET
                    )

                    cv2.imshow("RealSense Depth Capture (press 'q' to quit)", depth_colormap)

                    counter += 1

                    # Wait 1 second or until key press
                    key = cv2.waitKey(1000) & 0xFF
                    if key == ord('q'):
                        print("Exiting capture loop.")
                        break

            finally:
                cv2.destroyAllWindows()


def main():
    cam1 = RealSenseCamera(serial="211622067750")
    cam2 = RealSenseCamera(serial="217222062474")

    # cam.capture_realsense_images()
    # try:
    for i in range(5):
        # timestamp = datetime.now().strftime("%Y.%m.%d_%H:%M_%S.%f")
        timestamp = datetime.now().strftime("%Y.%m.%d_%H%M_%S.%f")
        filename1 = os.path.join("captures", f"cam1_{timestamp}.png")
        filename2 = os.path.join("captures", f"cam2_{timestamp}.png")
        cam1.take_picture(save_path=filename1,picType="color")
        cam2.take_picture(save_path=filename2,picType="color")
        time.sleep(0.5)

    # except KeyboardInterrupt:
    #     print("Exiting capture loop")

if __name__ == "__main__":
    main()


# Serial Numbers:
# 211622067750
# 217222062474
'''