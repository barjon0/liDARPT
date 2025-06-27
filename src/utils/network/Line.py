from typing import List

from utils.helper.Timer import TimeImpl
from utils.network.Stop import Stop


class Line:
    def __init__(self, line_id: int, stops: List[Stop], depot: Stop, capacity: int, start_time: TimeImpl, end_time: TimeImpl):
        self.id: int = line_id
        self.stops: List[Stop] = stops
        self.depot: Stop = depot
        self.capacity: int = capacity    # all buses on a line have the same capacity
        self.start_time: TimeImpl = start_time
        self.end_time: TimeImpl = end_time
