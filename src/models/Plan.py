"""
© 2025 Jonas Barth

This file is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0).

You may share and adapt the material for non-commercial use, provided you give appropriate credit,
indicate if changes were made, and distribute your contributions under the same license.

License: https://creativecommons.org/licenses/by-nc-sa/4.0/

File: Plan.py
Description: Models a plan for a specific bus to store the solution.
"""
from typing import Set, List

from models.Demand import Request
from utils.Timer import TimeImpl
from models.Network import Bus, Stop


class RouteStop:
    """
    Models a bus stopping on its tour at a specific location and time to pick-up and drop-off requests.
    """
    def __init__(self, stop: Stop, arriv_time: TimeImpl, depart_time: TimeImpl, bus: Bus):
        self.stop: Stop = stop
        self.arriv_time: TimeImpl = arriv_time
        self.depart_time: TimeImpl = depart_time
        self.pick_up: Set[Request] = set()
        self.drop_off: Set[Request] = set()
        self.bus: Bus = bus

    def to_output(self):
        return [self.stop.id, str(self.arriv_time), str(self.depart_time), [str(obj) for obj in self.pick_up],
                [str(obj) for obj in self.drop_off]]

    def __repr__(self):
        return f"RouteStop(Bus: {self.bus.id}, Location: {self.stop.id}, PickUp: {[str(obj) for obj in self.pick_up]}, DropOff: {[str(obj) for obj in self.drop_off]})"


class Route:
    """
    Models a bus tour consisting of a list of RouteStops
    """
    def __init__(self, bus: Bus):
        self.bus: Bus = bus
        self.stop_list: List[RouteStop] = []
