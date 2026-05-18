import depthai as dai
import cv2
import time

pipeline = dai.Pipeline()

# RGB camera using preview (8-bit debayered)
cam_rgb = pipeline.createColorCamera()
cam_rgb.setBoardSocket(dai.CameraBoardSocket.CAM_A)
cam_rgb.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)
cam_rgb.setColorOrder(dai.ColorCameraProperties.ColorOrder.BGR)

xout_rgb = pipeline.createXLinkOut()
xout_rgb.setStreamName("rgb")
cam_rgb.preview.link(xout_rgb.input)  # use preview, more reliable headless

with dai.Device(pipeline) as device:
    q_rgb = device.getOutputQueue("rgb", maxSize=4, blocking=True)

    frame_rgb = None
    print("Waiting for valid frame...")
    # Poll until a frame with variation appears
    while True:
        in_rgb = q_rgb.get()
        frame_rgb = in_rgb.getCvFrame()
        if frame_rgb.min() != frame_rgb.max():
            break
        time.sleep(0.05)  # wait a bit before next grab

    # Optional: convert RGB→BGR
    frame_rgb = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

    cv2.imwrite("rgb_headless_preview.jpg", frame_rgb)
    print("Saved RGB frame to rgb_headless_preview.jpg")

# pipeline = dai.Pipeline()

# mono = pipeline.createMonoCamera()
# mono.setBoardSocket(dai.CameraBoardSocket.CAM_B)
# mono.setResolution(dai.MonoCameraProperties.SensorResolution.THE_720_P)

# xout = pipeline.createXLinkOut()
# xout.setStreamName("mono")
# mono.out.link(xout.input)

# with dai.Device(pipeline) as device:
#     queue = device.getOutputQueue(name="mono", maxSize=1, blocking=True)
#     frame = None
#     while frame is None or frame.min() > 100:
#         frame = queue.get().getCvFrame()
#         print("Frame shape:", frame.shape)
#         print("Min/Max pixel values:", frame.min(), frame.max())
#     cv2.imwrite("my_frame.jpg", frame) # This delivers a frame in uniform grayscale... meaningless

