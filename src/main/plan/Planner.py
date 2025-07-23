"""
© 2025 Jonas Barth

This file is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0).

You may share and adapt the material for non-commercial use, provided you give appropriate credit,
indicate if changes were made, and distribute your contributions under the same license.

License: https://creativecommons.org/licenses/by-nc-sa/4.0/

File: Planner.py
Description: Interface for any kind of solving strategy.
"""
from typing import List, Dict, Set
from models.Demand import Request
from models.Plan import Route
from utils.LineGraph import LineGraph
from models.Network import Bus, Stop


class Planner:
    """
    Interface for a solving strategy of liDARPT instances. Needs to implement make_plan.
    """

    def __init__(self, bus_list: List[Bus], network_graph: LineGraph):
        self.bus_list: List[Bus] = bus_list
        self.network_graph: LineGraph = network_graph
        self.requests: Set[Route] = set()
        self.curr_routes: List[Route] = []

    def make_plan(self, new_requests: Set[Request], curr_bus_locations: Dict[Bus, Stop],
                  user_bus_dict: Dict[Bus, Set[Request]], user_locations: Dict[Request, Stop],
                  bus_delay: Dict[Bus, float]):
        pass
