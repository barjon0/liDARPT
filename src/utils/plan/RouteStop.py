from typing import Set

from utils.demand.AbstractRequest import Request
from utils.helper.Timer import TimeImpl
from utils.network.Bus import Bus
from utils.network.Stop import Stop


class RouteStop:
    def __init__(self, stop: Stop, arriv_time: TimeImpl, depart_time: TimeImpl, bus: Bus):
        self.stop: Stop = stop
        self.arriv_time: TimeImpl = arriv_time
        self.depart_time: TimeImpl = depart_time
        self.pick_up: Set[Request] = set()
        self.drop_off: Set[Request] = set()
        self.bus: Bus = bus

    def to_output(self):
        return [self.stop.id, str(self.arriv_time), str(self.depart_time), [str(obj) for obj in self.pick_up], [str(obj) for obj in self.drop_off]]

    def __repr__(self):
        return f"RouteStop(Bus: {self.bus.id}, Location: {self.stop.id}, PickUp: {[str(obj) for obj in self.pick_up]}, DropOff: {[str(obj) for obj in self.drop_off]})"
