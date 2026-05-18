import pyrealsense2 as rs

# List all connected devices
ctx = rs.context()
devices = ctx.query_devices()
print(f"Found {len(devices)} connected RealSense device(s)\n")

for dev in devices:
    serial = dev.get_info(rs.camera_info.serial_number)
    name = dev.get_info(rs.camera_info.name)
    print(f"=== Device: {name} (S/N: {serial}) ===")

    # Configure a temporary pipeline for this specific device
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_device(serial)
    width, height = 1920, 1080
    config.enable_stream(rs.stream.color, width, height, rs.format.bgr8, 15)
    config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    profile = pipeline.start(config)

    # --- Color Intrinsics ---
    try:
        color_stream = profile.get_stream(rs.stream.color)
        color_intr = color_stream.as_video_stream_profile().get_intrinsics()
        print("\n[Color Intrinsics]")
        print(f"  Resolution: {color_intr.width} x {color_intr.height}")
        print(f"  Focal Length (fx, fy): ({color_intr.fx:.2f}, {color_intr.fy:.2f})")
        print(f"  Principal Point (cx, cy): ({color_intr.ppx:.2f}, {color_intr.ppy:.2f})")
        print(f"  Distortion Model: {color_intr.model}")
        print(f"  Distortion Coeffs: {color_intr.coeffs}")
    except Exception as e:
        print("  ⚠️ Could not access color stream:", e)

    # --- Depth Intrinsics ---
    try:
        depth_stream = profile.get_stream(rs.stream.depth)
        depth_intr = depth_stream.as_video_stream_profile().get_intrinsics()
        print("\n[Depth Intrinsics]")
        print(f"  Resolution: {depth_intr.width} x {depth_intr.height}")
        print(f"  Focal Length (fx, fy): ({depth_intr.fx:.2f}, {depth_intr.fy:.2f})")
        print(f"  Principal Point (cx, cy): ({depth_intr.ppx:.2f}, {depth_intr.ppy:.2f})")
        print(f"  Distortion Model: {depth_intr.model}")
        print(f"  Distortion Coeffs: {depth_intr.coeffs}")
    except Exception as e:
        print("  ⚠️ Could not access depth stream:", e)

    # --- Extrinsics: Depth → Color ---
    try:
        extr = depth_stream.as_video_stream_profile().get_extrinsics_to(color_stream)
        print("\n[Depth → Color Extrinsics]")
        print(f"  Rotation:\n    {extr.rotation[0:3]}\n    {extr.rotation[3:6]}\n    {extr.rotation[6:9]}")
        print(f"  Translation (m): {extr.translation}")
    except Exception as e:
        print("  ⚠️ Could not access extrinsics:", e)

    # Stop the pipeline for this camera
    pipeline.stop()
    print("\n" + "-"*60 + "\n")
