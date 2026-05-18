# Copyright (c) farm-ng, inc.
#
# Licensed under the Amiga Development Kit License (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://github.com/farm-ng/amiga-dev-kit/blob/main/LICENSE
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import argparse
import asyncio
from pathlib import Path

from farm_ng.canbus.packet import MotorState
from farm_ng.core.event_client import EventClient
from farm_ng.core.event_service_pb2 import EventServiceConfig
from farm_ng.core.events_file_reader import proto_from_json_file



async def main(service_config_path: Path) -> None:
    """Run the camera service client.

    Args:
        service_config_path (Path): The path to the camera service config.
    """
    # create a client to the camera service
    config: EventServiceConfig = proto_from_json_file(service_config_path, EventServiceConfig())

    # async for event, message in EventClient(config).subscribe(config.subscriptions[0], decode=True):
    #     # Unpack the motor states
    #     motors = []
    #     for motor in message.motors:
    #         motors.append(MotorState.from_proto(motor))
    #     # motor = MotorState()
    #     # Print the motor states
    #     print("\n###################\n")
    #     for motor in sorted(motors, key=lambda m: m.id):
    #         print(f"Motor {motor.id}: RPM = {motor.rpm} at time {motor.timestamp}")

    motor_10_data = [(0,0)]
    rev = 0
    time_prev = 0
    i = 0
         
    async for event, message in EventClient(config).subscribe(config.subscriptions[0], decode=True):
        # Unpack the motor states
        motors = []
        for motor in message.motors:
            motors.append(MotorState.from_proto(motor))
        # motor = MotorState()
        # Print the motor states
        
        for motor in sorted(motors, key=lambda m: m.id):
            if motor.id == 10:                
                motor_10_data.append((motor.rpm, motor.timestamp))
                if i > 10:
                    time_prev = motor_10_data[-2][1]                    
                    rev += motor.rpm/(60*30)*(motor.timestamp - time_prev)
                print(time_prev)     
                print(f"Motor {motor.id}: RPM = {motor.rpm} at time {motor.timestamp}")
                print(rev)
                print("\n###################\n")
                i += 1
                


 
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stream motor states from the canbus service.")
    parser.add_argument("--service-config", type=Path, required=True, help="The camera config.")
    args = parser.parse_args()

    asyncio.run(main(args.service_config)) 
