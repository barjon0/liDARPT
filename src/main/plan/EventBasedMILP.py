"""
© 2025 Jonas Barth

This file is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0).

You may share and adapt the material for non-commercial use, provided you give appropriate credit,
indicate if changes were made, and distribute your contributions under the same license.

License: https://creativecommons.org/licenses/by-nc-sa/4.0/

File: EventBasedMILP.py
Description: Build the event graph from all requests and their route options.
            Delegates model construction and solving to the CplexModel, using the generated graph.
"""
import time
from typing import List, Set, Dict, Tuple
from utils import Global, Timer
from main.plan.CplexModel import CplexSolver
from main.plan.Planner import Planner
from models.Demand import SplitRequest, Request
from utils.EventGraph import EventGraph, Event, PickUpEvent, DropOffEvent, IdleEvent
from utils.LineGraph import LineGraph
from utils.Timer import TimeImpl
from models.Network import Bus, Stop, Line


def check_on_route(split: SplitRequest, search_loc: Stop):
    """
    Checks if a given stop is on the route of a splitRequest.
    :param split: SplitRequest to check route from
    :param search_loc: a specific stop to check if on route
    :return: bool indicating if on route or not
    """
    line: Line = split.line

    idx_start = line.stops.index(split.pick_up_location)
    idx_end = line.stops.index(split.drop_off_location)
    idx_search = line.stops.index(search_loc)

    if idx_start < idx_end:
        if idx_start <= idx_search <= idx_end:
            return True
    elif idx_start >= idx_search >= idx_end:
        return True

    return False


def sweep_line_local(splits_in_dir: Set[SplitRequest], line: Line, direction: int):
    """
    Sweep-Line-Algorithm; for splitRequest find candidates of splitRequests to be in vehicle
    at pick-up/drop-off stop(based on positioning on the line),
    Checks for entire set of splitRequests on the line and direction at once.
    :param splits_in_dir: set of SplitRequests on the line and direction
    :param line: line of SplitRequests
    :param direction: direction of SplitRequests
    :return: dictionary for splitRequest to sets of candidates for pick-up and drop-off
    """
    # extract event points(make queue with insert and delete objects) -> go trough queue
    # -> update status_dict -> build output from keys
    queue: Dict[Stop, Tuple[Set[SplitRequest], Set[SplitRequest]]] = {x: (set(), set()) for x in line.stops}

    for split_req in splits_in_dir:
        queue[split_req.pick_up_location][0].add(split_req)
        queue[split_req.drop_off_location][1].add(split_req)

    event_points: List[Stop] = line.stops.copy()
    if direction == 1:
        event_points.reverse()

    status_set: Set[SplitRequest] = set()
    output_dict: Dict[SplitRequest, Tuple[Set[SplitRequest], Set[SplitRequest]]] = {x: (set(), set()) for x in
                                                                                    splits_in_dir}

    for stop in event_points:

        status_set -= queue[stop][1]
        for req_del in queue[stop][1]:
            # when deleting a request -> all remaining as candidate for drop-off
            for other_del in queue[stop][1]:
                # add so that candidates have shorter latest time
                if req_del.id != other_del.id and req_del.latest_arr_time <= other_del.latest_arr_time:
                    output_dict[req_del][1].add(other_del)
            for other in status_set:
                if other.id != req_del.id:
                    output_dict[req_del][1].add(other)

        # when adding a request -> all remainining actives are candidate for pick-up
        for req_in in queue[stop][0]:
            for other_new in queue[stop][0]:
                if req_in.id != other_new.id and req_in.latest_start_time <= other_new.latest_start_time:
                    output_dict[req_in][0].add(other_new)

            for other in status_set:
                if other.id != req_in.id:
                    output_dict[req_in][0].add(other)

        status_set |= queue[stop][0]

    return output_dict


def sweep_line_time(splits_on_line: Set[SplitRequest]):
    """
    Sweep-Line-Algorithm; for splitRequests of line find candidates of splitRequests to be in vehicle
    at pick-up/drop-off stop(based on time constraints),
    Checks for entire set of splitRequests on the line at once.
    :param splits_on_line: set of SplitRequests on the line
    :return: dictionary for splitRequest to sets of candidates for pick-up and drop-off
    """
    queue: Dict[TimeImpl, List[Set[SplitRequest]]] = {}
    # fill the queue, (yes this looks horrible, i know...)
    for req in splits_on_line:
        if req.earl_start_time in queue:
            queue[req.earl_start_time][0].add(req)
        else:
            queue[req.earl_start_time] = [{req}, set(), set(), set()]

        if req.latest_start_time in queue:
            queue[req.latest_start_time][1].add(req)
        else:
            queue[req.latest_start_time] = [set(), {req}, set(), set()]

        if req.earl_arr_time in queue:
            queue[req.earl_arr_time][2].add(req)
        else:
            queue[req.earl_arr_time] = [set(), set(), {req}, set()]

        if req.latest_arr_time in queue:
            queue[req.latest_arr_time][3].add(req)
        else:
            queue[req.latest_arr_time] = [set(), set(), set(), {req}]

    event_points = sorted(queue.keys())
    status_tuple: Tuple[Set[SplitRequest], Set[SplitRequest]] = (
        set(), set())  # tuple of sets of split_requests for both interval types
    total_status: Set[SplitRequest] = set()  # all open intervals [earliest_start, latest_finish]
    output_dict: Dict[SplitRequest, Tuple[Set[SplitRequest], Set[SplitRequest]]] = {x: (set(), set()) for x in
                                                                                    splits_on_line}

    for time_obj in event_points:
        status_tuple[1].update(queue[time_obj][2])
        status_tuple[0].update(queue[time_obj][0])
        total_status |= queue[time_obj][0]

        for drop_open in queue[time_obj][2]:
            for other in total_status:
                if other.id != drop_open.id:
                    output_dict[drop_open][1].add(other)

        for pick_open in queue[time_obj][0]:
            for other in total_status:
                if other.id != pick_open.id:
                    output_dict[pick_open][0].add(other)
                    # check also if candidate in other direction
                    if other in status_tuple[0]:
                        output_dict[other][0].add(pick_open)
                    if other in status_tuple[1]:
                        output_dict[other][1].add(pick_open)

        status_tuple[0].difference_update(queue[time_obj][1])
        status_tuple[1].difference_update(queue[time_obj][3])
        total_status -= queue[time_obj][3]

    return output_dict


class EventBasedMILP(Planner):
    """
    Implements Planner Interface to generate optimal plan based on event-graph and MILP.
    NOTE: still lacks functionality for usage in dynamic context
    """

    def __init__(self, bus_list: List[Bus], network_graph: LineGraph):
        super().__init__(bus_list, network_graph)
        self.event_graph = None

    def get_combinations(self, event_user: SplitRequest, cand_list: List[SplitRequest], curr_combi: Set[SplitRequest],
                         index: int, event_type: bool) -> Set[Event]:
        """
        Finds all combinations(therefore events) for given event_user action based on found candidates.
        Recursively builds subset up to capacity, stops if current combination is infeasible(based on timing).
        :param event_user: SplitRequest
        :param cand_list: list of candidates of SplitRequests in the vehicle for this action
        :param curr_combi: currently explored combination of candidates
        :param index: marks position of last added SplitRequest added to curr_combi
        :param event_type: indicates weather we look at pick-up or drop-off
        :return: set of events, connected to event_user action
        """
        return_set: Set[Event] = set()
        # check for next candidate to be distinct from previous ones
        id_set: Set[int] = {x.id for x in curr_combi}

        # check if candidates left
        while len(cand_list) > index:
            # if no one left stop
            if not cand_list[index].id in id_set:

                # add candidate to current_permutation, check for feasibility
                next_permut = curr_combi | {cand_list[index]}
                # if max length exceeded stop
                if (sum(x.number_of_passengers for x in
                        next_permut) + event_user.number_of_passengers) <= event_user.line.capacity:
                    earl_time, lat_time = get_event_window(event_user, next_permut, event_type)
                    if earl_time is not None and lat_time is not None:
                        event: Event
                        if event_type:
                            event = PickUpEvent(event_user, next_permut, earl_time, lat_time)
                        else:
                            event = DropOffEvent(event_user, next_permut, earl_time, lat_time)
                        return_set |= {event} | self.get_combinations(event_user, cand_list, next_permut, index + 1,
                                                                      event_type)
            index += 1
        return return_set

    def walk_route(self, req: Request, bus_user_dict: Dict[Bus, Set[Request]], next_bus_locations: Dict[Bus, Stop]):
        """
        For usage in dynamic context: finds future splitRequests of an already picked-up Requests selected route option.
        :param req: a Request that is already planned
        :param bus_user_dict: current requests seated in buses
        :param next_bus_locations: dictionary of next bus stops according to plan
        :return: current active splitRequest and following of route option
        """
        # find current position -> walk among selected route to position -> return all future splits
        bus: Bus = next(k for k, v in bus_user_dict if req in v)

        curr_location: Stop = next_bus_locations[bus]

        result = {}
        found: bool = False
        for split in req.split_requests[req.route_int]:
            if not found:
                if split.line == bus.line:
                    split.in_action = True
                    if check_on_route(split, curr_location):
                        found = True
                        result += split
                else:
                    split.in_action = True
            else:
                result += split

        return result

    def make_plan(self, new_requests: Set[Request], next_bus_locations: Dict[Bus, Stop],
                  bus_user_dict: Dict[Bus, Set[Request]], wait_user_locations: Dict[Request, Stop],
                  bus_delay: Dict[Bus, float]):
        """
        Creates a plan based on new incoming requests and previously known requests.
        Builds candidate sets for splitRequest actions, then events and graph.
        Calls CplexModel to build model and solve.
        :param new_requests: additional requests to be planned
        :param next_bus_locations: dictionary of next bus stops, according to current plan
        :param bus_user_dict: dictionary of request allocations in buses
        :param wait_user_locations: dictionary of request locations still waiting
        :param bus_delay: dictionary of time until bus reaches next stop
        """

        self.event_graph = EventGraph()
        all_active_requests: Set[Request] = set()
        all_active_requests |= new_requests | wait_user_locations.keys()

        all_follow_splits: Set[SplitRequest] = set()
        for req in all_active_requests:
            for opt in req.split_requests.keys():
                all_follow_splits |= set(req.split_requests[opt])

        curr_passengers: Set[Request] = set().union(*bus_user_dict.values())
        all_active_requests |= curr_passengers

        for req in curr_passengers:
            all_follow_splits |= self.walk_route(req, bus_user_dict, next_bus_locations)

        # build candidate sets for lines and directions
        line_dir_dict: Dict[Line, Tuple[Set[SplitRequest], Set[SplitRequest]]] = \
            {x: (set(), set()) for x in self.network_graph.all_lines}
        for split_req in all_follow_splits:
            direction = check_dir(split_req)
            line_dir_dict[split_req.line][direction].add(split_req)

        sort_lines = sorted(line_dir_dict.keys(), key=lambda l: l.id)

        for line in sort_lines:
            permutations: Set[Event] = set()
            idle_event = IdleEvent(line)
            permutations.add(idle_event)

            for direction in range(2):
                # direction 0 is normal, 1 is reverse
                # local_cand_map generate pick_up candidates and drop off candidates
                users_here = line_dir_dict[line][direction]
                local_cand_dict: Dict[SplitRequest, Tuple[Set[SplitRequest], Set[SplitRequest]]] = \
                    sweep_line_local(users_here, line, direction)

                time_cand_dict: Dict[SplitRequest, Tuple[Set[SplitRequest], Set[SplitRequest]]] = sweep_line_time(
                    line_dir_dict[line][direction])

                agg_cand_dict: Dict[SplitRequest, Tuple[Set[SplitRequest], Set[SplitRequest]]] = {}
                for split_req in local_cand_dict.keys():
                    agg_cand_dict[split_req] = (local_cand_dict[split_req][0] & time_cand_dict[split_req][0],
                                                local_cand_dict[split_req][1] & time_cand_dict[split_req][1])

                for event_user in agg_cand_dict.keys():
                    permutations |= {
                        PickUpEvent(event_user, set(), event_user.earl_start_time, event_user.latest_start_time)}

                    hold = self.get_combinations(event_user, list(agg_cand_dict[event_user][0]), set(), 0, True)
                    permutations |= hold

                    permutations |= {
                        DropOffEvent(event_user, set(), event_user.earl_arr_time, event_user.latest_arr_time)}
                    hold = self.get_combinations(event_user, list(agg_cand_dict[event_user][1]), set(), 0, False)
                    permutations |= hold

            self.event_graph.add_events(permutations)
            # check if event graph is fully connected, else throws error
            self.event_graph.check_connectivity(idle_event)

        Global.COMPUTATION_TIME_BUILDING = round(time.time() - Global.COMPUTATION_START_TIME, 4)
        print(f"Created EventGraph after {Global.COMPUTATION_TIME_BUILDING} seconds")
        print(self.event_graph.data_in_string())
        Global.EVENT_GRAPH_NODES = len(self.event_graph.edge_dict.keys())
        Global.EVENT_GRAPH_EDGES = self.event_graph.get_number_of_edges()
        Global.NUMBER_OF_SPLITS = len(self.event_graph.request_dict.keys())
        Global.COMPUTATION_START_TIME = time.time()

        # build lin. model
        cplex_model: CplexSolver = CplexSolver(self.event_graph, all_active_requests, self.bus_list)

        Global.COMPUTATION_TIME_BUILDING_CPLEX = round(time.time() - Global.COMPUTATION_START_TIME, 4)
        print(f"Build the Cplex-Model after {Global.COMPUTATION_TIME_BUILDING_CPLEX} seconds")
        Global.COMPUTATION_START_TIME = time.time()

        # solve model
        cplex_model.solve_model()
        # convert to route solution
        self.curr_routes = cplex_model.convert_to_plan()


def get_event_window(event_user: SplitRequest, other_users: Set[SplitRequest], event_type: bool) -> (
        TimeImpl, TimeImpl):
    """
    Checks if combination of event_user and candidates is possible based on time constraints.
    Then returns time window of this event.
    :param event_user: SplitRequest
    :param other_users: set of candidates for action
    :param event_type: type of action pick-up/drop-off
    :return: Time Window for the ensuing event, empty if impossible
    """
    curr_time: TimeImpl
    curr_stop: Stop
    earl_time: TimeImpl
    latest_time: TimeImpl

    all_users = other_users | {event_user}
    stops: Set[Stop] = {x.drop_off_location for x in all_users}
    stops |= {x.pick_up_location for x in all_users}
    cand_dict: Dict[Stop, Set[SplitRequest]] = {x: set() for x in stops}
    for user in all_users:
        cand_dict[user.pick_up_location].add(user)
        cand_dict[user.drop_off_location].add(user)

    key_list: List[Stop] = event_user.line.stops.copy()
    if check_dir(event_user) == 1:
        key_list.reverse()

    # check what type and identify stop, that splits pick-ups and drop-offs
    pick_up_stop_idx: int
    if event_type:
        split_stop = event_user.pick_up_location
        first_drop_off_idx = key_list.index(split_stop) + 1
    else:
        split_stop = event_user.drop_off_location
        first_drop_off_idx = key_list.index(split_stop)

    key_list_pick = key_list[:first_drop_off_idx]
    key_list_drop = key_list[first_drop_off_idx:]

    # walk through pick-up points -> check current_time (earliest possibilities)
    curr_stop: Stop = next((x for x in key_list_pick if x in cand_dict))
    curr_time = TimeImpl(0, 0)
    latest_time = TimeImpl(23, 59, 59)
    for key in key_list_pick:
        if key in cand_dict:
            pick_up_users: Set[SplitRequest] = cand_dict[key]
            duration: int = Timer.calc_time(curr_stop.calc_distance(key))
            curr_time = curr_time.add_seconds(duration)
            for user in pick_up_users:
                if curr_time < user.earl_start_time:
                    curr_time = user.earl_start_time
            for user in pick_up_users:
                if curr_time > user.latest_start_time:
                    return None, None
            curr_stop = key
            curr_time = curr_time.add_seconds(Global.TRANSFER_SECONDS)

    if event_type:
        rem_travel_time: int = 0
        earl_time = curr_time.sub_seconds(Global.TRANSFER_SECONDS)

        for user in cand_dict[event_user.pick_up_location]:
            poss_time = user.latest_start_time
            if latest_time > poss_time:
                latest_time = poss_time
    else:
        duration = Timer.calc_time(curr_stop.calc_distance(event_user.drop_off_location))
        rem_travel_time = -duration - Global.TRANSFER_SECONDS
        earl_time = curr_time.add_seconds(duration)

    # need to check for all remaining if latest_arr time is satisfied,
    # -> also check latest possible departure: sum travel times from here, check latest_arr time - travel time, choose leftmost

    for key in key_list_drop:
        if key in cand_dict:
            drop_off_users: Set[SplitRequest] = cand_dict[key]
            duration: int = Timer.calc_time(curr_stop.calc_distance(key))

            rem_travel_time += duration
            curr_time = curr_time.add_seconds(duration)
            for user in drop_off_users:
                poss_time = user.latest_arr_time.sub_seconds(rem_travel_time + Global.TRANSFER_SECONDS)
                if poss_time < latest_time:
                    latest_time = poss_time

                if curr_time > user.latest_arr_time:
                    return None, None
            curr_stop = key
            curr_time = curr_time.add_seconds(Global.TRANSFER_SECONDS)
            rem_travel_time += Global.TRANSFER_SECONDS

    if earl_time > latest_time:
        return None, None
    else:
        return earl_time, latest_time


def check_dir(split_req: SplitRequest):
    line: Line = split_req.line
    start_idx = line.stops.index(split_req.pick_up_location)
    end_idx = line.stops.index(split_req.drop_off_location)
    if start_idx < end_idx:
        return 0
    else:
        return 1
