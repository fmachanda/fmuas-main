[![status](https://img.shields.io/badge/status-Development-orange)](https://trello.com/b/E168SpHn/fmuas)

# fmuas-main

**Table of Contents**
* [Overview](#overview)
* [Requirements](#requirements)
* [Installation](#installation)
* [Important Files](#important-files)
* [Usage with X-Plane 12](#usage-with-x-plane-12)
* [GCS Graphical User Interface](#gcs-graphical-user-interface)
* [Credits](#credits)

## Overview
This project provides the software for a humanitarian remote-sensing UAV system.  

The software is designed to be simulated using the [X-Plane 12][xplane-link] flight simulator. However, it was produced using real-world protocols, so  it can also be used with UAVCAN and MAVLINK compatible hardware (minor adjustments required).

## Requirements
* Windows 11.0+ or MacOS 13.0+
* Python 3.11.6+
    * **pip** modules listed in `requirements.txt`
* X-Plane 12.07+ (if using simulation)

> Not tested with older versions or Linux

## Installation

> Ensure you have **python**/**python3** and **git** on your system path.

Clone this repo into the desired directory. If you plan to use this project with the X-Plane flight simulator, ensure the files are cloned into the `X-Plane 12/Aircraft/` directory. Replace `<directory>` below with the correct path.

```bash
git clone https://github.com/fmachanda/fmuas-main.git <directory>
```

Navigate to the `scripts` folder, and double-click on `install.bat` (for Windows) or `install.command` (for MacOS). You should see a terminal window open.

In the event you receive an error message, please retry installation manually.

### Manual Installation

If you do not wish to run `scripts/install.command` or `scripts/install.bat`, follow the steps below.

Clone this repo into the desired directory. This project contains the [public_regulated_data_types][prdt-link] submodule, so you must use `--recurse-submodules`.

The X-Plane simulation requires that the files are placed into the `X-Plane 12/Aircraft/` directory. Replace `<directory>` below with the correct path.

```bash
git clone https://github.com/fmachanda/fmuas-main.git <directory> --recurse-submodules

cd <directory>/fmuas-main
```

Install and update required python modules with [pip](https://pip.pypa.io/en/stable/installation/).

```bash
python -m pip install -r requirements.txt --upgrade
```

## Important Files

```bash
├── fmuas-main 
    ├── ...
    ├── scripts
        ├── run.bat # Run this for Windows
        ├── run.command # Run this for MacOS
        ├── uav.bat
        ├── uav.command
        ├── gcs.bat
        └── gcs.command
    ├── uav
        ├── uav.py
        ├── xpio.py
        └── flightplan.json # Make your own flight plan
    ├── gcs
        ├── gui_v2.py # Newer version (easier to use)
        ├── gui.py # Older version (more stable)
        └── gcs.py # Can only be used in a python terminal (error prone)
    ├── common
        ├── public_regulated_data_types # Initialize this submodule!
        ├── config.ini # Controllable settings for UAV
        ├── key.py # Shared Mavlink encryption key
        └── ...
    └── fmuas-xp # Contains the X-Plane files for simulation
```

`scripts/run.bat` (Windows) or `scripts/run.command` (MacOS) is an easy to run all UAV components and a GCS window simulataneously.

`scripts/uav.bat` (Windows) or `scripts/uav.command` (MacOS) is an easy to run all UAV components simulataneously.

`scripts/gcs.bat` (Windows) or `scripts/gcs.command` (MacOS) is an easy to run a GCS window.

`uav/uav.py` runs the UAV  
`uav/xpio.py` runs the connection with X-Plane 12 and simulates UAV components 
`uav/flightplan.json` contains customizable waypoints, altitudes, and speeds data that is followed by the autopilot during flight

`gcs/gui_v2.py` runs a GCS window
`gcs/gcs.py` can be used as a [CLI](#gcs-command-line-interface) if imported in a python terminal

`fmuas-xp` contains the X-Plane aircraft files

`common/config.ini` contains changeable settings for the UAV and GCS  

`common/key.py` contains the shared custom key used by MAVLINK connections
> The `KEY = ...` line in `key.py` can be changed to any desired MAVLINK key (must be length 25). If using separate files for GCS and UAV, ensure that this key is the same for both.  

**Important:** `common/public_regulated_data_types/` is a git [submodule][prdt-link] that must be initialized for scripts to work

## Usage with X-Plane 12

To use with X-Plane 12:

1. Ensure that the `fmuas-main` folder is in `/X-Plane 12/Aircraft`

2. Launch X-Plane 12 ([free demo][xplane-link] will work)

3. Start a new flight with the FMUAS aircraft

    > The flight will remain paused until `xpio.py` starts running

4. Either double-click on `scripts/run.bat` (Windows) or `scripts/run.command` (MacOS) or run the following scripts manually:
    * `gcs/gui_v2.py`
    * `uav/uav.py`
    * `uav/xpio.py`

5. Use the [GCS Interface](#gcs-graphical-user-interface) to boot and control the UAV.  

## GCS Graphical User Interface

Documentation coming soon!

---
### Credits

`common/public_regulated_data_types/` cloned from [OpenCyphal/public_regulated_data_types][prdt-link]

`common/find_xp.py` copied from the [XPPython3 Docs](https://xppython3.readthedocs.io/en/latest/_static/find_xp.py)  

`quaternion_to_euler()` and `euler_to_quaternion()` functions in `common/angles.py` copied from [automaticaddison](https://automaticaddison.com)

`xlua.xpl` and `init.lua` in `fmuas-xp/plugins/` copied from X-Plane

***All  other code is original.***

##

*Previous commit history (commits before 10/12/2023) can be found at [fmuas-main-history](https://github.com/fmachanda/fmuas-main-history)*

*Previous X-Plane file repo (before 11/18/2023) can be found at [fmuas-xp][fmuas-xp-link]*

*Updated 11/18/2023*


[prdt-link]: https://github.com/OpenCyphal/public_regulated_data_types
[xplane-link]: https://www.x-plane.com/desktop/try-it/
[fmuas-xp-link]: https://github.com/fmachanda/fmuas-xp