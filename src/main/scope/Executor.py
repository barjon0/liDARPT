"""
© 2025 Jonas Barth

This file is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0).

You may share and adapt the material for non-commercial use, provided you give appropriate credit,
indicate if changes were made, and distribute your contributions under the same license.

License: https://creativecommons.org/licenses/by-nc-sa/4.0/

File: Executor.py
Description: Traverses through given plan, up to a certain time,
            Stores information on bus and request locations.
NOTE: also intended for use in a dynamic setting, however still lacks some logic required
"""
from typing import Set, Dict, List
from utils import Global, Timer
from models.Demand import Request
from utils.Timer import TimeImpl
from models.Network import Bus, Stop
from models.Plan import RouteStop, Route


class Executor:
    """
    Traverses through given plan, up to a certain time and
    stores information on bus and request locations.
    """

    def __init__(self, busses: List[Bus], requests: Set[Request]):
        self.user_locations: Dict[Request, Stop] = {x: x.pick_up_location for x in requests}  # for waiting users
        self.passengers: Dict[Bus, Set[Request]] = {x: set() for x in busses}
        self.bus_locations: Dict[Bus, Stop] = {x: x.line.depot for x in
                                               busses}  # locations of bus (or next location bus is arriving at)
        self.bus_delay: Dict[Bus, int] = {x: 0 for x in busses}  # time of bus to arriving at next stop
        self.routes = [Route(x) for x in busses]
        self.requests = requests

        self.routes.sort(key=lambda x: x.bus.id)

    def check_plan(self, done_r_stops: List[RouteStop], final_time: TimeImpl = None):
        """
        Validates the current plan, for example pick-up and drop-off locations and time windows of requests.
        Updates location of buses and requests. Throws error if invalid.
        :param done_r_stops: list of all Routestops, sorted by arrival time
        :param final_time: executes plan up to this time
        """
        waiting_bus_stops: List[RouteStop] = []
        curr_time: TimeImpl
        for r_stop in done_r_stops:
            curr_time = r_stop.arriv_time

            still_waiting = []
            for wait_stop in waiting_bus_stops:
                if wait_stop.depart_time <= curr_time:
                    for u_picked in wait_stop.pick_up:
                        if u_picked not in self.user_locations.keys():
                            print_out_route(done_r_stops)
                            raise ValueError(f"User {u_picked.id} not marked as waiting")
                        this_stop = self.user_locations.pop(u_picked)
                        if this_stop is not wait_stop.stop:
                            raise ValueError("Missmatch between expected pick-up stop and actual")
                        self.passengers[wait_stop.bus].add(u_picked)
                        if wait_stop.stop is u_picked.pick_up_location:
                            u_picked.act_start_time = wait_stop.depart_time.sub_seconds(Global.TRANSFER_SECONDS)
                else:
                    still_waiting.append(wait_stop)

            waiting_bus_stops = still_waiting
            self.bus_locations[r_stop.bus] = r_stop.stop

            for u_dropped in r_stop.drop_off:
                if u_dropped not in self.passengers[r_stop.bus]:
                    for a_stop in done_r_stops:
                        print(a_stop)
                    raise ValueError(f"User {u_dropped.id} not supposed to be in bus")
                else:
                    self.passengers[r_stop.bus].remove(u_dropped)
                if r_stop.stop is not u_dropped.drop_off_location:
                    self.user_locations[u_dropped] = r_stop.stop
                else:
                    u_dropped.act_end_time = r_stop.arriv_time

            insert_sorted(waiting_bus_stops, r_stop)

        # DYNAMIC CASE: for waiting_bus_events change depart_time and empty pick-up set if not finished
        if final_time is not None:
            for wait_event in waiting_bus_stops:
                if wait_event.depart_time <= final_time:
                    for u_picked in wait_event.pick_up:
                        this_stop = self.user_locations.pop(u_picked)
                        if this_stop is not wait_event.stop:
                            raise ValueError("Missmatch between expected pick-up stop and actual")
                        self.passengers[wait_event.bus].add(u_picked)
                        if u_picked.pick_up_location is wait_event.stop:
                            u_picked.act_start_time = wait_event.depart_time.sub_seconds(Global.TRANSFER_SECONDS)
                else:
                    wait_event.depart_time = final_time
                    wait_event.pick_up.clear()
        else:
            for wait_event in waiting_bus_stops:
                for u_picked in wait_event.pick_up:
                    this_stop = self.user_locations.pop(u_picked)
                    if this_stop is not wait_event.stop:
                        raise ValueError("Missmatch between expected pick-up stop and actual")
                    self.passengers[wait_event.bus].add(u_picked)
                    if u_picked.pick_up_location is wait_event.stop:
                        u_picked.act_start_time = wait_event.depart_time.sub_seconds(Global.TRANSFER_SECONDS)

        # check accepted users are taken care of (valid start and end times) -> max ride time
        for request in self.requests:
            if request.act_start_time is not None:
                if not (request.earl_start_time <= request.act_start_time <= request.latest_start_time):
                    raise ValueError(
                        f"The pick-up time window of request {request.id} not respected; Window: [{request.earl_start_time} : {request.latest_start_time}], actual time: {request.act_start_time}")
                if request.act_end_time is None:
                    raise ValueError(f"Request {request.id} was picked up but not delivered")
                if not (request.earl_arr_time <= request.act_end_time <= request.latest_arr_time):
                    raise ValueError(
                        f"The drop-off time window of request {request.id} not respected; Window: [{request.earl_arr_time} : {request.latest_arr_time}], actual time: {request.act_end_time}")
                time_travelled = (request.act_end_time - request.act_start_time).get_in_seconds()
                max_travel_time = (request.latest_arr_time - request.latest_start_time).get_in_seconds()
                if time_travelled > (max_travel_time + 0.1):
                    raise ValueError(
                        f"Maximum travel time of request {request.id} not respected; Time travelled: {time_travelled}, Maximum Time: {max_travel_time}")

    def execute_plan(self, curr_routes: List[Route], new_requests: Set[Request], time_next: TimeImpl):
        """
        Executes the plan, triggered by context.
        :param curr_routes: list of bus routes
        :param new_requests: newly added requests
        :param time_next: executes plan up to this time
        """
        self.user_locations |= {x: x.pick_up_location for x in new_requests if x.route_int is not None}

        curr_routes.sort(key=lambda x: x.bus.id)

        # go through plan and check travel times
        for route in curr_routes:
            for i in range(0, len(route.stop_list) - 1):
                travel_time_min = Timer.calc_time(
                    route.stop_list[i].stop.calc_distance(route.stop_list[i + 1].stop))
                if route.stop_list[i + 1].arriv_time <= route.stop_list[i].depart_time:
                    print_out_route(route.stop_list)
                needed_time = (route.stop_list[i + 1].arriv_time - route.stop_list[i].depart_time).get_in_seconds()
                if (travel_time_min - 0.1) > needed_time:
                    raise ValueError(
                        f"Travel times are not respected in solution; Minimum Time: {travel_time_min / 60}, Needed time: {needed_time / 60}")

        if time_next is None:
            for route_count in range(len(curr_routes)):
                self.routes[route_count].stop_list += curr_routes[route_count].stop_list

            all_r_stops: List[RouteStop] = []
            for route in curr_routes:
                all_r_stops += route.stop_list

            all_r_stops.sort(key=lambda x: x.arriv_time)
            self.check_plan(all_r_stops)

        else:
            done_r_stops = []
            for route_count in range(len(curr_routes)):
                time_count: TimeImpl
                if len(curr_routes[route_count].stop_list) > 0:
                    time_count = curr_routes[route_count].stop_list[0].arriv_time
                else:
                    raise ValueError("Route can not be empty")
                counter = 0
                while counter < len(curr_routes[route_count].stop_list) and time_count < time_next:
                    done_r_stops.append(curr_routes[route_count].stop_list[counter])
                    self.routes[route_count].stop_list.append(curr_routes[route_count].stop_list[counter])

                    counter += 1
                    time_count = curr_routes[route_count].stop_list[counter].arriv_time

                # could lead to inconsistencies in dynamic case: not finished stop_events are counted as fully processed, but are cut short(pick-ups not done)
                if counter < len(curr_routes[route_count].stop_list):
                    self.bus_delay[curr_routes[route_count].bus] = (time_count - time_next).get_in_seconds()

            done_r_stops.sort(key=lambda x: x.arriv_time)
            self.check_plan(done_r_stops)


def print_out_route(route: List[RouteStop]):
    for stopr in route:
        print(str(stopr) + " arrival time: " + str(stopr.arriv_time) + " depart time: " + str(stopr.depart_time))


def insert_sorted(waiting_bus_stops: List[RouteStop], r_stop: RouteStop):
    i = 0
    while i < len(waiting_bus_stops) and waiting_bus_stops[i].depart_time < r_stop.depart_time:
        i += 1
    waiting_bus_stops.insert(i, r_stop)
