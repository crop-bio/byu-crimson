# # import pyrealsense2 as rs

# # ctx = rs.context()

# # dev = ctx.devices[0]
# # for s in dev.sensors[0].get_stream_profiles():
# #     print(s)

# # for dev in ctx.query_devices():
# #     print(dev.get_info(rs.camera_info.serial_number))
# #     # print(dev.get_info(rs.camera_info.firmware_version))

# import pyrealsense2 as rs
# import numpy as np
# import cv2

# pipeline = rs.pipeline()
# config = rs.config()
# try:
#     config.enable_stream(rs.stream.color, 1920, 1080, rs.format.bgr8, 30)
#     pipeline.start(config)

# except Exception as e:
#     print(f"Realsense failed, {e}")

# # Wait for auto-exposure and stream warm-up
# for _ in range(5):
#     pipeline.wait_for_frames()

# frames = pipeline.wait_for_frames()
# color_frame = frames.get_color_frame()

# # Convert frame to numpy array
# color_image = np.asanyarray(color_frame.get_data())

# # Save image
# cv2.imwrite("photo.png", color_image)

# pipeline.stop()


import pyrealsense2 as rs

# import playsound

# playsound.playsound('machine-error.mp3')

ctx = rs.context()
devices = ctx.query_devices()

## Uncomment to get all the possible streaming configurations

# for device in ctx.query_devices():
#     print(device)
#     for sensor in device.query_sensors():
#         print(sensor.get_info(rs.camera_info.name))

#         for profile in sensor.get_stream_profiles():
#             vprofile = profile.as_video_stream_profile()

#             print(f"{vprofile.stream_name()} {vprofile.format()} "
#                 f"{vprofile.width()}x{vprofile.height()} @ {vprofile.fps()}fps")
    
for dev in ctx.query_devices():
    print(dev.get_info(rs.camera_info.name),
          dev.get_info(rs.camera_info.serial_number),
          "->", dev.get_info(rs.camera_info.usb_type_descriptor))

