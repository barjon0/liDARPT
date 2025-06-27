from typing import List, Dict, Set

from utils.demand.AbstractRequest import Request
from utils.helper.LineGraph import LineGraph
from utils.network.Bus import Bus
from utils.network.Stop import Stop
from utils.plan.Route import Route


class Planner:

    def __init__(self, bus_list: List[Bus], network_graph: LineGraph):
        self.bus_list: List[Bus] = bus_list
        self.network_graph: LineGraph = network_graph
        self.requests: Set[Route] = set()
        self.curr_routes: List[Route] = []

    def make_plan(self, new_requests: Set[Request], curr_bus_locations: Dict[Bus, Stop], user_bus_dict: Dict[Bus, Set[Request]], user_locations: Dict[Request, Stop], bus_delay: Dict[Bus, float]):
        pass
