#!/usr/bin/env python

import os
import sys
from script_utils import SCRIPT_HOME, VERSION
sys.path.insert(1, os.path.join(os.path.dirname(__file__), f"{SCRIPT_HOME}/ext"))

import dbus
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib
from pathlib import Path
import logging
from vedbus import VeDbusService
from settableservice import SettableService
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dbus-pi")

DEVICE_INSTANCE_ID = 2048
PRODUCT_ID = 0
FIRMWARE_VERSION = 0
HARDWARE_VERSION = 0
CONNECTED = 1


MEMORY_TEXT = lambda path,value: f"{value}kB"

def UPTIME_TEXT(path, value):
    if value < 3600:
        return f"{value}s"
    elif value < 86400:
        return f"{value/3600.0:.1f} hours"
    else:
        return f"{value/86400.0:.1f} days"


class SystemBus(dbus.bus.BusConnection):
    def __new__(cls):
        return dbus.bus.BusConnection.__new__(cls, dbus.bus.BusConnection.TYPE_SYSTEM)


class SessionBus(dbus.bus.BusConnection):
    def __new__(cls):
        return dbus.bus.BusConnection.__new__(cls, dbus.bus.BusConnection.TYPE_SESSION)


def dbusConnection():
    return SessionBus() if 'DBUS_SESSION_BUS_ADDRESS' in os.environ else SystemBus()


class PiService(SettableService):
    def __init__(self, conn):
        super().__init__()
        with open("/proc/cpuinfo") as f:
            cpuinfo = f.read().rstrip()
            sections = cpuinfo.split('\n\n')
            last_section_dict= {}
            for line in sections[-1].split('\n'):
                cols = re.split('\\W*:\\W+', line)
                last_section_dict[cols[0]] = cols[1]
            serial = last_section_dict["Serial"]
        with open("/sys/firmware/devicetree/base/model", "r") as f:
            product_name = f.read().rstrip('\x00')
        self.service = VeDbusService('com.victronenergy.temperature.pi', conn, register=False)
        self.add_settable_path("/CustomName", "")
        self._init_settings(conn)
        di = self.register_device_instance("temperature", f"cpu_{serial}", DEVICE_INSTANCE_ID)
        self.service.add_mandatory_paths(__file__, VERSION, 'dbus', di,
                                         PRODUCT_ID, product_name, FIRMWARE_VERSION, HARDWARE_VERSION, CONNECTED)
        self.service.add_path("/Temperature", None)
        self.service.add_path("/TemperatureType", 2)
        self.service.add_path("/History/MinimumTemperature", None)
        self.service.add_path("/History/MaximumTemperature", None)
        self.service.add_path("/System/MemoryFree", None, gettextcallback=MEMORY_TEXT)
        self.service.add_path("/System/Uptime", None, gettextcallback=UPTIME_TEXT)
        self.service.register()

    def publish(self):
        with open("/sys/devices/virtual/thermal/thermal_zone0/temp", "r") as f:
            temp = float(f.read().rstrip())/1000.0
        self.service["/Temperature"] = temp
        with open("/proc/meminfo", "r") as f:
            meminfo = f.read().rstrip()
            meminfo_dict = {}
            for line in meminfo.split('\n'):
                cols = re.split(':\\W+', line)
                meminfo_dict[cols[0]] = int(cols[1].split(' ')[0])
        self.service["/System/MemoryFree"] = meminfo_dict["MemAvailable"]
        with open("/proc/uptime", "r") as f:
            uptime_secs = float(f.read().rstrip().split(' ')[0])
        self.service["/System/Uptime"] = uptime_secs
        return True


def main():
    DBusGMainLoop(set_as_default=True)
    pi = PiService(dbusConnection())
    GLib.timeout_add_seconds(1, pi.publish)
    mainloop = GLib.MainLoop()
    mainloop.run()


if __name__ == "__main__":
    main()
