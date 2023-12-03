import asyncio
import calendar
import datetime
import logging
import math
import os
import shutil
import sys
import threading
import time
from configparser import ConfigParser
from functools import wraps

os.chdir(os.path.dirname(os.path.realpath(__file__)) + '/../../..')
sys.path.append(os.getcwd())
for var in os.environ:
    if var.startswith('UAVCAN__'):
        os.environ.pop(var)
os.environ['CYPHAL_PATH']='./common/public_regulated_data_types'
os.environ['PYCYPHAL_PATH']='./common/pycyphal_generated'
os.environ['UAVCAN__DIAGNOSTIC__SEVERITY'] = '2'
os.environ['MAVLINK20'] = '1'
os.environ['MAVLINK_DIALECT'] = 'common'

filehandler = logging.FileHandler('uav/xpio.log', mode='a')
filehandler.setLevel(logging.INFO)
filehandler.setFormatter(logging.Formatter(str(os.getpid()) + ' (%(asctime)s %(name)s) %(levelname)s:%(message)s'))
streamhandler = logging.StreamHandler()
streamhandler.setLevel(logging.INFO)
logging.basicConfig(format='%(name)s %(levelname)s:%(message)s', level=logging.DEBUG, handlers=[filehandler, streamhandler])

MAVLOG_DEBUG = logging.DEBUG - 3
MAVLOG_TX = logging.DEBUG - 2
MAVLOG_RX = logging.DEBUG - 1
MAVLOG_LOG = logging.INFO + 1

logging.warning("Generating UAVCAN files, please wait...")

import pycyphal
import reg.udral.service.actuator.common
import reg.udral.service.common
import reg.udral.physics.electricity
import reg.udral.physics.dynamics.rotation
import reg.udral.physics.kinematics.cartesian
import reg.udral.physics.kinematics.translation
import reg.udral.physics.kinematics.geodetic
import uavcan.node
import uavcan.time
import uavcan.si.unit.temperature
import uavcan.si.unit.angle
import uavcan.si.unit.length
import uavcan.si.unit.velocity
import uavcan.si.unit.angular_velocity
import pycyphal.application
from pymavlink import mavutil

try:
    import xp
except ImportError:
    pass

#region from_common
def _clip(value: float):
#     """Clips value to valid domain for inverse trig functions."""
    return max(min(value, 1), -1)

def py_to_rp(Pc: float, Yc: float) -> tuple[float, float]:
    """Convert angles from pitch/yaw frame to roll/pitch frame."""
    assert -90<=Pc<=90, "Input pitch angle must be between -90 degrees and 90 degrees."
    # print("------------------")
    # print("Input: ", Pc, Yc)
    Pc = math.radians(Pc)
    Yc = math.radians(Yc)

    Pd = math.acos(math.cos(Pc) * math.cos(Yc))
    # print("Pd: ", math.degrees(Pd))

    try:
        # print("asin: ", _clip(math.cos(Pc) * math.sin(Yc) / math.sin(Pd)))
        Rd = math.asin(_clip(math.cos(Pc) * math.sin(Yc) / math.sin(Pd)))
        # print("Rd v1: ", math.degrees(Rd))
        Rd = -(Rd + math.pi) if Pc<0 else Rd
        # print("Rd v2: ", math.degrees(Rd))
    except ZeroDivisionError:
        Rd = 0.0
        # print("Rd err: ", math.degrees(Rd))

    Pd = round(math.degrees(Pd), 5)
    Rd = round(math.degrees(Rd), 5)

    # assert abs(math.sin(Pd)*math.cos(Rd) - math.sin(Pc)) < 1e-6
    return Rd, Pd

def quaternion_to_euler(q: list[float, float, float, float]) -> tuple[float, float, float]:
    """Convert a quaternion angle to Euler. 

    Copied on 10/2/2023 from automaticaddison.com
    
    Parameters
    ----------
    q : tuple[float, float, float, float]
        The quaternion values w, x, y, z
    
    Returns
    -------
    tuple[float, float, float]
        A tuple of roll, pitch, yaw as radians in Euler format
    
    Raises
    ------
    ValueError
        If the input is not of length 4
    """

    if len(q)!=4:
        raise ValueError("Quaternion input must be tuple with length 4")

    w, x, y, z = q

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
#endregion

m = mavutil.mavlink

for name in ['pymavlink', 'pycyphal', 'pydsdl', 'nunavut']:
    logging.getLogger(name).setLevel(logging.WARNING)
filehandler.setLevel(logging.DEBUG)

config = ConfigParser()
config.read('./common/config.ini')

db_config = ConfigParser()
db_config.read('./common/_db_config.ini')

os.system('cls' if os.name == 'nt' else 'clear')

stop = asyncio.Event()

rx_data = {
    b'fmuas/att/attitude_quaternion_x': 0.0, # 0
    b'fmuas/att/attitude_quaternion_y': 0.0,
    b'fmuas/att/attitude_quaternion_z': 0.0,
    b'fmuas/att/attitude_quaternion_w': 0.0,
    b'fmuas/att/rollrate': 0.0,
    b'fmuas/att/pitchrate': 0.0,
    b'fmuas/att/yawrate': 0.0,

    b'fmuas/gps/latitude': 0.0,
    b'fmuas/gps/longitude': 0.0,
    b'fmuas/gps/altitude': 0.0,
    b'fmuas/gps/vn': 0.0,
    b'fmuas/gps/ve': 0.0,
    b'fmuas/gps/vd': 0.0,

    b'fmuas/radalt/altitude': 0.0,

    b'fmuas/adc/ias': 0.0,
    b'fmuas/adc/aoa': 0.0,
    
    b'sim/time/paused': 1.0, # xp.Type_Int
    b'sim/time/local_date_days': 0.0, # xp.Type_Int
    b'sim/time/zulu_time_sec': 0.0, # xp.Type_Float
    b'fmuas/clock/time': 0.0,

    b'fmuas/camera/pitch_actual': 0.0,
    b'fmuas/camera/roll_actual': 0.0,
}

tx_data = {
    b'fmuas/afcs/output/elevon1': 90.0,
    b'fmuas/afcs/output/elevon2': 90.0,
    b'fmuas/afcs/output/wing_tilt': 0.0,
    b'fmuas/afcs/output/wing_stow': 0.0,
    b'fmuas/afcs/output/rpm1': 0.0,
    b'fmuas/afcs/output/rpm2': 0.0,
    b'fmuas/afcs/output/rpm3': 0.0,
    b'fmuas/afcs/output/rpm4': 0.0,
    b'fmuas/camera/roll': 0.0,
    b'fmuas/camera/pitch': 180.0,
    b'fmuas/python_running': 1.0
}

COMPILE_DB = False
XP_FIND_TIMEOUT = 1
TX_DATA_FIRST_ESC = 4 # Index of first esc dref in tx_data
XP_FREQ = 50
FREQ = 50
FT_TO_M = 3.048e-1
KT_TO_MS = 5.14444e-1
RADS_TO_RPM = 30/math.pi

def async_loop_decorator(close=True):
    """Provide decorator to gracefully loop coroutines."""
    def decorator(func):
        @wraps(func) # Preserve metadata like func.__name__
        async def wrapper(self: 'MotorHub | SensorHub | GPS | Clock | Camera', *args, **kwargs):
            try:
                while not stop.is_set():
                    try:
                        await asyncio.sleep(0)
                        await func(self, *args, **kwargs)
                    except asyncio.exceptions.CancelledError:
                        stop.set()
                        raise
                    except Exception as e:
                        logging.error(f"Error in {func.__name__}: {e}")
                        raise # TODO
            except KeyboardInterrupt:
                stop.set()
                raise
            finally:
                if close:
                    await self.close()
                else:
                    logging.debug(f"Closing {func.__name__}")
        return wrapper
    return decorator


def get_xp_time() -> int:
    """Get monotonic microseconds from X-Plane with jump handling."""
    _xpsecs = rx_data[b'fmuas/clock/time']

    if abs(_xpsecs - get_xp_time._last_xpsecs) > 1.0: # Time jump
        logging.debug("XP time jumped")
        get_xp_time._secs += 1e-6
    elif _xpsecs == get_xp_time._last_xpsecs and rx_data[b'sim/time/paused'] != 1.0: # No time but running
        get_xp_time._secs += time.monotonic() - get_xp_time._last_time
    elif rx_data[b'sim/time/paused'] != 1.0: # Normal and running
        get_xp_time._last_real += _xpsecs - get_xp_time._last_xpsecs
        get_xp_time._secs = get_xp_time._last_real

    get_xp_time._last_time = time.monotonic()
    get_xp_time._last_xpsecs = _xpsecs
    return int(get_xp_time._secs*1e6)
get_xp_time._last_xpsecs = 0.0
get_xp_time._secs = 0.0
get_xp_time._last_time = time.monotonic()
get_xp_time._last_real = 0.0


class MotorHub:
    def __init__(self, freq: int = FREQ) -> None:
        if COMPILE_DB:
            if os.path.exists(f:='./'+config.get('db_files', 'motorhub')):
                os.remove(f)
                logging.debug(f"Removing preexisting {f}")
            logging.debug(f"Compiling {f}")

            _registry = pycyphal.application.make_registry(environment_variables={
                'UAVCAN__NODE__ID'                      :db_config.get('node_ids', 'motorhub'),
                'UAVCAN__UDP__IFACE'                    :db_config.get('main', 'udp'),

                'UAVCAN__SUB__SERVO_READINESS__ID'      :db_config.get('subject_ids', 'servo_readiness'),
                'UAVCAN__SUB__ESC_READINESS__ID'        :db_config.get('subject_ids', 'esc_readiness'),

                'UAVCAN__SUB__ELEVON1_SP__ID'           :db_config.get('subject_ids', 'elevon1_sp'),
                'UAVCAN__PUB__ELEVON1_FEEDBACK__ID'     :db_config.get('subject_ids', 'elevon1_feedback'),
                'UAVCAN__PUB__ELEVON1_STATUS__ID'       :db_config.get('subject_ids', 'elevon1_status'),
                'UAVCAN__PUB__ELEVON1_POWER__ID'        :db_config.get('subject_ids', 'elevon1_power'),
                'UAVCAN__PUB__ELEVON1_DYNAMICS__ID'     :db_config.get('subject_ids', 'elevon1_dynamics'),

                'UAVCAN__SUB__ELEVON2_SP__ID'           :db_config.get('subject_ids', 'elevon2_sp'),
                'UAVCAN__PUB__ELEVON2_FEEDBACK__ID'     :db_config.get('subject_ids', 'elevon2_feedback'),
                'UAVCAN__PUB__ELEVON2_STATUS__ID'       :db_config.get('subject_ids', 'elevon2_status'),
                'UAVCAN__PUB__ELEVON2_POWER__ID'        :db_config.get('subject_ids', 'elevon2_power'),
                'UAVCAN__PUB__ELEVON2_DYNAMICS__ID'     :db_config.get('subject_ids', 'elevon2_dynamics'),

                'UAVCAN__SUB__TILT_SP__ID'              :db_config.get('subject_ids', 'tilt_sp'),
                'UAVCAN__PUB__TILT_FEEDBACK__ID'        :db_config.get('subject_ids', 'tilt_feedback'),
                'UAVCAN__PUB__TILT_STATUS__ID'          :db_config.get('subject_ids', 'tilt_status'),
                'UAVCAN__PUB__TILT_POWER__ID'           :db_config.get('subject_ids', 'tilt_power'),
                'UAVCAN__PUB__TILT_DYNAMICS__ID'        :db_config.get('subject_ids', 'tilt_dynamics'),

                'UAVCAN__SUB__STOW_SP__ID'              :db_config.get('subject_ids', 'stow_sp'),
                'UAVCAN__PUB__STOW_FEEDBACK__ID'        :db_config.get('subject_ids', 'stow_feedback'),
                'UAVCAN__PUB__STOW_STATUS__ID'          :db_config.get('subject_ids', 'stow_status'),
                'UAVCAN__PUB__STOW_POWER__ID'           :db_config.get('subject_ids', 'stow_power'),
                'UAVCAN__PUB__STOW_DYNAMICS__ID'        :db_config.get('subject_ids', 'stow_dynamics'),

                'UAVCAN__SUB__ESC1_SP__ID'              :db_config.get('subject_ids', 'esc1_sp'),
                'UAVCAN__PUB__ESC1_FEEDBACK__ID'        :db_config.get('subject_ids', 'esc1_feedback'),
                'UAVCAN__PUB__ESC1_STATUS__ID'          :db_config.get('subject_ids', 'esc1_status'),
                'UAVCAN__PUB__ESC1_POWER__ID'           :db_config.get('subject_ids', 'esc1_power'),
                'UAVCAN__PUB__ESC1_DYNAMICS__ID'        :db_config.get('subject_ids', 'esc1_dynamics'),

                'UAVCAN__SUB__ESC2_SP__ID'              :db_config.get('subject_ids', 'esc2_sp'),
                'UAVCAN__PUB__ESC2_FEEDBACK__ID'        :db_config.get('subject_ids', 'esc2_feedback'),
                'UAVCAN__PUB__ESC2_STATUS__ID'          :db_config.get('subject_ids', 'esc2_status'),
                'UAVCAN__PUB__ESC2_POWER__ID'           :db_config.get('subject_ids', 'esc2_power'),
                'UAVCAN__PUB__ESC2_DYNAMICS__ID'        :db_config.get('subject_ids', 'esc2_dynamics'),

                'UAVCAN__SUB__ESC3_SP__ID'              :db_config.get('subject_ids', 'esc3_sp'),
                'UAVCAN__PUB__ESC3_FEEDBACK__ID'        :db_config.get('subject_ids', 'esc3_feedback'),
                'UAVCAN__PUB__ESC3_STATUS__ID'          :db_config.get('subject_ids', 'esc3_status'),
                'UAVCAN__PUB__ESC3_POWER__ID'           :db_config.get('subject_ids', 'esc3_power'),
                'UAVCAN__PUB__ESC3_DYNAMICS__ID'        :db_config.get('subject_ids', 'esc3_dynamics'),

                'UAVCAN__SUB__ESC4_SP__ID'              :db_config.get('subject_ids', 'esc4_sp'),
                'UAVCAN__PUB__ESC4_FEEDBACK__ID'        :db_config.get('subject_ids', 'esc4_feedback'),
                'UAVCAN__PUB__ESC4_STATUS__ID'          :db_config.get('subject_ids', 'esc4_status'),
                'UAVCAN__PUB__ESC4_POWER__ID'           :db_config.get('subject_ids', 'esc4_power'),
                'UAVCAN__PUB__ESC4_DYNAMICS__ID'        :db_config.get('subject_ids', 'esc4_dynamics'),
            })

            for var in os.environ:
                if var.startswith('UAVCAN__'):
                    os.environ.pop(var, None)
            for var, value in _registry.environment_variables.items():
                assert isinstance(value, bytes)
                os.environ[var] = value.decode('utf-8')

        self._freq = freq
        
        node_info = uavcan.node.GetInfo_1.Response(
            software_version=uavcan.node.Version_1(major=1, minor=0),
            name='fmuas.motorhub',
        )

        self._registry = pycyphal.application.make_registry(config.get('db_files', 'motorhub'))
        self._node = pycyphal.application.make_node(node_info, self._registry)

        self._node.heartbeat_publisher.mode = uavcan.node.Mode_1.INITIALIZATION
        self._node.heartbeat_publisher.vendor_specific_status_code = os.getpid() % 100

        self._sub_servo_readiness = self._node.make_subscriber(reg.udral.service.common.Readiness_0, 'servo_readiness')
        self._sub_esc_readiness = self._node.make_subscriber(reg.udral.service.common.Readiness_0, 'esc_readiness')

        self._sub_elevon1_sp = self._node.make_subscriber(reg.udral.physics.dynamics.rotation.Planar_0, 'elevon1_sp')
        self._pub_elevon1_feedback = self._node.make_publisher(reg.udral.service.actuator.common.Feedback_0, 'elevon1_feedback')
        self._pub_elevon1_status = self._node.make_publisher(reg.udral.service.actuator.common.Status_0, 'elevon1_status')
        self._pub_elevon1_power = self._node.make_publisher(reg.udral.physics.electricity.PowerTs_0, 'elevon1_power')
        self._pub_elevon1_dynamics = self._node.make_publisher(reg.udral.physics.dynamics.rotation.PlanarTs_0, 'elevon1_dynamics')

        self._sub_elevon2_sp = self._node.make_subscriber(reg.udral.physics.dynamics.rotation.Planar_0, 'elevon2_sp')
        self._pub_elevon2_feedback = self._node.make_publisher(reg.udral.service.actuator.common.Feedback_0, 'elevon2_feedback')
        self._pub_elevon2_status = self._node.make_publisher(reg.udral.service.actuator.common.Status_0, 'elevon2_status')
        self._pub_elevon2_power = self._node.make_publisher(reg.udral.physics.electricity.PowerTs_0, 'elevon2_power')
        self._pub_elevon2_dynamics = self._node.make_publisher(reg.udral.physics.dynamics.rotation.PlanarTs_0, 'elevon2_dynamics')

        self._sub_tilt_sp = self._node.make_subscriber(reg.udral.physics.dynamics.rotation.Planar_0, 'tilt_sp')
        self._pub_tilt_feedback = self._node.make_publisher(reg.udral.service.actuator.common.Feedback_0, 'tilt_feedback')
        self._pub_tilt_status = self._node.make_publisher(reg.udral.service.actuator.common.Status_0, 'tilt_status')
        self._pub_tilt_power = self._node.make_publisher(reg.udral.physics.electricity.PowerTs_0, 'tilt_power')
        self._pub_tilt_dynamics = self._node.make_publisher(reg.udral.physics.dynamics.rotation.PlanarTs_0, 'tilt_dynamics')

        self._sub_stow_sp = self._node.make_subscriber(reg.udral.physics.dynamics.rotation.Planar_0, 'stow_sp')
        self._pub_stow_feedback = self._node.make_publisher(reg.udral.service.actuator.common.Feedback_0, 'stow_feedback')
        self._pub_stow_status = self._node.make_publisher(reg.udral.service.actuator.common.Status_0, 'stow_status')
        self._pub_stow_power = self._node.make_publisher(reg.udral.physics.electricity.PowerTs_0, 'stow_power')
        self._pub_stow_dynamics = self._node.make_publisher(reg.udral.physics.dynamics.rotation.PlanarTs_0, 'stow_dynamics')

        self._sub_esc1_sp = self._node.make_subscriber(reg.udral.physics.dynamics.rotation.Planar_0, 'esc1_sp')
        self._pub_esc1_feedback = self._node.make_publisher(reg.udral.service.actuator.common.Feedback_0, 'esc1_feedback')
        self._pub_esc1_status = self._node.make_publisher(reg.udral.service.actuator.common.Status_0, 'esc1_status')
        self._pub_esc1_power = self._node.make_publisher(reg.udral.physics.electricity.PowerTs_0, 'esc1_power')
        self._pub_esc1_dynamics = self._node.make_publisher(reg.udral.physics.dynamics.rotation.PlanarTs_0, 'esc1_dynamics')

        self._sub_esc2_sp = self._node.make_subscriber(reg.udral.physics.dynamics.rotation.Planar_0, 'esc2_sp')
        self._pub_esc2_feedback = self._node.make_publisher(reg.udral.service.actuator.common.Feedback_0, 'esc2_feedback')
        self._pub_esc2_status = self._node.make_publisher(reg.udral.service.actuator.common.Status_0, 'esc2_status')
        self._pub_esc2_power = self._node.make_publisher(reg.udral.physics.electricity.PowerTs_0, 'esc2_power')
        self._pub_esc2_dynamics = self._node.make_publisher(reg.udral.physics.dynamics.rotation.PlanarTs_0, 'esc2_dynamics')

        self._sub_esc3_sp = self._node.make_subscriber(reg.udral.physics.dynamics.rotation.Planar_0, 'esc3_sp')
        self._pub_esc3_feedback = self._node.make_publisher(reg.udral.service.actuator.common.Feedback_0, 'esc3_feedback')
        self._pub_esc3_status = self._node.make_publisher(reg.udral.service.actuator.common.Status_0, 'esc3_status')
        self._pub_esc3_power = self._node.make_publisher(reg.udral.physics.electricity.PowerTs_0, 'esc3_power')
        self._pub_esc3_dynamics = self._node.make_publisher(reg.udral.physics.dynamics.rotation.PlanarTs_0, 'esc3_dynamics')

        self._sub_esc4_sp = self._node.make_subscriber(reg.udral.physics.dynamics.rotation.Planar_0, 'esc4_sp')
        self._pub_esc4_feedback = self._node.make_publisher(reg.udral.service.actuator.common.Feedback_0, 'esc4_feedback')
        self._pub_esc4_status = self._node.make_publisher(reg.udral.service.actuator.common.Status_0, 'esc4_status')
        self._pub_esc4_power = self._node.make_publisher(reg.udral.physics.electricity.PowerTs_0, 'esc4_power')
        self._pub_esc4_dynamics = self._node.make_publisher(reg.udral.physics.dynamics.rotation.PlanarTs_0, 'esc4_dynamics')

        self._srv_exec_cmd = self._node.get_server(uavcan.node.ExecuteCommand_1)

        self._sub_servo_readiness.receive_in_background(self._on_servo_readiness)
        self._sub_esc_readiness.receive_in_background(self._on_esc_readiness)
        self._sub_elevon1_sp.receive_in_background(self._on_elevon1_sp)
        self._sub_elevon2_sp.receive_in_background(self._on_elevon2_sp)
        self._sub_tilt_sp.receive_in_background(self._on_tilt_sp)
        self._sub_stow_sp.receive_in_background(self._on_stow_sp)
        self._sub_esc1_sp.receive_in_background(self._on_esc1_sp)
        self._sub_esc2_sp.receive_in_background(self._on_esc2_sp)
        self._sub_esc3_sp.receive_in_background(self._on_esc3_sp)
        self._sub_esc4_sp.receive_in_background(self._on_esc4_sp)

        self._srv_exec_cmd.serve_in_background(self._serve_exec_cmd)

        self._servo_readiness = reg.udral.service.common.Readiness_0.ENGAGED
        self._esc_readiness = reg.udral.service.common.Readiness_0.ENGAGED

        now = time.monotonic()
        self._elevon1_publish_time = now
        self._elevon2_publish_time = now
        self._tilt_publish_time = now
        self._stow_publish_time = now
        self._esc1_publish_time = now
        self._esc2_publish_time = now
        self._esc3_publish_time = now
        self._esc4_publish_time = now
        self._status_publish_time = now

        self._node.start()

    async def _serve_exec_cmd(
            self,
            request: uavcan.node.ExecuteCommand_1.Request, 
            metadata: pycyphal.presentation.ServiceRequestMetadata,) -> uavcan.node.ExecuteCommand_1.Response:
        logging.info("Execute command request %s from node %d", request, metadata.client_node_id)
        match request.command:
            case uavcan.node.ExecuteCommand_1.Request.COMMAND_POWER_OFF:
                return uavcan.node.ExecuteCommand_1.Response(
                    uavcan.node.ExecuteCommand_1.Response.STATUS_NOT_AUTHORIZED
                )
            case uavcan.node.ExecuteCommand_1.Request.COMMAND_RESTART:
                return uavcan.node.ExecuteCommand_1.Response(
                    uavcan.node.ExecuteCommand_1.Response.STATUS_NOT_AUTHORIZED
                )
            case uavcan.node.ExecuteCommand_1.Request.COMMAND_EMERGENCY_STOP:
                return uavcan.node.ExecuteCommand_1.Response(
                    uavcan.node.ExecuteCommand_1.Response.STATUS_NOT_AUTHORIZED
                )
            case uavcan.node.ExecuteCommand_1.Request.COMMAND_FACTORY_RESET:
                return uavcan.node.ExecuteCommand_1.Response(
                    uavcan.node.ExecuteCommand_1.Response.STATUS_NOT_AUTHORIZED
                )
            case uavcan.node.ExecuteCommand_1.Request.COMMAND_STORE_PERSISTENT_STATES:
                return uavcan.node.ExecuteCommand_1.Response(
                    uavcan.node.ExecuteCommand_1.Response.STATUS_NOT_AUTHORIZED
                )
            case uavcan.node.ExecuteCommand_1.Request.COMMAND_BEGIN_SOFTWARE_UPDATE:
                return uavcan.node.ExecuteCommand_1.Response(
                    uavcan.node.ExecuteCommand_1.Response.STATUS_NOT_AUTHORIZED
                )
            case _:
                return uavcan.node.ExecuteCommand_1.Response(
                    uavcan.node.ExecuteCommand_1.Response.STATUS_BAD_COMMAND
                )

    @async_loop_decorator()
    async def _motorhub_run_loop(self) -> None:
        now = time.monotonic()

        if now > self._elevon1_publish_time + 1.0:
            await self._pub_elevon1_feedback.publish(reg.udral.service.actuator.common.Feedback_0(
                reg.udral.service.common.Heartbeat_0(
                    reg.udral.service.common.Readiness_0(self._servo_readiness),
                    uavcan.node.Health_1(uavcan.node.Health_1.NOMINAL)
                )
            ))
            await self._pub_elevon1_power.publish(reg.udral.physics.electricity.PowerTs_0())
            await self._pub_elevon1_dynamics.publish(reg.udral.physics.dynamics.rotation.PlanarTs_0())
            self._elevon1_publish_time = now

        if now > self._elevon2_publish_time + 1.0:
            await self._pub_elevon2_feedback.publish(reg.udral.service.actuator.common.Feedback_0(
                reg.udral.service.common.Heartbeat_0(
                    reg.udral.service.common.Readiness_0(self._servo_readiness),
                    uavcan.node.Health_1(uavcan.node.Health_1.NOMINAL)
                )
            ))
            await self._pub_elevon2_power.publish(reg.udral.physics.electricity.PowerTs_0())
            await self._pub_elevon2_dynamics.publish(reg.udral.physics.dynamics.rotation.PlanarTs_0())
            self._elevon2_publish_time = now

        if now > self._tilt_publish_time + 1.0:
            await self._pub_tilt_feedback.publish(reg.udral.service.actuator.common.Feedback_0(
                reg.udral.service.common.Heartbeat_0(
                    reg.udral.service.common.Readiness_0(self._servo_readiness),
                    uavcan.node.Health_1(uavcan.node.Health_1.NOMINAL)
                )
            ))
            await self._pub_tilt_power.publish(reg.udral.physics.electricity.PowerTs_0())
            await self._pub_tilt_dynamics.publish(reg.udral.physics.dynamics.rotation.PlanarTs_0())
            self._tilt_publish_time = now

        if now > self._stow_publish_time + 1.0:
            await self._pub_stow_feedback.publish(reg.udral.service.actuator.common.Feedback_0(
                reg.udral.service.common.Heartbeat_0(
                    reg.udral.service.common.Readiness_0(self._servo_readiness),
                    uavcan.node.Health_1(uavcan.node.Health_1.NOMINAL)
                )
            ))
            await self._pub_stow_power.publish(reg.udral.physics.electricity.PowerTs_0())
            await self._pub_stow_dynamics.publish(reg.udral.physics.dynamics.rotation.PlanarTs_0())
            self._stow_publish_time = now

        if now > self._esc1_publish_time + 1.0:
            await self._pub_esc1_feedback.publish(reg.udral.service.actuator.common.Feedback_0(
                reg.udral.service.common.Heartbeat_0(
                    reg.udral.service.common.Readiness_0(self._esc_readiness),
                    uavcan.node.Health_1(uavcan.node.Health_1.NOMINAL)
                )
            ))
            await self._pub_esc1_power.publish(reg.udral.physics.electricity.PowerTs_0())
            await self._pub_esc1_dynamics.publish(reg.udral.physics.dynamics.rotation.PlanarTs_0())
            self._esc1_publish_time = now

        if now > self._esc2_publish_time + 1.0:
            await self._pub_esc2_feedback.publish(reg.udral.service.actuator.common.Feedback_0(
                reg.udral.service.common.Heartbeat_0(
                    reg.udral.service.common.Readiness_0(self._esc_readiness),
                    uavcan.node.Health_1(uavcan.node.Health_1.NOMINAL)
                )
            ))
            await self._pub_esc2_power.publish(reg.udral.physics.electricity.PowerTs_0())
            await self._pub_esc2_dynamics.publish(reg.udral.physics.dynamics.rotation.PlanarTs_0())
            self._esc2_publish_time = now

        if now > self._esc3_publish_time + 1.0:
            await self._pub_esc3_feedback.publish(reg.udral.service.actuator.common.Feedback_0(
                reg.udral.service.common.Heartbeat_0(
                    reg.udral.service.common.Readiness_0(self._esc_readiness),
                    uavcan.node.Health_1(uavcan.node.Health_1.NOMINAL)
                )
            ))
            await self._pub_esc3_power.publish(reg.udral.physics.electricity.PowerTs_0())
            await self._pub_esc3_dynamics.publish(reg.udral.physics.dynamics.rotation.PlanarTs_0())
            self._esc3_publish_time = now

        if now > self._esc4_publish_time + 1.0:
            await self._pub_esc4_feedback.publish(reg.udral.service.actuator.common.Feedback_0(
                reg.udral.service.common.Heartbeat_0(
                    reg.udral.service.common.Readiness_0(self._esc_readiness),
                    uavcan.node.Health_1(uavcan.node.Health_1.NOMINAL)
                )
            ))
            await self._pub_esc4_power.publish(reg.udral.physics.electricity.PowerTs_0())
            await self._pub_esc4_dynamics.publish(reg.udral.physics.dynamics.rotation.PlanarTs_0())
            self._esc4_publish_time = now

        if now > self._status_publish_time + 1.0:
            await self._pub_elevon1_status.publish(reg.udral.service.actuator.common.Status_0())
            await self._pub_elevon2_status.publish(reg.udral.service.actuator.common.Status_0())
            await self._pub_tilt_status.publish(reg.udral.service.actuator.common.Status_0())
            await self._pub_stow_status.publish(reg.udral.service.actuator.common.Status_0())
            await self._pub_esc1_status.publish(reg.udral.service.actuator.common.Status_0())
            await self._pub_esc2_status.publish(reg.udral.service.actuator.common.Status_0())
            await self._pub_esc3_status.publish(reg.udral.service.actuator.common.Status_0())
            await self._pub_esc4_status.publish(reg.udral.service.actuator.common.Status_0())
            self._status_publish_time = now

        await asyncio.sleep(1 / self._freq)

    #region Subscribers
    def _on_servo_readiness(self, msg: reg.udral.service.common.Readiness_0, _: pycyphal.transport.TransferFrom) -> None:
        self._servo_readiness = msg.value

    def _on_esc_readiness(self, msg: reg.udral.service.common.Readiness_0, _: pycyphal.transport.TransferFrom) -> None:
        self._esc_readiness = msg.value

    def _on_elevon1_sp(self, msg: reg.udral.physics.dynamics.rotation.Planar_0, _: pycyphal.transport.TransferFrom) -> None:
        tx_data[b'fmuas/afcs/output/elevon1'] = math.degrees(msg.kinematics.angular_position.radian)
        try:
            self._pub_elevon1_feedback.publish_soon(reg.udral.service.actuator.common.Feedback_0(
                reg.udral.service.common.Heartbeat_0(
                    reg.udral.service.common.Readiness_0(self._servo_readiness),
                    uavcan.node.Health_1(uavcan.node.Health_1.NOMINAL)
                )
            ))
            self._pub_elevon1_power.publish_soon(reg.udral.physics.electricity.PowerTs_0())
            self._pub_elevon1_dynamics.publish_soon(reg.udral.physics.dynamics.rotation.PlanarTs_0())
        except pycyphal.presentation._port._error.PortClosedError:
            pass
        else:
            self._elevon1_publish_time = time.monotonic()

    def _on_elevon2_sp(self, msg: reg.udral.physics.dynamics.rotation.Planar_0, _: pycyphal.transport.TransferFrom) -> None:
        tx_data[b'fmuas/afcs/output/elevon2'] = math.degrees(msg.kinematics.angular_position.radian)
        try:
            self._pub_elevon2_feedback.publish_soon(reg.udral.service.actuator.common.Feedback_0(
                reg.udral.service.common.Heartbeat_0(
                    reg.udral.service.common.Readiness_0(self._servo_readiness),
                    uavcan.node.Health_1(uavcan.node.Health_1.NOMINAL)
                )
            ))
            self._pub_elevon2_power.publish_soon(reg.udral.physics.electricity.PowerTs_0())
            self._pub_elevon2_dynamics.publish_soon(reg.udral.physics.dynamics.rotation.PlanarTs_0())
        except pycyphal.presentation._port._error.PortClosedError:
            pass
        else:
            self._elevon2_publish_time = time.monotonic()

    def _on_tilt_sp(self, msg: reg.udral.physics.dynamics.rotation.Planar_0, _: pycyphal.transport.TransferFrom) -> None:
        tx_data[b'fmuas/afcs/output/wing_tilt'] = math.degrees(msg.kinematics.angular_position.radian)
        try:
            self._pub_tilt_feedback.publish_soon(reg.udral.service.actuator.common.Feedback_0(
                reg.udral.service.common.Heartbeat_0(
                    reg.udral.service.common.Readiness_0(self._servo_readiness),
                    uavcan.node.Health_1(uavcan.node.Health_1.NOMINAL)
                )
            ))
            self._pub_tilt_power.publish_soon(reg.udral.physics.electricity.PowerTs_0())
            self._pub_tilt_dynamics.publish_soon(reg.udral.physics.dynamics.rotation.PlanarTs_0())
        except pycyphal.presentation._port._error.PortClosedError:
            pass
        else:
            self._tilt_publish_time = time.monotonic()

    def _on_stow_sp(self, msg: reg.udral.physics.dynamics.rotation.Planar_0, _: pycyphal.transport.TransferFrom) -> None:
        tx_data[b'fmuas/afcs/output/wing_stow'] = math.degrees(msg.kinematics.angular_position.radian)
        try:
            self._pub_stow_feedback.publish_soon(reg.udral.service.actuator.common.Feedback_0(
                reg.udral.service.common.Heartbeat_0(
                    reg.udral.service.common.Readiness_0(self._servo_readiness),
                    uavcan.node.Health_1(uavcan.node.Health_1.NOMINAL)
                )
            ))
            self._pub_stow_power.publish_soon(reg.udral.physics.electricity.PowerTs_0())
            self._pub_stow_dynamics.publish_soon(reg.udral.physics.dynamics.rotation.PlanarTs_0())
        except pycyphal.presentation._port._error.PortClosedError:
            pass
        else:
            self._stow_publish_time = time.monotonic()

    def _on_esc1_sp(self, msg: reg.udral.physics.dynamics.rotation.Planar_0, _: pycyphal.transport.TransferFrom) -> None:
        tx_data[b'fmuas/afcs/output/rpm1'] = msg.kinematics.angular_velocity.radian_per_second * (30/math.pi)
        try:
            self._pub_esc1_feedback.publish_soon(reg.udral.service.actuator.common.Feedback_0(
                reg.udral.service.common.Heartbeat_0(
                    reg.udral.service.common.Readiness_0(self._esc_readiness),
                    uavcan.node.Health_1(uavcan.node.Health_1.NOMINAL)
                )
            ))
            self._pub_esc1_power.publish_soon(reg.udral.physics.electricity.PowerTs_0())
            self._pub_esc1_dynamics.publish_soon(reg.udral.physics.dynamics.rotation.PlanarTs_0())
        except pycyphal.presentation._port._error.PortClosedError:
            pass
        else:
            self._esc1_publish_time = time.monotonic()

    def _on_esc2_sp(self, msg: reg.udral.physics.dynamics.rotation.Planar_0, _: pycyphal.transport.TransferFrom) -> None:
        tx_data[b'fmuas/afcs/output/rpm2'] = msg.kinematics.angular_velocity.radian_per_second * (30/math.pi)
        try:
            self._pub_esc2_feedback.publish_soon(reg.udral.service.actuator.common.Feedback_0(
                reg.udral.service.common.Heartbeat_0(
                    reg.udral.service.common.Readiness_0(self._esc_readiness),
                    uavcan.node.Health_1(uavcan.node.Health_1.NOMINAL)
                )
            ))
            self._pub_esc2_power.publish_soon(reg.udral.physics.electricity.PowerTs_0())
            self._pub_esc2_dynamics.publish_soon(reg.udral.physics.dynamics.rotation.PlanarTs_0())
        except pycyphal.presentation._port._error.PortClosedError:
            pass
        else:
            self._esc2_publish_time = time.monotonic()

    def _on_esc3_sp(self, msg: reg.udral.physics.dynamics.rotation.Planar_0, _: pycyphal.transport.TransferFrom) -> None:
        tx_data[b'fmuas/afcs/output/rpm3'] = msg.kinematics.angular_velocity.radian_per_second * (30/math.pi)
        try:
            self._pub_esc3_feedback.publish_soon(reg.udral.service.actuator.common.Feedback_0(
                reg.udral.service.common.Heartbeat_0(
                    reg.udral.service.common.Readiness_0(self._esc_readiness),
                    uavcan.node.Health_1(uavcan.node.Health_1.NOMINAL)
                )
            ))
            self._pub_esc3_power.publish_soon(reg.udral.physics.electricity.PowerTs_0())
            self._pub_esc3_dynamics.publish_soon(reg.udral.physics.dynamics.rotation.PlanarTs_0())
        except pycyphal.presentation._port._error.PortClosedError:
            pass
        else:
            self._esc3_publish_time = time.monotonic()

    def _on_esc4_sp(self, msg: reg.udral.physics.dynamics.rotation.Planar_0, _: pycyphal.transport.TransferFrom) -> None:
        tx_data[b'fmuas/afcs/output/rpm4'] = msg.kinematics.angular_velocity.radian_per_second * (30/math.pi)
        try:
            self._pub_esc4_feedback.publish_soon(reg.udral.service.actuator.common.Feedback_0(
                reg.udral.service.common.Heartbeat_0(
                    reg.udral.service.common.Readiness_0(self._esc_readiness),
                    uavcan.node.Health_1(uavcan.node.Health_1.NOMINAL)
                )
            ))
            self._pub_esc4_power.publish_soon(reg.udral.physics.electricity.PowerTs_0())
            self._pub_esc4_dynamics.publish_soon(reg.udral.physics.dynamics.rotation.PlanarTs_0())
        except pycyphal.presentation._port._error.PortClosedError:
            pass
        else:
            self._esc4_publish_time = time.monotonic()
    #endregion
        
    async def run(self) -> None:
        """docstring placeholder"""
        self._node.heartbeat_publisher.mode = uavcan.node.Mode_1.OPERATIONAL
        await self._motorhub_run_loop()

    async def close(self) -> None:
        logging.debug("Closing MOT")
        self._node.close()


class SensorHub:
    def __init__(self, freq: int = FREQ) -> None:
        if COMPILE_DB:
            if os.path.exists(f:='./'+config.get('db_files', 'sensorhub')):
                os.remove(f)
                logging.debug(f"Removing preexisting {f}")
            logging.debug(f"Compiling {f}")

            _registry = pycyphal.application.make_registry(environment_variables={
                'UAVCAN__NODE__ID'                      :db_config.get('node_ids', 'sensorhub'),
                'UAVCAN__UDP__IFACE'                    :db_config.get('main', 'udp'),

                'UAVCAN__PUB__INERTIAL__ID'             :db_config.get('subject_ids', 'inertial'),
                'UAVCAN__PUB__ALTITUDE__ID'             :db_config.get('subject_ids', 'altitude'),
                'UAVCAN__PUB__IAS__ID'                  :db_config.get('subject_ids', 'ias'),
                'UAVCAN__PUB__AOA__ID'                  :db_config.get('subject_ids', 'aoa'),

                'UAVCAN__SUB__CLOCK_SYNC_TIME__ID'      :db_config.get('subject_ids', 'clock_sync_time'),
                'UAVCAN__SUB__GPS_SYNC_TIME__ID'        :db_config.get('subject_ids', 'gps_sync_time')
            })
            
            for var in os.environ:
                if var.startswith('UAVCAN__'):
                    os.environ.pop(var, None)
            for var, value in _registry.environment_variables.items():
                assert isinstance(value, bytes)
                os.environ[var] = value.decode('utf-8')

        self._freq = freq
        self._time = 0.0
        self._use_gps_time = False
        
        node_info = uavcan.node.GetInfo_1.Response(
            software_version=uavcan.node.Version_1(major=1, minor=0),
            name='fmuas.sensorhub',
        )

        self._registry = pycyphal.application.make_registry(config.get('db_files', 'sensorhub'))
        self._node = pycyphal.application.make_node(node_info, self._registry)

        self._node.heartbeat_publisher.mode = uavcan.node.Mode_1.INITIALIZATION
        self._node.heartbeat_publisher.vendor_specific_status_code = os.getpid() % 100
        
        self._pub_ins = self._node.make_publisher(reg.udral.physics.kinematics.cartesian.StateVarTs_0, 'inertial')
        self._pub_alt = self._node.make_publisher(uavcan.si.unit.length.WideScalar_1, 'altitude')
        self._pub_ias = self._node.make_publisher(reg.udral.physics.kinematics.translation.LinearTs_0, 'ias')
        self._pub_aoa = self._node.make_publisher(uavcan.si.unit.angle.Scalar_1, 'aoa')

        self._sub_clock_sync_time = self._node.make_subscriber(uavcan.time.SynchronizedTimestamp_1, 'clock_sync_time')
        self._sub_clock_sync_time_last = self._node.make_subscriber(uavcan.time.Synchronization_1)

        self._sub_gps_sync_time = self._node.make_subscriber(uavcan.time.SynchronizedTimestamp_1, 'gps_sync_time')
        self._sub_gps_sync_time_last = self._node.make_subscriber(uavcan.time.Synchronization_1)

        # TODO: remove db_config dependency
        self._cln_clock_sync_info = self._node.make_client(uavcan.time.GetSynchronizationMasterInfo_0, db_config.getint('node_ids', 'clock'))
        self._cln_gps_sync_info = self._node.make_client(uavcan.time.GetSynchronizationMasterInfo_0, db_config.getint('node_ids', 'gps'))

        self._srv_exec_cmd = self._node.get_server(uavcan.node.ExecuteCommand_1)

        self._sub_clock_sync_time.receive_in_background(self._on_time)
        self._sub_clock_sync_time_last.receive_in_background(self._on_time_last)
        self._sub_gps_sync_time.receive_in_background(self._on_gps_time)
        self._sub_gps_sync_time_last.receive_in_background(self._on_gps_time_last)

        self._srv_exec_cmd.serve_in_background(self._serve_exec_cmd)

        self._node.start()

    async def _serve_exec_cmd(
            self,
            request: uavcan.node.ExecuteCommand_1.Request, 
            metadata: pycyphal.presentation.ServiceRequestMetadata,) -> uavcan.node.ExecuteCommand_1.Response:
        logging.info("Execute command request %s from node %d", request, metadata.client_node_id)
        match request.command:
            case uavcan.node.ExecuteCommand_1.Request.COMMAND_POWER_OFF:
                return uavcan.node.ExecuteCommand_1.Response(
                    uavcan.node.ExecuteCommand_1.Response.STATUS_NOT_AUTHORIZED
                )
            case uavcan.node.ExecuteCommand_1.Request.COMMAND_RESTART:
                return uavcan.node.ExecuteCommand_1.Response(
                    uavcan.node.ExecuteCommand_1.Response.STATUS_NOT_AUTHORIZED
                )
            case uavcan.node.ExecuteCommand_1.Request.COMMAND_EMERGENCY_STOP:
                return uavcan.node.ExecuteCommand_1.Response(
                    uavcan.node.ExecuteCommand_1.Response.STATUS_NOT_AUTHORIZED
                )
            case uavcan.node.ExecuteCommand_1.Request.COMMAND_FACTORY_RESET:
                return uavcan.node.ExecuteCommand_1.Response(
                    uavcan.node.ExecuteCommand_1.Response.STATUS_NOT_AUTHORIZED
                )
            case uavcan.node.ExecuteCommand_1.Request.COMMAND_STORE_PERSISTENT_STATES:
                return uavcan.node.ExecuteCommand_1.Response(
                    uavcan.node.ExecuteCommand_1.Response.STATUS_NOT_AUTHORIZED
                )
            case uavcan.node.ExecuteCommand_1.Request.COMMAND_BEGIN_SOFTWARE_UPDATE:
                return uavcan.node.ExecuteCommand_1.Response(
                    uavcan.node.ExecuteCommand_1.Response.STATUS_NOT_AUTHORIZED
                )
            case _:
                return uavcan.node.ExecuteCommand_1.Response(
                    uavcan.node.ExecuteCommand_1.Response.STATUS_BAD_COMMAND
                )

    @async_loop_decorator()
    async def _sensorhub_run_loop(self) -> None:
        await self._pub_ins.publish(reg.udral.physics.kinematics.cartesian.StateVarTs_0(
            uavcan.time.SynchronizedTimestamp_1(self._time),
            reg.udral.physics.kinematics.cartesian.StateVar_0(
                reg.udral.physics.kinematics.cartesian.PoseVar_0(
                    reg.udral.physics.kinematics.cartesian.Pose_0(
                        # position,
                        orientation = uavcan.si.unit.angle.Quaternion_1(
                            [
                                rx_data[b'fmuas/att/attitude_quaternion_w'],
                                rx_data[b'fmuas/att/attitude_quaternion_x'], 
                                rx_data[b'fmuas/att/attitude_quaternion_y'], 
                                rx_data[b'fmuas/att/attitude_quaternion_z']
                            ]
                        )
                    ),
                    # covariance
                ),
                reg.udral.physics.kinematics.cartesian.TwistVar_0(
                    reg.udral.physics.kinematics.cartesian.Twist_0(
                        uavcan.si.unit.velocity.Vector3_1(
                            # TODO: inertial velocity
                            [rx_data[b'fmuas/gps/vn'], rx_data[b'fmuas/gps/ve'], rx_data[b'fmuas/gps/vd']],
                        ),
                        uavcan.si.unit.angular_velocity.Vector3_1(
                            # TODO: not extrinsic
                            [
                                rx_data[b'fmuas/att/rollrate'],
                                rx_data[b'fmuas/att/pitchrate'],
                                rx_data[b'fmuas/att/yawrate'],
                            ],
                        )
                    ),
                    # covariance
                )
            )
        ))

        await self._pub_ias.publish(reg.udral.physics.kinematics.translation.LinearTs_0(
            uavcan.time.SynchronizedTimestamp_1(self._time),
            reg.udral.physics.kinematics.translation.Linear_0(
                velocity = uavcan.si.unit.velocity.Scalar_1(rx_data[b'fmuas/adc/ias'])
            )
        ))

        await self._pub_alt.publish(uavcan.si.unit.length.WideScalar_1(rx_data[b'fmuas/radalt/altitude']))
        await self._pub_aoa.publish(uavcan.si.unit.angle.Scalar_1(rx_data[b'fmuas/adc/aoa']))

        await asyncio.sleep(1 / self._freq)

    def _on_time(self, msg: uavcan.time.SynchronizedTimestamp_1, _: pycyphal.transport.TransferFrom) -> None:
        self._time = msg.microsecond

    def _on_time_last(self, msg: uavcan.time.SynchronizedTimestamp_1, info: pycyphal.transport.TransferFrom) -> None:
        pass # TODO

    def _on_gps_time(self, msg: uavcan.time.SynchronizedTimestamp_1, _: pycyphal.transport.TransferFrom) -> None:
        if self._use_gps_time:
            self._time = msg.microsecond

    def _on_gps_time_last(self, msg: uavcan.time.SynchronizedTimestamp_1, info: pycyphal.transport.TransferFrom) -> None:
        pass # TODO

    async def run(self) -> None:
        """docstring placeholder"""
        self._node.heartbeat_publisher.mode = uavcan.node.Mode_1.OPERATIONAL
        await self._sensorhub_run_loop()

    async def close(self) -> None:
        logging.debug("Closing SNS")
        self._node.close()


class GPS:
    def __init__(self, freq: int = FREQ) -> None:
        if COMPILE_DB:
            if os.path.exists(f:='./'+config.get('db_files', 'gps')):
                os.remove(f)
                logging.debug(f"Removing preexisting {f}")
            logging.debug(f"Compiling {f}")
            
            _registry = pycyphal.application.make_registry(environment_variables={
                'UAVCAN__NODE__ID'                      :db_config.get('node_ids', 'gps'),
                'UAVCAN__UDP__IFACE'                    :db_config.get('main', 'udp'),

                'UAVCAN__PUB__GPS__ID'                  :db_config.get('subject_ids', 'gps'),
                'UAVCAN__PUB__GPS_SYNC_TIME__ID'        :db_config.get('subject_ids', 'gps_sync_time'),

                'UAVCAN__SUB__CLOCK_SYNC_TIME__ID'      :db_config.get('subject_ids', 'clock_sync_time'),
            })
            
            for var in os.environ:
                if var.startswith('UAVCAN__'):
                    os.environ.pop(var, None)
            for var, value in _registry.environment_variables.items():
                assert isinstance(value, bytes)
                os.environ[var] = value.decode('utf-8')

        self._freq = freq
        self._time = 0.0
        self._gnss_time = 0.0
        
        node_info = uavcan.node.GetInfo_1.Response(
            software_version=uavcan.node.Version_1(major=1, minor=0),
            name='fmuas.gps',
        )

        self._registry = pycyphal.application.make_registry(config.get('db_files', 'gps'))
        self._node = pycyphal.application.make_node(node_info, self._registry)

        self._node.heartbeat_publisher.mode = uavcan.node.Mode_1.INITIALIZATION
        self._node.heartbeat_publisher.vendor_specific_status_code = os.getpid() % 100
        
        self._pub_gps = self._node.make_publisher(reg.udral.physics.kinematics.geodetic.PointStateVarTs_0, 'gps')
        
        self._srv_sync_info = self._node.get_server(uavcan.time.GetSynchronizationMasterInfo_0)
        self._srv_sync_info.serve_in_background(self._serve_sync_master_info)
        
        self._pub_gps_sync_time = self._node.make_publisher(uavcan.time.SynchronizedTimestamp_1, 'gps_sync_time')
        self._pub_gps_sync_time_last = self._node.make_publisher(uavcan.time.Synchronization_1)

        self._sub_clock_sync_time = self._node.make_subscriber(uavcan.time.SynchronizedTimestamp_1, 'clock_sync_time')
        self._sub_clock_sync_time_last = self._node.make_subscriber(uavcan.time.Synchronization_1)

        # TODO: remove db_config dependency
        self._cln_clock_sync_info = self._node.make_client(uavcan.time.GetSynchronizationMasterInfo_0, db_config.getint('node_ids', 'clock'))

        self._srv_exec_cmd = self._node.get_server(uavcan.node.ExecuteCommand_1)

        self._sub_clock_sync_time.receive_in_background(self._on_time)
        self._sub_clock_sync_time_last.receive_in_background(self._on_time_last)

        self._srv_exec_cmd.serve_in_background(self._serve_exec_cmd)

        self._node.start()

    async def _serve_exec_cmd(
            self,
            request: uavcan.node.ExecuteCommand_1.Request, 
            metadata: pycyphal.presentation.ServiceRequestMetadata,) -> uavcan.node.ExecuteCommand_1.Response:
        logging.info("Execute command request %s from node %d", request, metadata.client_node_id)
        match request.command:
            case uavcan.node.ExecuteCommand_1.Request.COMMAND_POWER_OFF:
                return uavcan.node.ExecuteCommand_1.Response(
                    uavcan.node.ExecuteCommand_1.Response.STATUS_NOT_AUTHORIZED
                )
            case uavcan.node.ExecuteCommand_1.Request.COMMAND_RESTART:
                return uavcan.node.ExecuteCommand_1.Response(
                    uavcan.node.ExecuteCommand_1.Response.STATUS_NOT_AUTHORIZED
                )
            case uavcan.node.ExecuteCommand_1.Request.COMMAND_EMERGENCY_STOP:
                return uavcan.node.ExecuteCommand_1.Response(
                    uavcan.node.ExecuteCommand_1.Response.STATUS_NOT_AUTHORIZED
                )
            case uavcan.node.ExecuteCommand_1.Request.COMMAND_FACTORY_RESET:
                return uavcan.node.ExecuteCommand_1.Response(
                    uavcan.node.ExecuteCommand_1.Response.STATUS_NOT_AUTHORIZED
                )
            case uavcan.node.ExecuteCommand_1.Request.COMMAND_STORE_PERSISTENT_STATES:
                return uavcan.node.ExecuteCommand_1.Response(
                    uavcan.node.ExecuteCommand_1.Response.STATUS_NOT_AUTHORIZED
                )
            case uavcan.node.ExecuteCommand_1.Request.COMMAND_BEGIN_SOFTWARE_UPDATE:
                return uavcan.node.ExecuteCommand_1.Response(
                    uavcan.node.ExecuteCommand_1.Response.STATUS_NOT_AUTHORIZED
                )
            case _:
                return uavcan.node.ExecuteCommand_1.Response(
                    uavcan.node.ExecuteCommand_1.Response.STATUS_BAD_COMMAND
                )

    @staticmethod
    async def _serve_sync_master_info(
            request: uavcan.time.GetSynchronizationMasterInfo_0.Request, 
            metadata: pycyphal.presentation.ServiceRequestMetadata,) -> uavcan.time.GetSynchronizationMasterInfo_0.Response:
        logging.info("Execute command request %s from node %d", request, metadata.client_node_id)
        return uavcan.time.GetSynchronizationMasterInfo_0.Response(
            0.0, # error_variance
            uavcan.time.TimeSystem_0(uavcan.time.TimeSystem_0.TAI),
            uavcan.time.TAIInfo_0(uavcan.time.TAIInfo_0.DIFFERENCE_TAI_MINUS_GPS)
        )
    
    @async_loop_decorator()
    async def _gps_run_loop(self) -> None:
        await self._pub_gps_sync_time_last.publish(uavcan.time.Synchronization_1(self._gnss_time))

        self._gnss_time = int(1e6*(calendar.timegm(datetime.datetime.strptime(str(datetime.date.today().year), '%Y').timetuple())
                             + (1+rx_data[b'sim/time/local_date_days'])*86400
                             + rx_data[b'sim/time/zulu_time_sec']))

        await self._pub_gps.publish(reg.udral.physics.kinematics.geodetic.PointStateVarTs_0(
            uavcan.time.SynchronizedTimestamp_1(self._time),
            reg.udral.physics.kinematics.geodetic.PointStateVar_0(
                reg.udral.physics.kinematics.geodetic.PointVar_0(
                    reg.udral.physics.kinematics.geodetic.Point_0(
                        rx_data[b'fmuas/gps/longitude'], # TODO: rads
                        rx_data[b'fmuas/gps/latitude'], # TODO: rads
                        uavcan.si.unit.length.WideScalar_1(
                            rx_data[b'fmuas/gps/altitude']
                        )
                    ),
                    # covariance
                ),
                reg.udral.physics.kinematics.translation.Velocity3Var_0(
                    uavcan.si.unit.velocity.Vector3_1(
                        [rx_data[b'fmuas/gps/vn'], rx_data[b'fmuas/gps/ve'], rx_data[b'fmuas/gps/vd']]
                    ),
                    # covariance
                )
            )
        ))

        await self._pub_gps_sync_time.publish(uavcan.time.SynchronizedTimestamp_1(self._gnss_time))
        
        await asyncio.sleep(1 / self._freq)

    def _on_time(self, msg: uavcan.time.SynchronizedTimestamp_1, _: pycyphal.transport.TransferFrom) -> None:
        self._time = msg.microsecond

    def _on_time_last(self, msg: uavcan.time.SynchronizedTimestamp_1, info: pycyphal.transport.TransferFrom) -> None:
        pass

    async def run(self) -> None:
        """docstring placeholder"""
        self._node.heartbeat_publisher.mode = uavcan.node.Mode_1.OPERATIONAL
        await self._gps_run_loop()

    async def close(self) -> None:
        logging.debug("Closing GPS")
        self._node.close()


class Clock:
    def __init__(self) -> None:
        if COMPILE_DB:
            if os.path.exists(f:='./'+config.get('db_files', 'clock')):
                os.remove(f)
                logging.debug(f"Removing preexisting {f}")
            logging.debug(f"Compiling {f}")
            
            _registry = pycyphal.application.make_registry(environment_variables={
                'UAVCAN__NODE__ID'                      :db_config.get('node_ids', 'clock'),
                'UAVCAN__UDP__IFACE'                    :db_config.get('main', 'udp'),

                'UAVCAN__PUB__CLOCK_SYNC_TIME__ID'      :db_config.get('subject_ids', 'clock_sync_time'),
            })
            
            for var in os.environ:
                if var.startswith('UAVCAN__'):
                    os.environ.pop(var, None)
            for var, value in _registry.environment_variables.items():
                assert isinstance(value, bytes)
                os.environ[var] = value.decode('utf-8')
            
        self._sync_time = 0.0
        
        node_info = uavcan.node.GetInfo_1.Response(
            software_version=uavcan.node.Version_1(major=1, minor=0),
            name='fmuas.clock',
        )

        self._registry = pycyphal.application.make_registry(config.get('db_files', 'clock'))
        self._node = pycyphal.application.make_node(node_info, self._registry)

        self._node.heartbeat_publisher.mode = uavcan.node.Mode_1.INITIALIZATION
        self._node.heartbeat_publisher.vendor_specific_status_code = os.getpid() % 100
        
        self._srv_sync_info = self._node.get_server(uavcan.time.GetSynchronizationMasterInfo_0)
        self._srv_sync_info.serve_in_background(self._serve_sync_master_info)
        
        self._pub_sync_time = self._node.make_publisher(uavcan.time.SynchronizedTimestamp_1, 'clock_sync_time')
        self._pub_sync_time_last = self._node.make_publisher(uavcan.time.Synchronization_1)

        self._srv_exec_cmd = self._node.get_server(uavcan.node.ExecuteCommand_1)
        self._srv_exec_cmd.serve_in_background(self._serve_exec_cmd)

        self._node.start()

    async def _serve_exec_cmd(
            self,
            request: uavcan.node.ExecuteCommand_1.Request, 
            metadata: pycyphal.presentation.ServiceRequestMetadata,) -> uavcan.node.ExecuteCommand_1.Response:
        logging.info("Execute command request %s from node %d", request, metadata.client_node_id)
        match request.command:
            case uavcan.node.ExecuteCommand_1.Request.COMMAND_POWER_OFF:
                return uavcan.node.ExecuteCommand_1.Response(
                    uavcan.node.ExecuteCommand_1.Response.STATUS_NOT_AUTHORIZED
                )
            case uavcan.node.ExecuteCommand_1.Request.COMMAND_RESTART:
                return uavcan.node.ExecuteCommand_1.Response(
                    uavcan.node.ExecuteCommand_1.Response.STATUS_NOT_AUTHORIZED
                )
            case uavcan.node.ExecuteCommand_1.Request.COMMAND_EMERGENCY_STOP:
                return uavcan.node.ExecuteCommand_1.Response(
                    uavcan.node.ExecuteCommand_1.Response.STATUS_NOT_AUTHORIZED
                )
            case uavcan.node.ExecuteCommand_1.Request.COMMAND_FACTORY_RESET:
                return uavcan.node.ExecuteCommand_1.Response(
                    uavcan.node.ExecuteCommand_1.Response.STATUS_NOT_AUTHORIZED
                )
            case uavcan.node.ExecuteCommand_1.Request.COMMAND_STORE_PERSISTENT_STATES:
                return uavcan.node.ExecuteCommand_1.Response(
                    uavcan.node.ExecuteCommand_1.Response.STATUS_NOT_AUTHORIZED
                )
            case uavcan.node.ExecuteCommand_1.Request.COMMAND_BEGIN_SOFTWARE_UPDATE:
                return uavcan.node.ExecuteCommand_1.Response(
                    uavcan.node.ExecuteCommand_1.Response.STATUS_NOT_AUTHORIZED
                )
            case _:
                return uavcan.node.ExecuteCommand_1.Response(
                    uavcan.node.ExecuteCommand_1.Response.STATUS_BAD_COMMAND
                )

    @staticmethod
    async def _serve_sync_master_info(
            request: uavcan.time.GetSynchronizationMasterInfo_0.Request, 
            metadata: pycyphal.presentation.ServiceRequestMetadata,) -> uavcan.time.GetSynchronizationMasterInfo_0.Response:
        logging.info("Execute command request %s from node %d", request, metadata.client_node_id)
        return uavcan.time.GetSynchronizationMasterInfo_0.Response(
            0.0, # error_variance
            uavcan.time.TimeSystem_0(uavcan.time.TimeSystem_0.MONOTONIC_SINCE_BOOT),
            uavcan.time.TAIInfo_0(uavcan.time.TAIInfo_0.DIFFERENCE_TAI_MINUS_UTC_UNKNOWN)
        )

    @async_loop_decorator()
    async def _clock_run_loop(self) -> None:
        await self._pub_sync_time_last.publish(uavcan.time.Synchronization_1(int(self._sync_time))) # Last timestamp

        self._sync_time = get_xp_time()

        await self._pub_sync_time.publish(uavcan.time.SynchronizedTimestamp_1(int(self._sync_time))) # Current timestamp
        await asyncio.sleep(0)

    async def run(self) -> None:
        self._node.heartbeat_publisher.mode = uavcan.node.Mode_1.OPERATIONAL
        await self._clock_run_loop()

    async def close(self) -> None:
        logging.debug("Closing CLK")
        self._node.close()


class Camera:
    DELAY = 0.5

    def __init__(self) -> None:
        self._cam_id = config.getint('main', 'cam_id')
        self._uav_id = None

        self.xp_path = config.get('xplane', 'xp_screenshot_path')
        self.destination_dir = './stored_images'
        if not os.path.exists(self.destination_dir):
           os.makedirs(self.destination_dir)
           
        logging.addLevelName(MAVLOG_DEBUG, 'MAVdebug')
        logging.addLevelName(MAVLOG_TX, 'TX')
        logging.addLevelName(MAVLOG_RX, 'RX')
        logging.addLevelName(MAVLOG_LOG, 'LOG')

        _formatter = logging.Formatter(str(os.getpid()) + ' (%(asctime)s - %(name)s - %(levelname)s) %(message)s')
        _filehandler = logging.FileHandler('mavlog.log', mode='a')
        _filehandler.setFormatter(_formatter)

        self._mavlogger = logging.getLogger(f'CAMERA{self._cam_id}')
        self._mavlogger.addHandler(_filehandler)
        self._mavlogger.setLevel(MAVLOG_TX)

        self._mavlogger.log(MAVLOG_TX, "test tx")
        self._mavlogger.log(MAVLOG_RX, "test rx")
        self._mavlogger.log(MAVLOG_LOG, "test log")
        
        self._camera_mav_conn: mavutil.mavfile = mavutil.mavlink_connection(config.get('mavlink', 'camera_uav_conn'), source_system=self._cam_id, source_component=m.MAV_COMP_ID_CAMERA, input=False, autoreconnect=True)
        import common.key as key
        self._camera_mav_conn.setup_signing(key.CAMKEY.encode('utf-8'))

        self._att = [0.0, 0.0] # r, p

    @async_loop_decorator()
    async def _camera_run_loop(self) -> None:
        try:
            msg = self._camera_mav_conn.recv_msg()
        except (ConnectionError, OSError):
            try:
                self._mavlogger.log(MAVLOG_DEBUG, "Controller connection refused")
                await asyncio.sleep(0)
            except asyncio.exceptions.CancelledError:
                stop.set()
                raise
            finally:
                return
            
        if msg is not None and msg.get_type() == 'CHANGE_OPERATOR_CONTROL':
            import common.key as key
            if msg.control_request == 0 and msg.passkey==key.CAMKEY:
                if self._uav_id is None or self._uav_id==msg.get_srcSystem():
                    # Accepted
                    if self._uav_id!=msg.get_srcSystem():
                        self._mavlogger.log(MAVLOG_RX, f"Camera accepting control request from UAV ({msg.get_srcSystem()})")
                    self._uav_id = msg.get_srcSystem()
                    self._camera_mav_conn.mav.change_operator_control_ack_send(msg.get_srcSystem(), msg.control_request, 0)
                else:
                    # Already controlled
                    self._mavlogger.log(MAVLOG_RX, f"Camera rejecting second control request from {msg.get_srcSystem()}")
                    self._camera_mav_conn.mav.change_operator_control_ack_send(msg.get_srcSystem(), msg.control_request, 3)
            elif msg.control_request == 1 and msg.passkey==key.CAMKEY:
                # Accepted (released)
                self._mavlogger.log(MAVLOG_RX, f"Releasing from UAV ({self._uav_id})")
                self._uav_id = None
                self._camera_mav_conn.mav.change_operator_control_ack_send(msg.get_srcSystem(), msg.control_request, 0)
            else:
                # Bad key
                self._mavlogger.log(MAVLOG_RX, f"Bad key in UAV control request")
                self._camera_mav_conn.mav.change_operator_control_ack_send(msg.get_srcSystem(), msg.control_request, 1)
        elif msg is not None and msg.get_srcSystem()==self._uav_id:
            if msg.get_type() == 'HEARTBEAT':
                self._mavlogger.log(MAVLOG_DEBUG, "Camera rx heartbeat from UAV")
            elif msg.target_system==self._uav_id and msg.target_component==m.MAV_COMP_ID_CAMERA and msg.get_type() == 'COMMAND_LONG':
                if msg.command == m.MAV_CMD_IMAGE_START_CAPTURE:
                    cap: asyncio.Task = asyncio.create_task(self._capture_cycle(int(msg.param3), msg.param2))
                    self._camera_mav_conn.mav.command_ack_send(m.MAV_CMD_IMAGE_START_CAPTURE, m.MAV_RESULT_ACCEPTED, 255, 0, self._cam_id, 0)
                elif msg.command == m.MAV_CMD_IMAGE_STOP_CAPTURE:
                    try:
                        cap.cancel()
                        self._camera_mav_conn.mav.command_ack_send(m.MAV_CMD_IMAGE_STOP_CAPTURE, m.MAV_RESULT_ACCEPTED, 255, 0, self._cam_id, 0)
                    except AttributeError:
                        pass
                        self._camera_mav_conn.mav.command_ack_send(m.MAV_CMD_IMAGE_STOP_CAPTURE, m.MAV_RESULT_DENIED, 255, 0, self._cam_id, 0)
                else:
                    self._camera_mav_conn.mav.command_ack_send(msg.command, m.MAV_RESULT_UNSUPPORTED, 255, 0, self._cam_id, 0)
            elif msg.target_system==self._cam_id and msg.target_component==m.MAV_COMP_ID_CAMERA and msg.get_type() == 'GIMBAL_DEVICE_SET_ATTITUDE':
                self._att = py_to_rp(*[math.degrees(the) for the in quaternion_to_euler(msg.q)[1:]])
                tx_data[b'fmuas/camera/roll'] = self._att[0]
                tx_data[b'fmuas/camera/pitch'] = self._att[1]
        await asyncio.sleep(0)

    async def _camera_run(self) -> None:
        await self._camera_run_loop()

    async def run(self) -> None:
        asyncio.create_task(self._heartbeat())
        asyncio.create_task(self._camera_run())

        await asyncio.sleep(0)

    async def _capture(self) -> None:
        previous_file_list = [f for f in os.listdir(self.xp_path) if os.path.isfile(os.path.join(self.xp_path, f))]

        logging.info("Commanding screenshot...")
        # TODO: send command

        await asyncio.sleep(Camera.DELAY)

        new_file_list = [f for f in os.listdir(self.xp_path) if os.path.isfile(os.path.join(self.xp_path, f))]
        file_diff = [x for x in new_file_list if x not in previous_file_list]
        previous_file_list = new_file_list

        if len(file_diff) != 0:
            logging.debug(f"Detected file_diff: {file_diff}")
            for f in file_diff:
                ready = False
                last_modified = os.stat(os.path.join(self.xp_path, f)).st_mtime
                while not ready:
                    await asyncio.sleep(Camera.DELAY)
                    new_last_modified = os.stat(os.path.join(self.xp_path, f)).st_mtime
                    ready = (last_modified == new_last_modified)
                    last_modified = new_last_modified
                    logging.debug('Shutil waiting...')
                logging.debug("Shutil moving")
                if not os.path.exists(self.destination_dir):
                    os.makedirs(self.destination_dir)
                file_path = os.path.join(self.xp_path, f)
                try:
                    shutil.move(file_path, self.destination_dir)
                    logging.info(f"Moving file {f} to {self.destination_dir}")
                except (shutil.Error, PermissionError):
                    logging.error(f"Error moving file {f} to {self.destination_dir}")
        
        # TODO: send command (image reset)

    async def _capture_cycle(self, iterations: int, period: float) -> None:
        if iterations != 0:
            for _ in range(iterations):
                try:
                    tstart = time.time()
                    await asyncio.gather(asyncio.create_task(self._capture()))
                    await asyncio.sleep(max(0, period - (time.time()-tstart)))
                except asyncio.exceptions.CancelledError:
                    break
        else:
            while True:
                try:
                    await asyncio.gather(asyncio.create_task(self._capture()))
                    await asyncio.sleep(period)
                except asyncio.exceptions.CancelledError:
                    break

    @async_loop_decorator(close=False)
    async def _camera_heartbeat_loop(self) -> None:
        self._camera_mav_conn.mav.heartbeat_send(
            m.MAV_TYPE_CAMERA,
            m.MAV_AUTOPILOT_INVALID,
            m.MAV_MODE_PREFLIGHT,
            0,
            m.MAV_STATE_ACTIVE
        )
        await asyncio.sleep(1)

    async def _heartbeat(self) -> None:
        await self._camera_heartbeat_loop()

    async def close(self) -> None:
        self._camera_mav_conn.close()
        logging.debug("Closing CAM")


class PythonInterface:
    def __init__(self):
        self.Name = "FMUAS X-Plane Interface"
        self.Sig = "fmuas.xppython3"
        self.Desc = "Allows connection between FMUAS software and X-Plane 12 via Cyphal and Mavlink protocols"

    def XPluginStart(self) -> tuple[str]:
        # Required by XPPython3
        # Called once by X-Plane on startup (or when plugins are re-starting as part of reload)
        # You need to return three strings
        return self.Name, self.Sig, self.Desc

    def XPluginStop(self):
        # Called once by X-Plane on quit (or when plugins are exiting as part of reload)
        # Return is ignored
        pass

    async def clock_main(self) -> None:
        self.clk = Clock()
        task = asyncio.create_task(self.clk.run())
        try:
            await task
        except asyncio.exceptions.CancelledError:
            stop.set()

        logging.warning("Clock closed")

    def clock(self) -> None:
        asyncio.run(self.clock_main())

    async def motor_main(self) -> None:
        self.mot = MotorHub()
        task = asyncio.create_task(self.mot.run())
        try:
            await task
        except asyncio.exceptions.CancelledError:
            stop.set()

        logging.warning("MotorHub closed")

    def motor(self) -> None:
        asyncio.run(self.motor_main())
        
    async def sensor_main(self) -> None:
        self.sns = SensorHub()
        task = asyncio.create_task(self.sns.run())
        try:
            await task
        except asyncio.exceptions.CancelledError:
            stop.set()

        logging.warning("SensorHub closed")

    def sensor(self) -> None:
        asyncio.run(self.sensor_main())

    async def gps_main(self) -> None:
        self.gps = GPS()
        task = asyncio.create_task(self.gps.run())
        try:
            await task
        except asyncio.exceptions.CancelledError:
            stop.set()

        logging.warning("GPS closed")

    def gps(self) -> None:
        asyncio.run(self.gps_main())

    def XPluginEnable(self) -> int:
        # Required by XPPython3
        # Called once by X-Plane, after all plugins have "Started" (including during reload sequence).
        # You need to return an integer 1, if you have successfully enabled, 0 otherwise.
        self.rx_drefs = {name: xp.findDataRef(name.decode('utf-8')) for name in rx_data.keys()}
        self.tx_drefs = {name: xp.findDataRef(name.decode('utf-8')) for name in tx_data.keys()}
        self.flightLoopID = xp.createFlightLoop(self.FLCallback)
        xp.scheduleFlightLoop(self.flightLoopID, interval=-1)

        self.clock_thread = threading.Thread(target=self.clock)
        self.clock_thread.start()

        self.sensor_thread = threading.Thread(target=self.sensor)
        self.sensor_thread.start()

        self.motor_thread = threading.Thread(target=self.motor)
        self.motor_thread.start()

        self.gps_thread = threading.Thread(target=self.clock)
        self.gps_thread.start()
        
        logging.warning("Starting FMUAS plugin")

        return 1

    def XPluginDisable(self):
        # Called once by X-Plane, when plugin is requested to be disabled. All plugins
        # are disabled prior to Stop.
        # Return is ignored
        xp.setDatad(self.tx_drefs[b'fmuas/python_running'], 0)
        xp.destroyFlightLoop(self.flightLoopID)
        stop.set()
        self.clock_thread.join()
        self.motor_thread.join()
        self.sensor_thread.join()
        self.gps_thread.join()
        pass

    def XPluginReceiveMessage(self, inFromWho, inMessage, inParam):
        # Called by X-Plane whenever a plugin message is being sent to your
        # plugin. Messages include MSG_PLANE_LOADED, MSG_ENTERED_VR, etc., as
        # described in XPLMPlugin module.
        # Messages may be custom inter-plugin messages, as defined by other plugins.
        # Return is ignored
        pass

    def FLCallback(self, lastCall: float, elapsedTime: float, counter: int, refCon) -> float:
        for name, dref in self.rx_drefs.items():
            if name in [b'sim/time/paused', b'sim/time/local_date_days']:
                rx_data[name] = xp.getDatai(dref)
            elif name==b'sim/time/zulu_time_sec':
                rx_data[name] = xp.getDataf(dref)
            else:
                rx_data[name] = xp.getDatad(dref)
        
        for name, dref in self.tx_drefs.items():
            xp.setDatad(dref, tx_data[name])

        return -1