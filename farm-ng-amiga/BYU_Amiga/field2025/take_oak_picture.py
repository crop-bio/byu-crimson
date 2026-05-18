#!/usr/bin/env python3
import depthai as dai
import cv2
import numpy as np

CAMERA_IP = "10.95.76.20"
SAVE_FILE = "oak_12mp_still3.jpg"

pipeline = dai.Pipeline()

# Camera + MJPEG encoder
camera = pipeline.create(dai.node.ColorCamera)
mjpeg_encoder = pipeline.create(dai.node.VideoEncoder)
mjpeg_output = pipeline.create(dai.node.XLinkOut)
mjpeg_output.setStreamName("MJPEG Encoder Output")

# Set encoder to MJPEG
mjpeg_encoder.setDefaultProfilePreset(1, dai.VideoEncoderProperties.Profile.MJPEG)

# Camera settings
camera.setBoardSocket(dai.CameraBoardSocket.RGB)
camera.setResolution(dai.ColorCameraProperties.SensorResolution.THE_12_MP)
camera.setStillSize(4056, 3040)
camera.setInterleaved(False)

# Link camera still output to MJPEG encoder
camera.still.link(mjpeg_encoder.input)
mjpeg_encoder.bitstream.link(mjpeg_output.input)

# Add control input to trigger still
ctrl_in = pipeline.createXLinkIn()
ctrl_in.setStreamName("control")
ctrl_in.out.link(camera.inputControl)

# Connect and run
dev_info = dai.DeviceInfo(CAMERA_IP)
with dai.Device(pipeline, dev_info) as device:
    # Trigger still capture
    ctrl = dai.CameraControl()
    ctrl.setCaptureStill(True)
    device.getInputQueue("control").send(ctrl)

    # Wait for encoded MJPEG frame
    queue = device.getOutputQueue("MJPEG Encoder Output", maxSize=1, blocking=True)
    frame = queue.get()

    # Decode MJPEG to BGR
    img = cv2.imdecode(frame.getData(), cv2.IMREAD_UNCHANGED)
    cv2.imwrite(SAVE_FILE, img)
    print("Saved still image to:", SAVE_FILE)

            # cv2.imshow("Still", frame)
            # cv2.waitKey(0)
            # cv2.destroyAllWindows()

    # # Configure color camera for 12MP still capture
    # cam = pipeline.createColorCamera()
    # cam.setResolution(dai.ColorCameraProperties.SensorResolution.THE_12_MP)
    # cam.setStillSize(4056, 3040)
    # cam.setInterleaved(False)
    # cam.setColorOrder(dai.ColorCameraProperties.ColorOrder.BGR)

    # # Create still output
    # xout = pipeline.createXLinkOut()
    # xout.setStreamName("still")
    # cam.still.link(xout.input)

    # # Input queue for camera control
    # controlIn = pipeline.createXLinkIn()
    # controlIn.setStreamName("control")
    # controlIn.out.link(cam.inputControl)

    # print("Connecting to device...")
    # dev_info = dai.DeviceInfo(CAMERA_IP)
    # with dai.Device(pipeline, dev_info) as device:
    #     print(f"Connected to {device.getDeviceInfo().name}. Triggering still capture...")

    #     ctrl = dai.CameraControl()
    #     ctrl.setCaptureStill(True)
    #     device.getInputQueue("control").send(ctrl)

    #     q = device.getOutputQueue("still", maxSize=1, blocking=True)
    #     frame = q.get()
    #     frame_data = frame.getCvFrame()
    #     success, jpeg_data = cv2.imencode(".jpg", frame_data)

    #     if not success:
    #         raise RuntimeError("Failed to encode JPEG")
        
    #     with open(SAVE_FILE, "wb") as f: 
    #         f.write(jpeg_data.tobytes())


        # print("Saved still image to:", SAVE_FILE)


if __name__ == "__main__":
    main()
