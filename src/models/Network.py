"""
© 2025 Jonas Barth

This file is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0).

You may share and adapt the material for non-commercial use, provided you give appropriate credit,
indicate if changes were made, and distribute your contributions under the same license.

License: https://creativecommons.org/licenses/by-nc-sa/4.0/

File: Network.py
Description: Models the bus network consisting of stops(with 2d-coordinates), lines and buses.
"""
import math
from typing import List, Tuple

from utils import Global
from utils.Timer import TimeImpl


class Stop:
    """
    Models a bus stop, has an unique id and a 2d coordinate
    """

    def __init__(self, stop_id: int, coordinates: Tuple[float, float]):
        self.id: int = stop_id
        self.coordinates: Tuple[float, float] = coordinates

    def __repr__(self):
        return f"Stop(id: {self.id}, coordinateX: {self.coordinates[0]}, coordinateY: {self.coordinates[1]})"

    def calc_distance(self, other):
        assert isinstance(other, Stop)
        unit_dist = math.sqrt(
            (other.coordinates[0] - self.coordinates[0]) ** 2 + (other.coordinates[1] - self.coordinates[1]) ** 2)
        return unit_dist * Global.KM_PER_UNIT


class Line:
    """
    Models a bus line, has an unique id and list of stops with a depot.
    Also capacity of buses travelling on this line and earliest start/latest end times of these buses.
    """

    def __init__(self, line_id: int, stops: List[Stop], depot: Stop, capacity: int, start_time: TimeImpl,
                 end_time: TimeImpl):
        self.id: int = line_id
        self.stops: List[Stop] = stops
        self.depot: Stop = depot
        self.capacity: int = capacity  # all buses on a line have the same capacity
        self.start_time: TimeImpl = start_time
        self.end_time: TimeImpl = end_time


class Bus:
    """
    Models a bus, has an unique id and a single line it corresponds to.
    """

    def __init__(self, bus_id: int, line: Line):
        self.id: int = bus_id
        self.line: Line = line

    def __str__(self):
        return str(self.id)
