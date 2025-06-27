from typing import Set, Dict

from main.plan.Planner import Planner
from main.scope.Executor import Executor
from utils.demand.AbstractRequest import Request
from utils.helper.Timer import TimeImpl
from utils.network.Bus import Bus
from utils.network.Stop import Stop


class Context:
    def __init__(self, requests: Set[Request], executor: Executor, planner: Planner):
        self.time_table: Dict[TimeImpl, Set[Request]] = self.create_time_table(requests)
        self.executor: Executor = executor
        self.planner: Planner = planner

    def create_time_table(self, requests: Set[Request]):
        NotImplementedError("instantiated abstract context class")

    def start_context(self):
        key_list = list(self.time_table.keys())
        for t in range(len(key_list) - 1):
            self.trigger_event(key_list[t], key_list[t + 1])

        self.trigger_event(key_list[len(key_list) - 1])

    # when trigger: receives curr. stand. from executor
    # gives curr. Standing + new requests to planner
    # waits some time for planning
    # give new plan to executor -> execute()
    def trigger_event(self, time_now: TimeImpl, time_next=None):
        curr_requests: Set[Request] = self.time_table[time_now]
        curr_bus_locations: Dict[Bus, Stop] = self.executor.bus_locations.copy()
        curr_user_locations: Dict[Request, Stop] = self.executor.user_locations.copy()
        curr_bus_delay: Dict[Bus, int] = self.executor.bus_delay.copy()
        bus_user_dict: Dict[Bus, Set[Request]] = self.executor.passengers.copy()

        self.planner.make_plan(curr_requests, curr_bus_locations, bus_user_dict, curr_user_locations, curr_bus_delay)

        self.executor.execute_plan(self.planner.curr_routes, curr_requests, time_next)


class Static(Context):
    def __init__(self, requests: Set[Request], executor: Executor, planner: Planner):
        super().__init__(requests, executor, planner)

    def create_time_table(self, requests: Set[Request]):
        return {TimeImpl(0, 0): requests}
