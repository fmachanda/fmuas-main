import os
import asyncio
import logging
import numpy as np
import math
from configparser import ConfigParser

os.environ['CYPHAL_PATH']='./data_types/custom_data_types;./data_types/public_regulated_data_types'
os.environ['PYCYPHAL_PATH']='./pycyphal_generated'
os.environ['MAVLINK20'] = '1'

from pymavlink import mavutil

import pycyphal
import pycyphal.application
import uavcan_archived
from uavcan_archived.equipment import actuator, esc, ahrs, gnss, range_sensor, air_data
import uavcan

logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)
logging.getLogger('pymavlink').setLevel(logging.ERROR)

os.system('cls' if os.name == 'nt' else 'clear')

DEFAULT_FREQ = 60

system_ids = []

class PID:

    def __init__(self, 
                 kp:float=0.0, 
                 ti:float=0.0, 
                 td:float=0.0, 
                 integral_limit:(float, None)=None, 
                 minimum:(float, None)=None, 
                 maximum:(float, None)=None
                 ) -> None:
        
        self.kp = kp
        self.ti = ti
        self.td = td

        self.integral_limit = integral_limit
        self.minimum = minimum
        self.maximum = maximum

        self._proportional = 0.0
        self._integral = 0.0
        self._derivative = 0.0

        self._error = 0.0
        self.output = 0.0

    def set(self, 
            kp:(float, None)=None, 
            ti:(float, None)=None, 
            td:(float, None)=None, 
            integral_limit:(float, None)=None, 
            minimum:(float, None)=None, 
            maximum:(float, None)=None
            ) -> None:
        
        if kp is not None: self.kp = kp
        if ti is not None: self.ti = ti
        if td is not None: self.td = td

        if integral_limit is not None: self.integral_limit = integral_limit
        if minimum is not None: self.minimum = minimum
        if maximum is not None: self.maximum = maximum

    def reset(self) -> None:
        self._proportional = 0.0
        self._integral = 0.0
        self._derivative = 0.0

        self._error = 0.0
        self.output = 0.0

    def cycle(self, value:float, setpoint:float, time_step:float) -> float:

        ki = (self.kp / self.ti) if (self.ti != 0.0) else 0.0

        time_step /= 1e6
        time_step = max(1e-6, time_step)

        error = setpoint - value

        self._proportional = error

        self._integral += (ki * error * time_step)

        if self.integral_limit is not None:
            self._integral = min(self._integral,  abs(self.integral_limit))
            self._integral = max(self._integral, -abs(self.integral_limit))

        self._derivative = self.td * (error - self._error) / time_step

        output = (self._proportional + self._integral + self._derivative) * self.kp
        
        self._error = error

        if self.minimum is not None:
            output = max(output, self.minimum)

        if self.maximum is not None:
            output = min(output, self.maximum)

        self.output = output
        return self.output

class GlobalRx:
    class Time:
        def __init__(self) -> None:
            self.time = 0.0
            self._last_time = 0.0
            self.dt = 0.0
        
        def dump(self, msg: uavcan.time.SynchronizedTimestamp_1) -> None:
            self._last_time = self.time
            self.time = msg.microsecond
            self.dt = self.time - self._last_time

    class Att:

        def __init__(self) -> None:

            self.time = 0.0
            self.pitch = 0.0
            self.pitchspeed = 0.0
            self.roll = 0.0
            self.rollspeed = 0.0
            self.yaw = 0.0
            self.yawspeed = 0.0

            self._last_time = 0.0
            self.dt = 0.0
            # self._last_pitch = 0.0
            # self._last_pitchspeed = 0.0
            # self._last_roll = 0.0
            # self._last_rollspeed = 0.0
            # self._last_yaw = 0.0
            # self._last_yawspeed = 0.0

        @staticmethod
        def quaternion_to_euler(q:tuple[float, float, float, float]) -> tuple[float, float, float]:
            """
            Convert an quaternion angle to Euler. Copied 10/2/2023 from automaticaddison.com
            
            Input
                :q: Tuple of length 4 with quaternion values [x, y, z, w]
            
            Output
                :return roll, pitch, yaw: The orientation in Euler format
            """
            
            if len(q)!=4: raise ValueError('Quaternion input must be tuple with length 4')

            x, y, z, w = q

            t0 = +2.0 * (w * x + y * z)
            t1 = +1.0 - 2.0 * (x * x + y * y)
            roll = math.atan2(t0, t1)
        
            t2 = +2.0 * (w * y - z * x)
            t2 = +1.0 if t2 > +1.0 else t2
            t2 = -1.0 if t2 < -1.0 else t2
            pitch = math.asin(t2)
        
            t3 = +2.0 * (w * z + x * y)
            t4 = +1.0 - 2.0 * (y * y + z * z)
            yaw = math.atan2(t3, t4)
        
            return roll, pitch, yaw # in radians

        def dump(self, msg: ahrs.Solution_1) -> None:

            self._last_time = self.time
            # self._last_pitch = self.pitch
            # self._last_pitchspeed = self.pitchspeed
            # self._last_roll = self.roll
            # self._last_rollspeed = self.rollspeed
            # self._last_yaw = self.yaw
            # self._last_yawspeed = self.yawspeed

            self.time = msg.timestamp.usec
            self.roll, self.pitch, self.yaw = GlobalRx.Att.quaternion_to_euler(msg.orientation_xyzw)
            if self.yaw < 0: self.yaw += 2*math.pi
            self.rollspeed, self.pitchspeed, self.yawspeed = msg.angular_velocity

            self.dt = self.time - self._last_time

    class Alt:

        def __init__(self) -> None:

            self.time = 0.0
            self.altitude = 0.0
            self.vs = 0.0

            self._last_time = 0.0
            self.dt = 0.0
            self._last_altitude = 0.0
            self._last_vs = 0.0

        def dump(self, msg: range_sensor.Measurement_1) -> None:

            self._last_time = self.time
            self._last_altitude = self.altitude
            self._last_vs = self.vs

            self.time = msg.timestamp.usec
            self.altitude = msg.range_

            try: self.vs = (self.altitude - self._last_altitude) / (self.time - self._last_time)
            except ZeroDivisionError: self.vs = self._last_vs

            self.dt = self.time - self._last_time

    class Gps:

        def __init__(self) -> None:

            self.time = 0.0
            self.latitude = 0.0
            self.longitude = 0.0
            self.altitude = 0.0
            self.xspeed = 0.0
            self.yspeed = 0.0
            self.zspeed = 0.0

            self._last_time = 0.0
            self.dt = 0.0
            # self._last_latitude = 0.0
            # self._last_longitude = 0.0
            # self._last_altitude = 0.0
            # self._last_xspeed = 0.0
            # self._last_yspeed = 0.0
            # self._last_zspeed = 0.0

        def dump(self, msg: gnss.Fix2_1) -> None:

            self._last_time = self.time
            # self._last_latitude = self.latitude
            # self._last_longitude = self.longitude
            # self._last_altitude = self.altitude
            # self._last_xspeed = self.xspeed
            # self._last_yspeed = self.yspeed
            # self._last_zspeed = self.zspeed

            self.time = msg.timestamp.usec
            self.latitude = msg.latitude_deg_1e8# / 1e8
            self.longitude = msg.longitude_deg_1e8# / 1e8
            self.altitude = msg.height_msl_mm / 1e3
            self.xspeed, self.yspeed, self.zspeed= msg.ned_velocity

            self.dt = self.time - self._last_time

    class Ias:

        def __init__(self) -> None:
            self.time = 0.0
            self.ias = 0.0

            self._last_time = 0.0
            self.dt = 0.0
            # self._last_ias = 0.0

        def dump(self, msg: air_data.IndicatedAirspeed_1, time: 'GlobalRx.Time.time') -> None:
            self._last_time = self.time
            # self._last_ias = self.ias
            
            self.time = time
            self.ias = msg.indicated_airspeed

            self.dt = self.time - self._last_time

    class Aoa:

        def __init__(self) -> None:
            self.time = 0.0
            self.aoa = 0.0

            self._last_time = 0.0
            self.dt = 0.0
            # self._last_aoa = 0.0

        def dump(self, msg: air_data.AngleOfAttack_1, time: 'GlobalRx.Time.time') -> None:
            self._last_time = self.time
            # self._last_aoa = self.aoa
            
            self.time = time
            self.aoa = msg.aoa

            self.dt = self.time - self._last_time

    class Slip:

        def __init__(self) -> None:
            self.time = 0.0
            self.slip = 0.0

            self._last_time = 0.0
            self.dt = 0.0
            # self._last_slip = 0.0

        def dump(self, msg: air_data.Sideslip_1, time: 'GlobalRx.Time.time') -> None:
            self._last_time = self.time
            # self._last_slip = self.slip
            
            self.time = time
            self.slip = msg.sideslip_angle

            self.dt = self.time - self._last_time

    def __init__(self) -> None:
        self.time = GlobalRx.Time()
        self.att =  GlobalRx.Att()
        self.alt =  GlobalRx.Alt()
        self.gps =  GlobalRx.Gps()
        self.ias =  GlobalRx.Ias()
        self.aoa =  GlobalRx.Aoa()
        self.slip = GlobalRx.Slip()

class GlobalTx:

    def __init__(self) -> None:
        
        self.servo = actuator.ArrayCommand_1([
                        actuator.Command_1(0, actuator.Command_1.COMMAND_TYPE_POSITION, 0.0), # Elevon 1
                        actuator.Command_1(1, actuator.Command_1.COMMAND_TYPE_POSITION, 0.0), # Elevon 2
                        actuator.Command_1(2, actuator.Command_1.COMMAND_TYPE_POSITION, 0.0), # Rudder
                        actuator.Command_1(3, actuator.Command_1.COMMAND_TYPE_POSITION, 0.0)  # Wing-tilt
                    ])
        
        self.esc = esc.RawCommand_1([
                        int(0.0 * 8191), # Throttle 1
                        int(0.0 * 8191), # Throttle 2
                        int(0.0 * 8191), # Throttle 3
                        int(0.0 * 8191)  # Throttle 4
                    ])

class GlobalState:

    CUSTOM_MODE_UNINIT = 0
    CUSTOM_MODE_BOOT = 1
    CUSTOM_MODE_GROUND = 2
    CUSTOM_MODE_TAKEOFF = 3
    CUSTOM_MODE_FLIGHT = 4
    CUSTOM_MODE_LANDING = 5

    CUSTOM_SUBMODE_UNINIT = 0
    CUSTOM_SUBMODE_BOOT = 10
    CUSTOM_SUBMODE_SHUTDOWN = 11
    CUSTOM_SUBMODE_GROUND_DISARMED = 20
    CUSTOM_SUBMODE_GROUND_ARMED = 21
    CUSTOM_SUBMODE_TAKEOFF_ASCENT = 30
    CUSTOM_SUBMODE_TAKEOFF_HOVER = 31
    CUSTOM_SUBMODE_TAKEOFF_TRANSIT = 32
    CUSTOM_SUBMODE_FLIGHT_NORMAL = 40
    CUSTOM_SUBMODE_FLIGHT_MANUAL = 41
    CUSTOM_SUBMODE_FLIGHT_TERRAIN_AVOIDANCE = 42
    CUSTOM_SUBMODE_LANDING_TRANSIT = 50
    CUSTOM_SUBMODE_LANDING_HOVER = 51
    CUSTOM_SUBMODE_LANDING_DESCENT = 52


    MAV_MODES = [
        mavutil.mavlink.MAV_MODE_PREFLIGHT,
        mavutil.mavlink.MAV_MODE_MANUAL_ARMED,
        # mavutil.mavlink.MAV_MODE_MANUAL_DISARMED,
        mavutil.mavlink.MAV_MODE_GUIDED_ARMED,
        # mavutil.mavlink.MAV_MODE_GUIDED_DISARMED,
        mavutil.mavlink.MAV_MODE_AUTO_ARMED,
        mavutil.mavlink.MAV_MODE_AUTO_DISARMED,
    ]

    MAV_STATES_NOMINAL = [
        mavutil.mavlink.MAV_STATE_UNINIT,
        mavutil.mavlink.MAV_STATE_BOOT,
        mavutil.mavlink.MAV_STATE_CALIBRATING,
        mavutil.mavlink.MAV_STATE_STANDBY,
        mavutil.mavlink.MAV_STATE_ACTIVE,
    ]

    MAV_STATES_ABNORMAL = [
        mavutil.mavlink.MAV_STATE_CRITICAL,
        mavutil.mavlink.MAV_STATE_EMERGENCY,
        mavutil.mavlink.MAV_STATE_POWEROFF,
        # mavutil.mavlink.MAV_STATE_FLIGHT_TERMINATION,
    ]

    CUSTOM_MODES = [
        CUSTOM_MODE_UNINIT,
        CUSTOM_MODE_BOOT,
        CUSTOM_MODE_GROUND,
        CUSTOM_MODE_TAKEOFF,
        CUSTOM_MODE_FLIGHT,
        CUSTOM_MODE_LANDING,
    ]

    CUSTOM_SUBMODES = [
        CUSTOM_SUBMODE_UNINIT,
        CUSTOM_SUBMODE_BOOT,
        CUSTOM_SUBMODE_SHUTDOWN,
        CUSTOM_SUBMODE_GROUND_DISARMED,
        CUSTOM_SUBMODE_GROUND_ARMED,
        CUSTOM_SUBMODE_TAKEOFF_ASCENT,
        CUSTOM_SUBMODE_TAKEOFF_HOVER,
        CUSTOM_SUBMODE_TAKEOFF_TRANSIT,
        CUSTOM_SUBMODE_FLIGHT_NORMAL,
        CUSTOM_SUBMODE_FLIGHT_MANUAL,
        CUSTOM_SUBMODE_FLIGHT_TERRAIN_AVOIDANCE,
        CUSTOM_SUBMODE_LANDING_TRANSIT,
        CUSTOM_SUBMODE_LANDING_HOVER,
        CUSTOM_SUBMODE_LANDING_DESCENT,
    ]


    # Index 0 is default for that submode
    ALLOWED_CUSTOM_MODES = {
        CUSTOM_SUBMODE_UNINIT:[CUSTOM_MODE_UNINIT],
        CUSTOM_SUBMODE_BOOT:[CUSTOM_MODE_BOOT],
        CUSTOM_SUBMODE_SHUTDOWN:[CUSTOM_MODE_BOOT],
        CUSTOM_SUBMODE_GROUND_DISARMED:[CUSTOM_MODE_GROUND],
        CUSTOM_SUBMODE_GROUND_ARMED:[CUSTOM_MODE_GROUND],
        CUSTOM_SUBMODE_TAKEOFF_ASCENT:[CUSTOM_MODE_TAKEOFF],
        CUSTOM_SUBMODE_TAKEOFF_HOVER:[CUSTOM_MODE_TAKEOFF],
        CUSTOM_SUBMODE_TAKEOFF_TRANSIT:[CUSTOM_MODE_TAKEOFF],
        CUSTOM_SUBMODE_FLIGHT_NORMAL:[CUSTOM_MODE_FLIGHT],
        CUSTOM_SUBMODE_FLIGHT_MANUAL:[CUSTOM_MODE_FLIGHT],
        CUSTOM_SUBMODE_FLIGHT_TERRAIN_AVOIDANCE:[CUSTOM_MODE_FLIGHT],
        CUSTOM_SUBMODE_LANDING_TRANSIT:[CUSTOM_MODE_LANDING],
        CUSTOM_SUBMODE_LANDING_HOVER:[CUSTOM_MODE_LANDING],
        CUSTOM_SUBMODE_LANDING_DESCENT:[CUSTOM_MODE_LANDING],
    }

    ALLOWED_MODES = {
        CUSTOM_SUBMODE_UNINIT:[mavutil.mavlink.MAV_MODE_PREFLIGHT],
        CUSTOM_SUBMODE_BOOT:[mavutil.mavlink.MAV_MODE_PREFLIGHT],
        CUSTOM_SUBMODE_SHUTDOWN:[mavutil.mavlink.MAV_MODE_PREFLIGHT],
        CUSTOM_SUBMODE_GROUND_DISARMED:[mavutil.mavlink.MAV_MODE_PREFLIGHT, mavutil.mavlink.MAV_MODE_AUTO_DISARMED],
        CUSTOM_SUBMODE_GROUND_ARMED:[mavutil.mavlink.MAV_MODE_GUIDED_ARMED, mavutil.mavlink.MAV_MODE_AUTO_ARMED],
        CUSTOM_SUBMODE_TAKEOFF_ASCENT:[mavutil.mavlink.MAV_MODE_GUIDED_ARMED, mavutil.mavlink.MAV_MODE_AUTO_ARMED],
        CUSTOM_SUBMODE_TAKEOFF_HOVER:[mavutil.mavlink.MAV_MODE_GUIDED_ARMED, mavutil.mavlink.MAV_MODE_AUTO_ARMED],
        CUSTOM_SUBMODE_TAKEOFF_TRANSIT:[mavutil.mavlink.MAV_MODE_GUIDED_ARMED, mavutil.mavlink.MAV_MODE_AUTO_ARMED],
        CUSTOM_SUBMODE_FLIGHT_NORMAL:[mavutil.mavlink.MAV_MODE_GUIDED_ARMED, mavutil.mavlink.MAV_MODE_AUTO_ARMED],
        CUSTOM_SUBMODE_FLIGHT_MANUAL:[mavutil.mavlink.MAV_MODE_MANUAL_ARMED],
        CUSTOM_SUBMODE_FLIGHT_TERRAIN_AVOIDANCE:[mavutil.mavlink.MAV_MODE_GUIDED_ARMED, mavutil.mavlink.MAV_MODE_AUTO_ARMED],
        CUSTOM_SUBMODE_LANDING_TRANSIT:[mavutil.mavlink.MAV_MODE_GUIDED_ARMED, mavutil.mavlink.MAV_MODE_AUTO_ARMED],
        CUSTOM_SUBMODE_LANDING_HOVER:[mavutil.mavlink.MAV_MODE_GUIDED_ARMED, mavutil.mavlink.MAV_MODE_AUTO_ARMED],
        CUSTOM_SUBMODE_LANDING_DESCENT:[mavutil.mavlink.MAV_MODE_GUIDED_ARMED, mavutil.mavlink.MAV_MODE_AUTO_ARMED],
    }

    ALLOWED_STATES = {
        CUSTOM_SUBMODE_UNINIT:[mavutil.mavlink.MAV_STATE_UNINIT, mavutil.mavlink.MAV_STATE_POWEROFF, mavutil.mavlink.MAV_STATE_CRITICAL],
        CUSTOM_SUBMODE_BOOT:[mavutil.mavlink.MAV_STATE_BOOT, mavutil.mavlink.MAV_STATE_CALIBRATING, mavutil.mavlink.MAV_STATE_STANDBY, mavutil.mavlink.MAV_STATE_CRITICAL],
        CUSTOM_SUBMODE_SHUTDOWN:[mavutil.mavlink.MAV_STATE_POWEROFF, mavutil.mavlink.MAV_STATE_BOOT, mavutil.mavlink.MAV_STATE_CRITICAL],
        CUSTOM_SUBMODE_GROUND_DISARMED:[mavutil.mavlink.MAV_STATE_STANDBY, mavutil.mavlink.MAV_STATE_CRITICAL],
        CUSTOM_SUBMODE_GROUND_ARMED:[mavutil.mavlink.MAV_STATE_ACTIVE, mavutil.mavlink.MAV_STATE_CRITICAL, mavutil.mavlink.MAV_STATE_EMERGENCY],
        CUSTOM_SUBMODE_TAKEOFF_ASCENT:[mavutil.mavlink.MAV_STATE_ACTIVE, mavutil.mavlink.MAV_STATE_CRITICAL, mavutil.mavlink.MAV_STATE_EMERGENCY],
        CUSTOM_SUBMODE_TAKEOFF_HOVER:[mavutil.mavlink.MAV_STATE_ACTIVE, mavutil.mavlink.MAV_STATE_CRITICAL, mavutil.mavlink.MAV_STATE_EMERGENCY],
        CUSTOM_SUBMODE_TAKEOFF_TRANSIT:[mavutil.mavlink.MAV_STATE_ACTIVE, mavutil.mavlink.MAV_STATE_CRITICAL, mavutil.mavlink.MAV_STATE_EMERGENCY],
        CUSTOM_SUBMODE_FLIGHT_NORMAL:[mavutil.mavlink.MAV_STATE_ACTIVE, mavutil.mavlink.MAV_STATE_CRITICAL, mavutil.mavlink.MAV_STATE_EMERGENCY],
        CUSTOM_SUBMODE_FLIGHT_TERRAIN_AVOIDANCE:[mavutil.mavlink.MAV_STATE_ACTIVE, mavutil.mavlink.MAV_STATE_CRITICAL, mavutil.mavlink.MAV_STATE_EMERGENCY],
        CUSTOM_SUBMODE_LANDING_TRANSIT:[mavutil.mavlink.MAV_STATE_ACTIVE, mavutil.mavlink.MAV_STATE_CRITICAL, mavutil.mavlink.MAV_STATE_EMERGENCY],
        CUSTOM_SUBMODE_LANDING_HOVER:[mavutil.mavlink.MAV_STATE_ACTIVE, mavutil.mavlink.MAV_STATE_CRITICAL, mavutil.mavlink.MAV_STATE_EMERGENCY],
        CUSTOM_SUBMODE_LANDING_DESCENT:[mavutil.mavlink.MAV_STATE_ACTIVE, mavutil.mavlink.MAV_STATE_CRITICAL, mavutil.mavlink.MAV_STATE_EMERGENCY],
    }


    # Index 0 is default step up, index 1 is default step down (if applicable)
    ALLOWED_SUBMODE_CHANGES = {
        CUSTOM_SUBMODE_UNINIT:[CUSTOM_SUBMODE_BOOT],
        CUSTOM_SUBMODE_BOOT:[CUSTOM_SUBMODE_GROUND_DISARMED, CUSTOM_SUBMODE_SHUTDOWN],
        CUSTOM_SUBMODE_SHUTDOWN:[CUSTOM_SUBMODE_UNINIT, CUSTOM_SUBMODE_BOOT],
        CUSTOM_SUBMODE_GROUND_DISARMED:[CUSTOM_SUBMODE_GROUND_ARMED, CUSTOM_SUBMODE_SHUTDOWN],
        CUSTOM_SUBMODE_GROUND_ARMED:[CUSTOM_SUBMODE_TAKEOFF_ASCENT, CUSTOM_SUBMODE_GROUND_DISARMED],
        CUSTOM_SUBMODE_TAKEOFF_ASCENT:[CUSTOM_SUBMODE_TAKEOFF_HOVER, CUSTOM_SUBMODE_LANDING_DESCENT],
        CUSTOM_SUBMODE_TAKEOFF_HOVER:[CUSTOM_SUBMODE_TAKEOFF_TRANSIT, CUSTOM_SUBMODE_LANDING_HOVER],
        CUSTOM_SUBMODE_TAKEOFF_TRANSIT:[CUSTOM_SUBMODE_FLIGHT_NORMAL, CUSTOM_SUBMODE_LANDING_TRANSIT],
        CUSTOM_SUBMODE_FLIGHT_NORMAL:[CUSTOM_SUBMODE_LANDING_TRANSIT, CUSTOM_SUBMODE_FLIGHT_TERRAIN_AVOIDANCE, CUSTOM_SUBMODE_FLIGHT_MANUAL],
        CUSTOM_SUBMODE_FLIGHT_MANUAL:[CUSTOM_SUBMODE_FLIGHT_NORMAL],
        CUSTOM_SUBMODE_FLIGHT_TERRAIN_AVOIDANCE:[CUSTOM_SUBMODE_FLIGHT_NORMAL, CUSTOM_SUBMODE_FLIGHT_MANUAL],
        CUSTOM_SUBMODE_LANDING_TRANSIT:[CUSTOM_SUBMODE_LANDING_HOVER, CUSTOM_SUBMODE_TAKEOFF_TRANSIT],
        CUSTOM_SUBMODE_LANDING_HOVER:[CUSTOM_SUBMODE_LANDING_DESCENT, CUSTOM_SUBMODE_TAKEOFF_HOVER],
        CUSTOM_SUBMODE_LANDING_DESCENT:[CUSTOM_SUBMODE_GROUND_ARMED, CUSTOM_SUBMODE_TAKEOFF_ASCENT],
    }


    def __init__(self, state:int, mode:int, custom_mode:int, custom_submode:int, boot:asyncio.Event) -> None:

        state = int(state)
        mode = int(mode)
        custom_mode = int(custom_mode)
        custom_submode = int(custom_submode)

        assert state in GlobalState.MAV_STATES_NOMINAL or state in GlobalState.MAV_STATES_ABNORMAL, 'GlobalState input \'state\' must be MAV_STATE int'
        assert mode in GlobalState.MAV_MODES, 'GlobalState input \'mode\' must be MAV_MODE int'
        assert custom_mode in GlobalState.CUSTOM_MODES, 'GlobalState input \'custom_mode\' must be GlobalState.CUSTOM_MODE int'
        assert custom_submode in GlobalState.CUSTOM_SUBMODES, 'GlobalState input \'custom_submode\' must be GlobalState.CUSTOM_SUBMODE int'
        
        self.state = state
        self.mode = mode
        self.custom_mode = custom_mode
        self.custom_submode = custom_submode
        logging.warning(f'Submode set to: {self.custom_submode}')

        self.boot = boot

    def set_mode(self, mode:int, custom_mode:int, custom_submode:int) -> bool:
       
        try:

            mode = int(mode)
            custom_mode = int(custom_mode)
            custom_submode = int(custom_submode)

            if mode == mavutil.mavlink.MAV_MODE_MANUAL_ARMED and self.custom_mode == GlobalState.CUSTOM_MODE_FLIGHT:

                self.custom_submode = GlobalState.CUSTOM_SUBMODE_FLIGHT_MANUAL
                logging.warning(f'Submode set to: {self.custom_submode}')
                self.mode = mode
                self.state = mavutil.mavlink.MAV_STATE_ACTIVE

                return True

            if self.custom_submode == GlobalState.CUSTOM_SUBMODE_UNINIT and custom_submode == GlobalState.CUSTOM_SUBMODE_BOOT:
                self.boot.set()

            if custom_submode != self.custom_submode:
                assert custom_submode in GlobalState.ALLOWED_SUBMODE_CHANGES[self.custom_submode]
                self.custom_submode = custom_submode
                logging.warning(f'Submode set to: {self.custom_submode}')

                if self.state not in GlobalState.MAV_STATES_ABNORMAL:
                    self.state = GlobalState.ALLOWED_STATES[self.custom_submode][0]

            if mode != self.mode:
                if mode in GlobalState.ALLOWED_MODES[self.custom_submode]:
                    self.mode = mode
                else:
                    self.mode = GlobalState.ALLOWED_MODES[self.custom_submode][0]

            if custom_mode != self.custom_mode:
                if custom_mode in GlobalState.ALLOWED_CUSTOM_MODES[self.custom_submode]:
                    self.custom_mode = custom_mode
                else:
                    self.custom_mode = GlobalState.ALLOWED_CUSTOM_MODES[self.custom_submode][0]

            return True
    
        except AssertionError:

            return False

    def inc_mode(self) -> None:
        
        self.custom_submode = GlobalState.ALLOWED_SUBMODE_CHANGES[self.custom_submode][0]
        logging.warning(f'Submode set to: {self.custom_submode}')
        self.mode = GlobalState.ALLOWED_MODES[self.custom_submode][0]
        self.custom_mode = GlobalState.ALLOWED_CUSTOM_MODES[self.custom_submode][0]

        if self.state not in GlobalState.MAV_STATES_ABNORMAL:
            self.state = GlobalState.ALLOWED_STATES[self.custom_submode][0]

    def dec_mode(self) -> None:

        if self.custom_submode not in [GlobalState.CUSTOM_SUBMODE_FLIGHT_MANUAL, GlobalState.CUSTOM_SUBMODE_FLIGHT_TERRAIN_AVOIDANCE, GlobalState.CUSTOM_SUBMODE_UNINIT]:
           
            self.custom_submode = GlobalState.ALLOWED_SUBMODE_CHANGES[self.custom_submode][1]
            logging.warning(f'Submode set to: {self.custom_submode}')
            self.mode = GlobalState.ALLOWED_MODES[self.custom_submode][0]
            self.custom_mode = GlobalState.ALLOWED_CUSTOM_MODES[self.custom_submode][0]

            if self.state not in GlobalState.MAV_STATES_ABNORMAL:
                self.state = GlobalState.ALLOWED_STATES[self.custom_submode][0]

        else:
            
            logging.debug('Invalid submode for GlobalState.dec_mode(), running GlobalState.inc_mode() instead')
            self.inc_mode()

    def set_state(self, state:int) -> None:

        if (state in GlobalState.MAV_STATES_NOMINAL or state in GlobalState.MAV_STATES_ABNORMAL) and state in GlobalState.ALLOWED_STATES[self.custom_submode]:
            self.state = state
        else:
            logging.debug('Invalid state passed into GlobalState.set_state()')


class MainIO:

    def __init__(self, main:'Main', freq:int=DEFAULT_FREQ) -> None:

        self.main = main

        self._freq = freq

        logging.info('Initializing UAVCAN Node...')

        self._registry = pycyphal.application.make_registry(environment_variables={
            'UAVCAN__NODE__ID'                      :self.main.config.get('node_ids', 'mainio'),
            'UAVCAN__UDP__IFACE'                    :self.main.config.get('main', 'udp'),

            'UAVCAN__SUB__ATTITUDE__ID'             :self.main.config.get('subject_ids', 'attitude'),
            'UAVCAN__SUB__ALTITUDE__ID'             :self.main.config.get('subject_ids', 'altitude'),
            'UAVCAN__SUB__GPS__ID'                  :self.main.config.get('subject_ids', 'gps'),

            'UAVCAN__SUB__IAS__ID'                  :self.main.config.get('subject_ids', 'ias'),
            'UAVCAN__SUB__AOA__ID'                  :self.main.config.get('subject_ids', 'aoa'),
            'UAVCAN__SUB__SLIP__ID'                 :self.main.config.get('subject_ids', 'slip'),

            'UAVCAN__PUB__SERVOS__ID'               :self.main.config.get('subject_ids', 'servo'),
            'UAVCAN__PUB__ESCS__ID'                 :self.main.config.get('subject_ids', 'esc'),

            'UAVCAN__SUB__CLOCK_SYNC_TIME__ID'      :self.main.config.get('subject_ids', 'clock_sync_time'),
            # 'UAVCAN__SUB__CLOCK_SYNC_TIME_LAST__ID' :self.main.config.get('subject_ids', 'clock_sync_time_last'),

            # 'UAVCAN__SUB__GPS_SYNC_TIME__ID'        :self.main.config.get('subject_ids', 'gps_sync_time'),
            # 'UAVCAN__SUB__GPS_SYNC_TIME_LAST__ID'   :self.main.config.get('subject_ids', 'gps_sync_time_last'),

            # 'UAVCAN__CLN__CLOCK_SYNC_INFO__ID'      :self.main.config.get('service_ids', 'clock_sync_info'),
            # 'UAVCAN__CLN__GPS_SYNC_INFO__ID'        :self.main.config.get('service_ids', 'gps_sync_info'),
        })
        
        node_info = uavcan.node.GetInfo_1.Response(
            software_version=uavcan.node.Version_1(major=1, minor=0),
            name=f"fmuas.uasmain{self.main.systemid}.mainio",
        )

        self._node = pycyphal.application.make_node(node_info, self._registry)

        self._node.heartbeat_publisher.mode = uavcan.node.Mode_1.INITIALIZATION
        self._node.heartbeat_publisher.vendor_specific_status_code = os.getpid() % 100
        
        self._sub_att = self._node.make_subscriber(ahrs.Solution_1, 'attitude')
        self._sub_alt = self._node.make_subscriber(range_sensor.Measurement_1, 'altitude')
        self._sub_gps = self._node.make_subscriber(gnss.Fix2_1, 'gps')

        self._sub_ias = self._node.make_subscriber(air_data.IndicatedAirspeed_1, 'ias')
        self._sub_aoa = self._node.make_subscriber(air_data.AngleOfAttack_1, 'aoa')
        self._sub_slip = self._node.make_subscriber(air_data.Sideslip_1, 'slip')

        self._pub_servos = self._node.make_publisher(actuator.ArrayCommand_1, 'servos')
        self._pub_escs = self._node.make_publisher(esc.RawCommand_1, 'escs')

        self._sub_clock_sync_time = self._node.make_subscriber(uavcan.time.SynchronizedTimestamp_1, 'clock_sync_time')
        # self._sub_clock_sync_time_last = self._node.make_subscriber(uavcan.time.Synchronization_1, 'clock_sync_time_last')

        # self._sub_gps_sync_time = self._node.make_subscriber(uavcan.time.SynchronizedTimestamp_1, 'gps_sync_time')
        # self._sub_gps_sync_time_last = self._node.make_subscriber(uavcan.time.Synchronization_1, 'gps_sync_time_last')

        # self._cln_clock_sync_info = self._node.make_client(uavcan.time.GetSynchronizationMasterInfo_0, self.main.config.getint('service_ids', 'clock_sync_info'), 'clock_sync_info')
        # self._cln_gps_sync_info = self._node.make_client(uavcan.time.GetSynchronizationMasterInfo_0, self.main.config.getint('service_ids', 'gps_sync_info'), 'gps_sync_info')

        self._node.start()

        logging.info('MainIO initialized')

    async def boot(self) -> None:
        # TODO do boot stuff here, maybe read a different .ini?
        await asyncio.sleep(0)

    async def run(self) -> None:

        # region Subscriptions
        def on_time(msg: uavcan.time.SynchronizedTimestamp_1, _:pycyphal.transport.TransferFrom) -> None:
            self.main.rxdata.time.dump(msg)
        self._sub_clock_sync_time.receive_in_background(on_time)

        def on_att(msg: ahrs.Solution_1, _:pycyphal.transport.TransferFrom) -> None:
            self.main.rxdata.att.dump(msg)
        self._sub_att.receive_in_background(on_att)

        def on_alt(msg: range_sensor.Measurement_1, _:pycyphal.transport.TransferFrom) -> None:
            self.main.rxdata.alt.dump(msg)
        self._sub_alt.receive_in_background(on_alt)

        def on_gps(msg: gnss.Fix2_1, _:pycyphal.transport.TransferFrom) -> None:
            self.main.rxdata.gps.dump(msg)
        self._sub_gps.receive_in_background(on_gps)

        def on_ias(msg: air_data.IndicatedAirspeed_1, _:pycyphal.transport.TransferFrom) -> None:
            t = self.main.rxdata.time.time
            self.main.rxdata.ias.dump(msg, t)
        self._sub_ias.receive_in_background(on_ias)

        def on_aoa(msg: air_data.AngleOfAttack_1, _:pycyphal.transport.TransferFrom) -> None:
            t = self.main.rxdata.time.time
            self.main.rxdata.aoa.dump(msg, t)
        self._sub_aoa.receive_in_background(on_aoa)

        def on_slip(msg: air_data.Sideslip_1, _:pycyphal.transport.TransferFrom) -> None:
            t = self.main.rxdata.time.time
            self.main.rxdata.slip.dump(msg, t)
        self._sub_slip.receive_in_background(on_slip)
        # endregion
        
        self._node.heartbeat_publisher.mode = uavcan.node.Mode_1.OPERATIONAL

        logging.warning('UAVCAN Node Running...\n----- Ctrl-C to exit -----') # NOTE no verification

        while not self.main.stop.is_set():
            try:
                await self._pub_servos.publish(self.main.txdata.servo)
                await self._pub_escs.publish(self.main.txdata.esc)
                await asyncio.sleep(1 / self._freq)
            except asyncio.exceptions.CancelledError: self.main.stop.set()
            except KeyboardInterrupt: self.main.stop.set()
            except Exception as e:
                logging.error(f'Error in MainIO: {e}')

        self.close()

    def close(self) -> None:
        logging.info('Closing MainIO') # NOTE Change to logging.debug()
        self._node.close()

class Processor:

    def __init__(self, main:'Main') -> None:

        self.main = main

        self._fservos = np.zeros(4, dtype=np.float16) # elevons*2, rudder, wingtilt
        self._vservos = np.zeros(4, dtype=np.float16)

        self._fthrottles = np.zeros(4, dtype=np.float16) # throttles*4
        self._vthrottles = np.zeros(4, dtype=np.float16)

        # self._pid{f or v}_{from}_{to}

        self._pidf_alt_vpa = PID(kp=0.1, td=1.0, ti=2.0, integral_limit=0.2, maximum=4.0, minimum=-3.0)
        self._pidf_vpa_aoa = PID(kp=1.0, ti=2.5, td=0.03, integral_limit=10.0, maximum=16.0, minimum=-3.0)

        self._pidf_aoa_out = PID(kp=-0.25, ti=-0.1, td=0.1, integral_limit=1, maximum=0.0, minimum=-math.pi/12)
        self._pidf_slp_out = PID(kp=-0.15, ti=-0.1, td=0.6, maximum=1.0, minimum=-1.0)
        self._pidf_ias_out = PID(kp=0.04, ti=0.2, td=0.0, integral_limit=0.25, maximum=0.25, minimum=0.02)

        self._pidf_yaw_rol = PID(kp=1.0, ti=1.0, td=0.0, integral_limit=2.0, maximum=30.0, minimum=-30.0)

        self._pidf_rol_rls = PID(kp=5.0, ti=2.5, td=0.01, integral_limit=10.0, maximum=10.0, minimum=-10.0)
        self._pidf_rls_out = PID(kp=0.03, ti=5.0, td=0.01, integral_limit=0.1, maximum=0.1, minimum=-0.1)

        self.spf_altitude = 200.0
        self.spf_heading = 0.0
        self.spf_ias = 80.0

        self._spf_vpath = 0.0
        self._spf_aoa = 0.14
        self._spf_roll = 0.0
        self._spf_rollspeed = 0.0

        self._outf_pitch = 0.0
        self._outf_roll = 0.0
        self._outf_yaw = 0.0
        self._outf_throttle = 0.0

    async def boot(self) -> None:
        # TODO do boot stuff here, maybe read a different .ini?
        await asyncio.sleep(0)

    # region Calculations
    @staticmethod
    def _calc_dyaw(value:float, setpoint:float) -> float: # FIXME if negative radians sent by uavcan
        dyaw = value - setpoint
        dyaw = dyaw - 2*math.pi if dyaw > math.pi else dyaw
        dyaw = dyaw + 2*math.pi if dyaw <= -math.pi else dyaw
        return -dyaw

    def _flight_servos(self) -> np.ndarray:

        if self.main.rxdata.alt.dt > 0.0:
            self._spf_vpath = 0.0 # self._pidf_alt_vpa.cycle(self.main.rxdata.alt.altitude, self.spf_altitude, self.main.rxdata.alt.dt)
            self.main.rxdata.alt.dt = 0.0

        if self.main.rxdata.att.dt > 0.0 or self.main.rxdata.aoa.dt > 0.0:

            if not self.main.rxdata.aoa.dt > 0.0:
                dt = self.main.rxdata.att.dt
            elif not self.main.rxdata.att.dt > 0.0:
                dt = self.main.rxdata.aoa.dt
            else:
                dt = (self.main.rxdata.att.dt + self.main.rxdata.aoa.dt) / 2

            vpath = self.main.rxdata.att.pitch - math.cos(self.main.rxdata.att.roll) * self.main.rxdata.aoa.aoa
            self._spf_aoa = 0.14 # self._pidf_vpa_aoa.cycle(vpath, self._spf_vpath, dt) # FIXME?

        if self.main.rxdata.att.dt > 0.0:

            dyaw = Processor._calc_dyaw(self.main.rxdata.att.yaw, self.spf_heading)

            self._spf_roll = 0.0 # self._pidf_yaw_rol.cycle(dyaw, 0.0, self.main.rxdata.att.dt)
            self._spf_rollspeed = 0.0 # self._pidf_rol_rls.cycle(self.main.rxdata.att.roll, self._spf_roll, self.main.rxdata.att.dt)
            self._outf_roll = self._pidf_rls_out.cycle(self.main.rxdata.att.rollspeed, self._spf_rollspeed, self.main.rxdata.att.dt)

            self.main.rxdata.att.dt = 0.0

        if self.main.rxdata.aoa.dt > 0.0:
            self._outf_pitch = self._pidf_aoa_out.cycle(self.main.rxdata.aoa.aoa, self._spf_aoa, self.main.rxdata.aoa.dt)
            self.main.rxdata.aoa.dt = 0.0

        if self.main.rxdata.slip.dt > 0.0:
            self._outf_yaw = 0.0 # self._pidf_slp_out.cycle(self.main.rxdata.slip.slip, 0.0, self.main.rxdata.slip.dt)
            self.main.rxdata.slip.dt = 0.0

        self._fservos[0] = self._outf_pitch + self._outf_roll # FIXME
        self._fservos[1] = self._outf_pitch - self._outf_roll # FIXME
        self._fservos[2] = self._outf_yaw

        return self._fservos

    def _vtol_servos(self) -> np.ndarray:

        # calculate and write to self._vservos
        return self._vservos

    def _flight_throttles(self) -> np.ndarray:

        if self.main.rxdata.ias.dt > 0.0:
            self._outf_throttle = self._pidf_ias_out.cycle(self.main.rxdata.ias.ias, self.spf_ias, self.main.rxdata.ias.dt)
            self.main.rxdata.ias.dt = 0.0

        self._fthrottles.fill(self._outf_throttle)

        return self._fthrottles

    def _vtol_throttles(self) -> np.ndarray:

        # calculate and write to self._vthrottles
        return self._vthrottles
    # endregion

    async def run(self) -> None:

        logging.info('Starting Processor')
        
        while not self.main.stop.is_set():
            try:

                # NOTE MIXING PLACEHOLDER vvv
                self._servos = np.sum(np.array([1.0 * self._flight_servos(), 0.0 * self._vtol_servos()]), axis=0, dtype=np.float16)
                self._throttles = np.sum(np.array([1.0 * self._flight_throttles(), 0.0 * self._vtol_throttles()]), axis=0, dtype=np.float16)

                self.main.txdata.servo = actuator.ArrayCommand_1([
                    actuator.Command_1(0, actuator.Command_1.COMMAND_TYPE_POSITION, self._servos[0]), # Elevon 1
                    actuator.Command_1(1, actuator.Command_1.COMMAND_TYPE_POSITION, self._servos[1]), # Elevon 2
                    actuator.Command_1(2, actuator.Command_1.COMMAND_TYPE_POSITION, self._servos[2]), # Rudder
                    actuator.Command_1(3, actuator.Command_1.COMMAND_TYPE_POSITION, self._servos[3])  # Wing-tilt
                    ])
                
                self.main.txdata.esc = esc.RawCommand_1([
                    int(self._throttles[0] * 8191), # Throttle 1
                    int(self._throttles[1] * 8191), # Throttle 2
                    int(self._throttles[2] * 8191), # Throttle 3
                    int(self._throttles[3] * 8191)  # Throttle 4
                    ])
                
                await asyncio.sleep(0)

            except asyncio.exceptions.CancelledError:
                self.main.stop.set()
            except KeyboardInterrupt:
                self.main.stop.set()
            except Exception as e:
                logging.error(f'Error in Processor: {e}')

        
        logging.info('Closing Processor') # NOTE Change to logging.debug()


class Controller:
    # Use mavlink to send/recieve information to GCS
    # Send commands to Processor
    # Regulate master modes, boot sequences, handle failures
    
    def __init__(self, main:'Main', tx_freq:int=DEFAULT_FREQ, heartbeat_freq:int=1) -> None:

        self.main = main

        self._txfreq = tx_freq
        self._heartbeatfreq = heartbeat_freq

        self._mav_conn_gcs = mavutil.mavlink_connection(self.main.config.get('mavlink', 'mavlink_conn'), source_system=self.main.systemid, source_component=mavutil.mavlink.MAV_COMP_ID_AUTOPILOT1)

        self._gcs_id = None

        assert isinstance(self._mav_conn_gcs, mavutil.mavfile) # TODO remove

        import key
        self.__key = key.KEY

        self._mav_conn_gcs.setup_signing(self.__key.encode('utf-8'))

    async def manager(self) -> None:
        
        asyncio.create_task(self.heartbeat())
        asyncio.create_task(self.rx())
        asyncio.create_task(self.tx())

        logging.info('Starting Controller')

        while not self.main.stop.is_set():
            try:
                # self.main.boot.set()
                await asyncio.sleep(0)

            except asyncio.exceptions.CancelledError:
                self.main.stop.set()
            except KeyboardInterrupt:
                self.main.stop.set()
            except Exception as e:
                logging.error(f'Error in Controller: {e}')
        
        self.close()

    async def rx(self) -> None:

        logging.debug('Starting Controller (RX)')

        while not self.main.stop.is_set():
            try:
                msg = self._mav_conn_gcs.recv_msg()

                # General messages
                if msg is not None and msg.get_type() == 'HEARTBEAT':
                    logging.debug(f'Heartbeat message from link #{msg.get_srcSystem()}')

                elif msg is not None and msg.get_type() == 'BAD_DATA':
                    pass
                
                # Specific messages
                elif msg is not None and msg.target_system == self.main.systemid:
                    
                    # Connection
                    if msg.get_type() == 'CHANGE_OPERATOR_CONTROL':
                        
                        if msg.control_request == 0 and msg.passkey==self.__key:
                            if self._gcs_id is None or self._gcs_id==msg.get_srcSystem():
                                # Accepted
                                if self._gcs_id!=msg.get_srcSystem(): logging.info(f'Accepting control request from GCS ({msg.get_srcSystem()})')
                                self._gcs_id = msg.get_srcSystem()
                                self._mav_conn_gcs.mav.change_operator_control_ack_send(msg.get_srcSystem(), msg.control_request, 0)

                            else:
                                # Already controlled
                                logging.info(f'Rejecting second control request from {msg.get_srcSystem()}')
                                self._mav_conn_gcs.mav.change_operator_control_ack_send(msg.get_srcSystem(), msg.control_request, 3)

                        elif msg.control_request == 1 and msg.passkey==self.__key:# and self._gcs_id is not None:
                            # Accepted (released)
                            logging.info(f'Releasing from GCS ({self._gcs_id})')
                            self._gcs_id = None
                            self._mav_conn_gcs.mav.change_operator_control_ack_send(msg.get_srcSystem(), msg.control_request, 0)

                        else:
                            # Bad key
                            logging.info(f'Bad key in GCS control request')
                            self._mav_conn_gcs.mav.change_operator_control_ack_send(msg.get_srcSystem(), msg.control_request, 1)

                    # GCS messages
                    if msg.get_srcSystem() == self._gcs_id:

                        if msg.get_type() == 'COMMAND_LONG':

                            if msg.command == mavutil.mavlink.MAV_CMD_DO_SET_MODE:

                                logging.info('Mode change requested')
                                    
                                if self.main.state.set_mode(msg.param1, msg.param2, msg.param3): # TODO Add safety check to verify message like below

                                    self._mav_conn_gcs.mav.command_ack_send(
                                        mavutil.mavlink.MAV_CMD_DO_SET_MODE,
                                        mavutil.mavlink.MAV_RESULT_ACCEPTED,
                                        255,
                                        0,
                                        0, # Target system FIXME
                                        0, # Target component FIXME
                                    )

                                else:

                                    self._mav_conn_gcs.mav.command_ack_send(
                                        mavutil.mavlink.MAV_CMD_DO_SET_MODE,
                                        mavutil.mavlink.MAV_RESULT_DENIED,
                                        255,
                                        0,
                                        0, # Target system FIXME
                                        0, # Target component FIXME
                                    )

                            elif msg.command in ["""list of commands that only use COMMAND_INT"""]:
                                self._mav_conn_gcs.mav.command_ack_send(
                                    mavutil.mavlink.MAV_CMD_DO_SET_MODE,
                                    mavutil.mavlink.MAV_RESULT_COMMAND_INT_ONLY,
                                    255,
                                    0,
                                    0, # Target system FIXME
                                    0, # Target component FIXME
                                )

                            else:
                                self._mav_conn_gcs.mav.command_ack_send(
                                    mavutil.mavlink.MAV_CMD_DO_SET_MODE,
                                    mavutil.mavlink.MAV_RESULT_UNSUPPORTED,
                                    255,
                                    0,
                                    0, # Target system FIXME
                                    0, # Target component FIXME
                                )
                        
                        elif msg.get_type() == 'COMMAND_INT':
                            if msg.command == """command""":
                                pass

                            elif msg.command in [mavutil.mavlink.MAV_CMD_DO_SET_MODE]:
                                self._mav_conn_gcs.mav.command_ack_send(
                                    mavutil.mavlink.MAV_CMD_DO_SET_MODE,
                                    mavutil.mavlink.MAV_RESULT_COMMAND_LONG_ONLY,
                                    255,
                                    0,
                                    0, # Target system FIXME
                                    0, # Target component FIXME
                                )

                            else:
                                self._mav_conn_gcs.mav.command_ack_send(
                                    mavutil.mavlink.MAV_CMD_DO_SET_MODE,
                                    mavutil.mavlink.MAV_RESULT_UNSUPPORTED,
                                    255,
                                    0,
                                    0, # Target system FIXME
                                    0, # Target component FIXME
                                )

                await asyncio.sleep(0)

            except asyncio.exceptions.CancelledError:
                self.main.stop.set()
            except KeyboardInterrupt:
                self.main.stop.set()
            except Exception as e:
                logging.error(f'Error in Controller (RX): {e}')

        logging.debug('Closing Controller (RX)')

    async def tx(self) -> None:

        # Used for transmitting continuous messages,
        # other transmissions should be called as needed
                
        logging.debug('Starting Controller (TX)')

        while not self.main.stop.is_set():
            try:
                # self._mav_conn_gcs.msg_send(None)
                await asyncio.sleep(1 / self._txfreq)

            except asyncio.exceptions.CancelledError:
                self.main.stop.set()
            except KeyboardInterrupt:
                self.main.stop.set()
            except Exception as e:
                logging.error(f'Error in Controller (TX): {e}')

        logging.debug('Closing Controller (TX)')

    async def heartbeat(self) -> None:

        # Used for transmitting eternal messages,
        # other transmissions should be called as needed
                
        logging.debug('Starting Controller (Heartbeat)')

        while not self.main.stop.is_set():
            try:
                self._mav_conn_gcs.mav.heartbeat_send(
                    mavutil.mavlink.MAV_TYPE_VTOL_RESERVED4, # 24
                    mavutil.mavlink.MAV_AUTOPILOT_GENERIC_WAYPOINTS_AND_SIMPLE_NAVIGATION_ONLY,
                    int(self.main.state.mode),
                    int(self.main.state.custom_mode),
                    int(self.main.state.state)
                )
                
                logging.debug('TX Heartbeat')
                
                await asyncio.sleep(1 / self._heartbeatfreq)

            except asyncio.exceptions.CancelledError:
                self.main.stop.set()
            except KeyboardInterrupt:
                self.main.stop.set()
            except Exception as e:
                logging.error(f'Error in Controller (Heartbeat): {e}')

        self._mav_conn_gcs.close()
        logging.debug('Closing Controller (Heartbeat)')

    def close(self) -> None:
        self._mav_conn_gcs.close()
        logging.info('Closing Controller')


class Main:

    def __init__(self, systemid:int=1, config:str='./config.ini') -> None:

        assert (isinstance(systemid, int)) and (systemid > 0) and (systemid.bit_length() <= 8), "System ID must be UINT8"

        self.systemid = systemid

        self.config = ConfigParser()
        self.config.read(config)

        self.boot = asyncio.Event()
        self.stop = asyncio.Event()

        self.rxdata = GlobalRx()
        self.txdata = GlobalTx()

        self.state = GlobalState(mavutil.mavlink.MAV_STATE_UNINIT, mavutil.mavlink.MAV_MODE_PREFLIGHT, GlobalState.CUSTOM_MODE_UNINIT, GlobalState.CUSTOM_SUBMODE_UNINIT, self.boot)

    async def _graph(self, name:str='0.0', freq:int=10) -> None:

        import grapher

        self._grapher = grapher.Grapher(deque_len=50)

        while not self.stop.is_set():
            try:
                self._grapher.add(eval(name))
                self._grapher.graph()
                await asyncio.sleep(1 / freq)

            except asyncio.exceptions.CancelledError:
                self.stop.set()
            except KeyboardInterrupt:
                self.stop.set()
            except Exception as e:
                logging.error(f'Error in Grapher: {e}')

        self._grapher.close()
        logging.info('Closing Grapher')

    async def run(self, graph:str=None) -> None:

        self.controller = Controller(self)
        self.io = MainIO(self)
        self.processor = Processor(self)

        controller_manager = asyncio.create_task(self.controller.manager())
        await asyncio.sleep(0)

        logging.warning(f'Creating instance #{self.systemid}, waiting for boot command from GCS')

        try:
            await asyncio.sleep(1)#self.boot.wait()
        except asyncio.CancelledError or KeyboardInterrupt:
            controller_manager.cancel()
            await asyncio.sleep(0)
            logging.warning(f'Never booted, closing instance #{self.systemid}')
            quit()

        logging.warning(f'Booting instance #{self.systemid}...')

        boot_tasks = [

            asyncio.create_task(self.processor.boot()),
            asyncio.create_task(self.io.boot()),

        ]

        try:
            await asyncio.gather(*boot_tasks)
        except asyncio.exceptions.CancelledError:
            controller_manager.cancel()
            await asyncio.sleep(0)
            logging.warning(f'Ctrl-C during boot cycle, closing instance #{self.systemid}')
            quit()

        self.state.inc_mode()
        logging.warning(f'Boot successful on #{self.systemid}')

        for _ in range(6):
            self.state.inc_mode()

        tasks = [

            asyncio.create_task(self.processor.run()),
            asyncio.create_task(self.io.run()),

        ]

        if graph is not None: 
            logging.info('Grapher on')
            tasks.append(asyncio.create_task(self._graph(name=graph)))

        try:
            await asyncio.gather(*tasks)
        except asyncio.exceptions.CancelledError: self.stop.set()

        logging.warning(f'Closing instance #{self.systemid}')

if __name__ == "__main__":

    main = Main(132)
    asyncio.run(main.run(graph='main.rxdata.att.rollspeed'))