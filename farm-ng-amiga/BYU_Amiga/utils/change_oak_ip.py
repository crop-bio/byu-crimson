import depthai as dai

# def change_ip(old_ip: str, new_ip: str):
#     """
#     Change the IP address of the DepthAI device.

#     Args:
#         new_ip (str): The new IP address to set for the device.
#     """
#     # Create a pipeline
#     pipeline = dai.Pipeline()

#     # Create a device object
#     with dai.Device(dai.DeviceInfo(old_ip)) as device:
#         print(f"Current IP address: {device.getDeviceInfo().name}")
#         # Change the IP address
#         device.setIpAddress(new_ip)
#         print(f"IP address changed to: {new_ip}")

def find_bootloader_device(ip_addr):
    found, info = dai.DeviceBootloader.getAllAvailableDevices()
    ip_addrs = [info.name for info in device_infos]
    ip_addr = max(ip_addrs)
    print(ip_addr)
    if not found:
        print("No POE bootloader device found!")
        return None
    print(f"Found POE device in bootloader: {info.name}")
    return info


def set_static_ip(info, ipv4, mask, gateway):
    conf = dai.DeviceBootloader.Config()
    conf.setStaticIPv4(ipv4, mask, gateway)
    with dai.DeviceBootloader(info) as bl:
        success, error = bl.flashConfig(conf)
        if success:
            print("IP flashed successfully!")
        else:
            print("Failed to flash IP:")

if __name__ == "__main__":
    print(dai.Device.getFirstAvailableDevice()[1])
    device_infos = dai.Device.getAllAvailableDevices()
    print(f'Found {len(device_infos)} devices')
    ip_addrs = [info.name for info in device_infos]
    print('current addresses: ', ip_addrs)

    pipeline = dai.Pipeline()
    active_ip = max(ip_addrs)
    active_info = dai.DeviceInfo(active_ip)
    

    new_ip = "10.95.76.11"
    netmask = "255.255.255.0"
    gateway = "10.95.76.1"
    set_static_ip(active_info, new_ip, netmask, gateway)