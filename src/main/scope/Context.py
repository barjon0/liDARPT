"""
© 2025 Jonas Barth

This file is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0).

You may share and adapt the material for non-commercial use, provided you give appropriate credit,
indicate if changes were made, and distribute your contributions under the same license.

License: https://creativecommons.org/licenses/by-nc-sa/4.0/

File: Context.py
Description: Handles control flow of execution,
            Can simulate different contexts(dynamic, static, etc.) based on implementation
"""
from typing import Set, Dict
from main.plan.Planner import Planner
from main.scope.Executor import Executor
from models.Demand import Request
from utils.Timer import TimeImpl
from models.Network import Bus, Stop


class Context:
    """
    Abstract class to handle control flow, holds timetable for dynamic incoming requests.
    Reference to Planner(to solve instance based on current info),
    and Executor (to validate current plan and report current situation)
    """
    def __init__(self, requests: Set[Request], executor: Executor, planner: Planner):
        self.time_table: Dict[TimeImpl, Set[Request]] = self.create_time_table(requests)
        self.executor: Executor = executor
        self.planner: Planner = planner

    def create_time_table(self, requests: Set[Request]):
        NotImplementedError("instantiated abstract context class")

    def start_context(self):
        """
        traverses time table and triggers update, no real-time time limit imposed on solve
        """
        key_list = list(self.time_table.keys())
        for t in range(len(key_list) - 1):
            self.trigger_event(key_list[t], key_list[t + 1])

        self.trigger_event(key_list[len(key_list) - 1])


    def trigger_event(self, time_now: TimeImpl, time_next=None):
        """
        Gets new incoming requests and situation in the network and starts solve,
        then executes the plan up to next interrupt.
        :param time_now: current time
        :param time_next: time of next interrupt
        """
        curr_requests: Set[Request] = self.time_table[time_now]
        curr_bus_locations: Dict[Bus, Stop] = self.executor.bus_locations.copy()
        curr_user_locations: Dict[Request, Stop] = self.executor.user_locations.copy()
        curr_bus_delay: Dict[Bus, int] = self.executor.bus_delay.copy()
        bus_user_dict: Dict[Bus, Set[Request]] = self.executor.passengers.copy()

        self.planner.make_plan(curr_requests, curr_bus_locations, bus_user_dict, curr_user_locations, curr_bus_delay)

        self.executor.execute_plan(self.planner.curr_routes, curr_requests, time_next)


class Static(Context):
    """
    Basic static implementation, with just one solve and one execution of plan.
    """
    def __init__(self, requests: Set[Request], executor: Executor, planner: Planner):
        super().__init__(requests, executor, planner)

    def create_time_table(self, requests: Set[Request]):
        return {TimeImpl(0, 0): requests}
