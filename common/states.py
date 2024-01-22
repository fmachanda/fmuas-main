import os

os.environ['MAVLINK20'] = '1'
from pymavlink import mavutil
m = mavutil.mavlink


class NodeCommands:
    """Stores IDs of UAVCAN Node Commands."""
    # IDs shall not exceed 32767, per Cyphal specifications.
    BOOT = 30000


class GlobalStates:
    """Manages custom modes for a UAV."""
    CUSTOM_MODE_UNINIT = 0
    CUSTOM_MODE_BOOT = 1
    CUSTOM_MODE_GROUND = 2
    CUSTOM_MODE_TAKEOFF = 3
    CUSTOM_MODE_FLIGHT = 4
    CUSTOM_MODE_LANDING = 5
    CUSTOM_MODE_EMERGENCY = 9

    CUSTOM_SUBMODE_UNINIT = 0
    CUSTOM_SUBMODE_BOOT = 10
    CUSTOM_SUBMODE_SHUTDOWN = 11
    CUSTOM_SUBMODE_GROUND_DISARMED = 20
    CUSTOM_SUBMODE_GROUND_ARMED = 21
    CUSTOM_SUBMODE_TAKEOFF_ASCENT = 30
    CUSTOM_SUBMODE_TAKEOFF_DEPART = 31
    CUSTOM_SUBMODE_TAKEOFF_TRANSIT = 32
    CUSTOM_SUBMODE_FLIGHT_NORMAL = 40
    CUSTOM_SUBMODE_FLIGHT_MANUAL = 41
    CUSTOM_SUBMODE_FLIGHT_TERRAIN_AVOIDANCE = 42
    CUSTOM_SUBMODE_LANDING_TRANSIT = 50
    CUSTOM_SUBMODE_LANDING_HOVER = 51
    CUSTOM_SUBMODE_LANDING_DESCENT = 52
    CUSTOM_SUBMODE_EMERGENCY_MULTI_MOTORS = 90
    CUSTOM_SUBMODE_EMERGENCY_SINGLE_MOTOR = 91
    CUSTOM_SUBMODE_EMERGENCY_GPS_FAIL = 92
    CUSTOM_SUBMODE_EMERGENCY_COMM_FAIL = 93
    CUSTOM_SUBMODE_EMERGENCY_UNKNOWN = 99

    CUSTOM_MODE_NAMES = {
        CUSTOM_MODE_UNINIT: 'UNINIT',
        CUSTOM_MODE_BOOT: 'BOOT',
        CUSTOM_MODE_GROUND: 'GROUND',
        CUSTOM_MODE_TAKEOFF: 'TAKEOFF',
        CUSTOM_MODE_FLIGHT: 'FLIGHT',
        CUSTOM_MODE_LANDING: 'LANDING',

        CUSTOM_MODE_EMERGENCY: 'EMERGENCY'
    }

    CUSTOM_SUBMODE_NAMES = {
        CUSTOM_SUBMODE_UNINIT: 'UNINIT',
        CUSTOM_SUBMODE_BOOT: 'BOOT',
        CUSTOM_SUBMODE_SHUTDOWN: 'SHUTDOWN',
        CUSTOM_SUBMODE_GROUND_DISARMED: 'GROUND_DISARMED',
        CUSTOM_SUBMODE_GROUND_ARMED: 'GROUND_ARMED',
        CUSTOM_SUBMODE_TAKEOFF_ASCENT: 'TAKEOFF_ASCENT',
        CUSTOM_SUBMODE_TAKEOFF_DEPART: 'TAKEOFF_DEPART',
        CUSTOM_SUBMODE_TAKEOFF_TRANSIT: 'TAKEOFF_TRANSIT',
        CUSTOM_SUBMODE_FLIGHT_NORMAL: 'FLIGHT_NORMAL',
        CUSTOM_SUBMODE_FLIGHT_MANUAL: 'FLIGHT_MANUAL',
        CUSTOM_SUBMODE_FLIGHT_TERRAIN_AVOIDANCE: 'FLIGHT_TERRAIN_AVOIDANCE',
        CUSTOM_SUBMODE_LANDING_TRANSIT: 'LANDING_TRANSIT',
        CUSTOM_SUBMODE_LANDING_HOVER: 'LANDING_HOVER',
        CUSTOM_SUBMODE_LANDING_DESCENT: 'LANDING_DESCENT',

        CUSTOM_SUBMODE_EMERGENCY_MULTI_MOTORS: 'EMERGENCY_MULTI_MOTORS',
        CUSTOM_SUBMODE_EMERGENCY_SINGLE_MOTOR: 'EMERGENCY_SINGLE_MOTOR',
        CUSTOM_SUBMODE_EMERGENCY_GPS_FAIL: 'EMERGENCY_GPS_FAIL',
        CUSTOM_SUBMODE_EMERGENCY_COMM_FAIL: 'EMERGENCY_COMM_FAIL',
        CUSTOM_SUBMODE_EMERGENCY_UNKNOWN: 'EMERGENCY_UNKNOWN'
    }

    MAV_MODES = [
        m.MAV_MODE_PREFLIGHT,
        m.MAV_MODE_MANUAL_ARMED,
        # m.MAV_MODE_MANUAL_DISARMED,
        m.MAV_MODE_GUIDED_ARMED,
        # m.MAV_MODE_GUIDED_DISARMED,
        m.MAV_MODE_AUTO_ARMED,
        m.MAV_MODE_AUTO_DISARMED,
    ]

    MAV_STATES_NOMINAL = [
        m.MAV_STATE_UNINIT,
        m.MAV_STATE_BOOT,
        m.MAV_STATE_CALIBRATING,
        m.MAV_STATE_STANDBY,
        m.MAV_STATE_ACTIVE,
    ]

    MAV_STATES_ABNORMAL = [
        m.MAV_STATE_CRITICAL,
        m.MAV_STATE_EMERGENCY,
        m.MAV_STATE_POWEROFF,
        # m.MAV_STATE_FLIGHT_TERMINATION,
    ]

    CUSTOM_MODES = [
        CUSTOM_MODE_UNINIT,
        CUSTOM_MODE_BOOT,
        CUSTOM_MODE_GROUND,
        CUSTOM_MODE_TAKEOFF,
        CUSTOM_MODE_FLIGHT,
        CUSTOM_MODE_LANDING,

        CUSTOM_MODE_EMERGENCY
    ]

    CUSTOM_SUBMODES = [
        CUSTOM_SUBMODE_UNINIT,
        CUSTOM_SUBMODE_BOOT,
        CUSTOM_SUBMODE_SHUTDOWN,
        CUSTOM_SUBMODE_GROUND_DISARMED,
        CUSTOM_SUBMODE_GROUND_ARMED,
        CUSTOM_SUBMODE_TAKEOFF_ASCENT,
        CUSTOM_SUBMODE_TAKEOFF_DEPART,
        CUSTOM_SUBMODE_TAKEOFF_TRANSIT,
        CUSTOM_SUBMODE_FLIGHT_NORMAL,
        CUSTOM_SUBMODE_FLIGHT_MANUAL,
        CUSTOM_SUBMODE_FLIGHT_TERRAIN_AVOIDANCE,
        CUSTOM_SUBMODE_LANDING_TRANSIT,
        CUSTOM_SUBMODE_LANDING_HOVER,
        CUSTOM_SUBMODE_LANDING_DESCENT,

        CUSTOM_SUBMODE_EMERGENCY_MULTI_MOTORS,
        CUSTOM_SUBMODE_EMERGENCY_SINGLE_MOTOR,
        CUSTOM_SUBMODE_EMERGENCY_GPS_FAIL,
        CUSTOM_SUBMODE_EMERGENCY_COMM_FAIL,
        CUSTOM_SUBMODE_EMERGENCY_UNKNOWN
    ]

    # Index 0 is default for that submode
    ALLOWED_CUSTOM_MODES = {
        CUSTOM_SUBMODE_UNINIT:[CUSTOM_MODE_UNINIT],
        CUSTOM_SUBMODE_BOOT:[CUSTOM_MODE_BOOT],
        CUSTOM_SUBMODE_SHUTDOWN:[CUSTOM_MODE_BOOT],
        CUSTOM_SUBMODE_GROUND_DISARMED:[CUSTOM_MODE_GROUND],
        CUSTOM_SUBMODE_GROUND_ARMED:[CUSTOM_MODE_GROUND],
        CUSTOM_SUBMODE_TAKEOFF_ASCENT:[CUSTOM_MODE_TAKEOFF],
        CUSTOM_SUBMODE_TAKEOFF_DEPART:[CUSTOM_MODE_TAKEOFF],
        CUSTOM_SUBMODE_TAKEOFF_TRANSIT:[CUSTOM_MODE_TAKEOFF],
        CUSTOM_SUBMODE_FLIGHT_NORMAL:[CUSTOM_MODE_FLIGHT],
        CUSTOM_SUBMODE_FLIGHT_MANUAL:[CUSTOM_MODE_FLIGHT],
        CUSTOM_SUBMODE_FLIGHT_TERRAIN_AVOIDANCE:[CUSTOM_MODE_FLIGHT],
        CUSTOM_SUBMODE_LANDING_TRANSIT:[CUSTOM_MODE_LANDING],
        CUSTOM_SUBMODE_LANDING_HOVER:[CUSTOM_MODE_LANDING],
        CUSTOM_SUBMODE_LANDING_DESCENT:[CUSTOM_MODE_LANDING],

        CUSTOM_SUBMODE_EMERGENCY_MULTI_MOTORS: [CUSTOM_MODE_EMERGENCY],
        CUSTOM_SUBMODE_EMERGENCY_SINGLE_MOTOR: [CUSTOM_MODE_EMERGENCY],
        CUSTOM_SUBMODE_EMERGENCY_GPS_FAIL: [CUSTOM_MODE_EMERGENCY],
        CUSTOM_SUBMODE_EMERGENCY_COMM_FAIL: [CUSTOM_MODE_EMERGENCY],
        CUSTOM_SUBMODE_EMERGENCY_UNKNOWN: [CUSTOM_MODE_EMERGENCY]
    }

    ALLOWED_MODES = {
        CUSTOM_SUBMODE_UNINIT:[m.MAV_MODE_PREFLIGHT],
        CUSTOM_SUBMODE_BOOT:[m.MAV_MODE_PREFLIGHT],
        CUSTOM_SUBMODE_SHUTDOWN:[m.MAV_MODE_PREFLIGHT],
        CUSTOM_SUBMODE_GROUND_DISARMED:[m.MAV_MODE_PREFLIGHT, m.MAV_MODE_AUTO_DISARMED],
        CUSTOM_SUBMODE_GROUND_ARMED:[m.MAV_MODE_GUIDED_ARMED, m.MAV_MODE_AUTO_ARMED],
        CUSTOM_SUBMODE_TAKEOFF_ASCENT:[m.MAV_MODE_GUIDED_ARMED, m.MAV_MODE_AUTO_ARMED],
        CUSTOM_SUBMODE_TAKEOFF_DEPART:[m.MAV_MODE_GUIDED_ARMED, m.MAV_MODE_AUTO_ARMED],
        CUSTOM_SUBMODE_TAKEOFF_TRANSIT:[m.MAV_MODE_GUIDED_ARMED, m.MAV_MODE_AUTO_ARMED],
        CUSTOM_SUBMODE_FLIGHT_NORMAL:[m.MAV_MODE_GUIDED_ARMED, m.MAV_MODE_AUTO_ARMED],
        CUSTOM_SUBMODE_FLIGHT_MANUAL:[m.MAV_MODE_MANUAL_ARMED],
        CUSTOM_SUBMODE_FLIGHT_TERRAIN_AVOIDANCE:[m.MAV_MODE_GUIDED_ARMED, m.MAV_MODE_AUTO_ARMED],
        CUSTOM_SUBMODE_LANDING_TRANSIT:[m.MAV_MODE_GUIDED_ARMED, m.MAV_MODE_AUTO_ARMED],
        CUSTOM_SUBMODE_LANDING_HOVER:[m.MAV_MODE_GUIDED_ARMED, m.MAV_MODE_AUTO_ARMED],
        CUSTOM_SUBMODE_LANDING_DESCENT:[m.MAV_MODE_GUIDED_ARMED, m.MAV_MODE_AUTO_ARMED],

        CUSTOM_SUBMODE_EMERGENCY_MULTI_MOTORS: [m.MAV_MODE_GUIDED_ARMED, m.MAV_MODE_AUTO_ARMED],
        CUSTOM_SUBMODE_EMERGENCY_SINGLE_MOTOR: [m.MAV_MODE_GUIDED_ARMED, m.MAV_MODE_AUTO_ARMED],
        CUSTOM_SUBMODE_EMERGENCY_GPS_FAIL: [m.MAV_MODE_GUIDED_ARMED, m.MAV_MODE_AUTO_ARMED],
        CUSTOM_SUBMODE_EMERGENCY_COMM_FAIL: [m.MAV_MODE_GUIDED_ARMED, m.MAV_MODE_AUTO_ARMED],
        CUSTOM_SUBMODE_EMERGENCY_UNKNOWN: [m.MAV_MODE_GUIDED_ARMED, m.MAV_MODE_AUTO_ARMED]
    }

    ALLOWED_STATES = {
        CUSTOM_SUBMODE_UNINIT:[m.MAV_STATE_UNINIT, m.MAV_STATE_POWEROFF, m.MAV_STATE_CRITICAL],
        CUSTOM_SUBMODE_BOOT:[m.MAV_STATE_BOOT, m.MAV_STATE_CALIBRATING, m.MAV_STATE_STANDBY, m.MAV_STATE_CRITICAL],
        CUSTOM_SUBMODE_SHUTDOWN:[m.MAV_STATE_POWEROFF, m.MAV_STATE_BOOT, m.MAV_STATE_CRITICAL],
        CUSTOM_SUBMODE_GROUND_DISARMED:[m.MAV_STATE_STANDBY],
        CUSTOM_SUBMODE_GROUND_ARMED:[m.MAV_STATE_ACTIVE],
        CUSTOM_SUBMODE_TAKEOFF_ASCENT:[m.MAV_STATE_ACTIVE],
        CUSTOM_SUBMODE_TAKEOFF_DEPART:[m.MAV_STATE_ACTIVE],
        CUSTOM_SUBMODE_TAKEOFF_TRANSIT:[m.MAV_STATE_ACTIVE],
        CUSTOM_SUBMODE_FLIGHT_NORMAL:[m.MAV_STATE_ACTIVE],
        CUSTOM_SUBMODE_FLIGHT_TERRAIN_AVOIDANCE:[m.MAV_STATE_ACTIVE],
        CUSTOM_SUBMODE_LANDING_TRANSIT:[m.MAV_STATE_ACTIVE],
        CUSTOM_SUBMODE_LANDING_HOVER:[m.MAV_STATE_ACTIVE],
        CUSTOM_SUBMODE_LANDING_DESCENT:[m.MAV_STATE_ACTIVE],

        CUSTOM_SUBMODE_EMERGENCY_MULTI_MOTORS: [m.MAV_STATE_CRITICAL, m.MAV_STATE_EMERGENCY],
        CUSTOM_SUBMODE_EMERGENCY_SINGLE_MOTOR: [m.MAV_STATE_CRITICAL, m.MAV_STATE_EMERGENCY],
        CUSTOM_SUBMODE_EMERGENCY_GPS_FAIL: [m.MAV_STATE_CRITICAL, m.MAV_STATE_EMERGENCY],
        CUSTOM_SUBMODE_EMERGENCY_COMM_FAIL: [m.MAV_STATE_CRITICAL, m.MAV_STATE_EMERGENCY],
        CUSTOM_SUBMODE_EMERGENCY_UNKNOWN: [m.MAV_STATE_CRITICAL, m.MAV_STATE_EMERGENCY]
    }

    # Index 0 is default step up, index 1 is default step down (if applicable)
    ALLOWED_SUBMODE_CHANGES = {
        CUSTOM_SUBMODE_UNINIT:[CUSTOM_SUBMODE_BOOT],
        CUSTOM_SUBMODE_BOOT:[CUSTOM_SUBMODE_GROUND_DISARMED, CUSTOM_SUBMODE_SHUTDOWN],
        CUSTOM_SUBMODE_SHUTDOWN:[CUSTOM_SUBMODE_UNINIT, CUSTOM_SUBMODE_BOOT],
        CUSTOM_SUBMODE_GROUND_DISARMED:[CUSTOM_SUBMODE_GROUND_ARMED, CUSTOM_SUBMODE_SHUTDOWN],
        CUSTOM_SUBMODE_GROUND_ARMED:[CUSTOM_SUBMODE_TAKEOFF_ASCENT, CUSTOM_SUBMODE_GROUND_DISARMED],
        CUSTOM_SUBMODE_TAKEOFF_ASCENT:[CUSTOM_SUBMODE_TAKEOFF_DEPART, CUSTOM_SUBMODE_LANDING_DESCENT],
        CUSTOM_SUBMODE_TAKEOFF_DEPART:[CUSTOM_SUBMODE_TAKEOFF_TRANSIT, CUSTOM_SUBMODE_LANDING_HOVER],
        CUSTOM_SUBMODE_TAKEOFF_TRANSIT:[CUSTOM_SUBMODE_FLIGHT_NORMAL, CUSTOM_SUBMODE_LANDING_TRANSIT],
        CUSTOM_SUBMODE_FLIGHT_NORMAL:[CUSTOM_SUBMODE_LANDING_TRANSIT, CUSTOM_SUBMODE_FLIGHT_TERRAIN_AVOIDANCE, CUSTOM_SUBMODE_FLIGHT_MANUAL],
        CUSTOM_SUBMODE_FLIGHT_MANUAL:[CUSTOM_SUBMODE_FLIGHT_NORMAL],
        CUSTOM_SUBMODE_FLIGHT_TERRAIN_AVOIDANCE:[CUSTOM_SUBMODE_FLIGHT_NORMAL, CUSTOM_SUBMODE_FLIGHT_MANUAL],
        CUSTOM_SUBMODE_LANDING_TRANSIT:[CUSTOM_SUBMODE_LANDING_HOVER, CUSTOM_SUBMODE_TAKEOFF_TRANSIT],
        CUSTOM_SUBMODE_LANDING_HOVER:[CUSTOM_SUBMODE_LANDING_DESCENT, CUSTOM_SUBMODE_TAKEOFF_DEPART],
        CUSTOM_SUBMODE_LANDING_DESCENT:[CUSTOM_SUBMODE_GROUND_DISARMED, CUSTOM_SUBMODE_TAKEOFF_ASCENT],
    }
