import time
from typing import List, Set, Dict, Tuple

from utils import Global
from main.plan.CplexModel import CplexSolver
from main.plan.Planner import Planner
from utils.demand.AbstractRequest import SplitRequest, Request
from utils.helper import Helper
from utils.helper.EventGraph import EventGraph, Event, PickUpEvent, DropOffEvent, IdleEvent
from utils.helper.LineGraph import LineGraph
from utils.helper.Timer import TimeImpl
from utils.network.Bus import Bus
from utils.network.Line import Line
from utils.network.Stop import Stop


def check_on_route(split: SplitRequest, search_loc: Stop):
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


def sweep_line_time(splits_in_dir: Set[SplitRequest]):
    queue: Dict[TimeImpl, List[Set[SplitRequest]]] = {}
    # fill the queue, (yes this looks horrible, i know...)
    for req in splits_in_dir:
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
                                                                                    splits_in_dir}

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
    def __init__(self, bus_list: List[Bus], network_graph: LineGraph):
        super().__init__(bus_list, network_graph)
        self.event_graph = None

    # checks all permutations recursively, only one request per id, always check if feasible, if not stop
    def get_permutations(self, event_user: SplitRequest, cand_list: List[SplitRequest], curr_permut: Set[SplitRequest],
                         index: int, event_type: bool) -> Set[Event]:

        return_set: Set[Event] = set()
        # check for next candidate to be distinct from previous ones
        id_set: Set[int] = {x.id for x in curr_permut}

        # check if candidates left
        while len(cand_list) > index:
            # if no one left stop
            if not cand_list[index].id in id_set:

                # add candidate to current_permutation, check for feasibility
                next_permut = curr_permut | {cand_list[index]}
                # if max length exceeded stop
                if (sum(x.number_of_passengers for x in
                        next_permut) + event_user.number_of_passengers) <= event_user.line.capacity:
                    earl_time, lat_time = Helper.get_event_window(event_user, next_permut, event_type)
                    if earl_time is not None and lat_time is not None:
                        event: Event
                        if event_type:
                            event = PickUpEvent(event_user, next_permut, earl_time, lat_time)
                        else:
                            event = DropOffEvent(event_user, next_permut, earl_time, lat_time)
                        return_set |= {event} | self.get_permutations(event_user, cand_list, next_permut, index + 1,
                                                                      event_type)
            index += 1
        return return_set

    def walk_route(self, req: Request, bus_user_dict: Dict[Bus, Set[Request]], next_bus_locations: Dict[Bus, Stop]):
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

    # for dynamic implementation:
    # find all active Requests(splitRequests) -> curr_waiting + new + passengers    and all poss. splitRequests
    def make_plan(self, new_requests: Set[Request], next_bus_locations: Dict[Bus, Stop],
                  bus_user_dict: Dict[Bus, Set[Request]], wait_user_locations: Dict[Request, Stop],
                  bus_delay: Dict[Bus, float]):

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
            direction = Helper.check_dir(split_req)
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
                # print(f"Users for this one is: {users_here}")
                local_cand_dict: Dict[SplitRequest, Tuple[Set[SplitRequest], Set[SplitRequest]]] = \
                    sweep_line_local(users_here, line, direction)

                # number_of_candidate_pairs_local = sum(len(local_cand_dict[x][0]) + len(local_cand_dict[x][1]) for x in local_cand_dict.keys())
                # print(f"number of local candidate pairs for line {line.id} and direction {direction}: {number_of_candidate_pairs_local}")

                time_cand_dict: Dict[SplitRequest, Tuple[Set[SplitRequest], Set[SplitRequest]]] = sweep_line_time(
                    line_dir_dict[line][direction])

                # number_of_candidate_pairs_time = sum(len(time_cand_dict[x][0]) + len(time_cand_dict[x][1]) for x in time_cand_dict.keys())
                # print(f"number of time candidate pairs for line {line.id} and direction {direction}: {number_of_candidate_pairs_time}")

                agg_cand_dict: Dict[SplitRequest, Tuple[Set[SplitRequest], Set[SplitRequest]]] = {}
                for split_req in local_cand_dict.keys():
                    agg_cand_dict[split_req] = (local_cand_dict[split_req][0] & time_cand_dict[split_req][0],
                                                local_cand_dict[split_req][1] & time_cand_dict[split_req][1])

                # number_of_candidate_pairs = sum(len(agg_cand_dict[x][0]) + len(agg_cand_dict[x][1]) for x in agg_cand_dict.keys())
                # print(f"number of candidate pairs for line {line.id} and direction {direction}: {number_of_candidate_pairs}")

                # make permutations (check if some split_requests already started)
                # user_sorted: List[SplitRequest] = sorted(agg_cand_dict.keys(), key=lambda user: user.split_id)

                for event_user in agg_cand_dict.keys():
                    permutations |= {
                        PickUpEvent(event_user, set(), event_user.earl_start_time, event_user.latest_start_time)}

                    hold = self.get_permutations(event_user, list(agg_cand_dict[event_user][0]), set(), 0, True)
                    # if len(hold) > 0:
                    #    print(f"for split {event_user.split_id} of user {event_user.id} there were {len(hold)} pick-up combis found")
                    permutations |= hold

                    permutations |= {
                        DropOffEvent(event_user, set(), event_user.earl_arr_time, event_user.latest_arr_time)}
                    hold = self.get_permutations(event_user, list(agg_cand_dict[event_user][1]), set(), 0, False)
                    # if len(hold) > 0:
                    #    print(f"for split {event_user.split_id} of user {event_user.id} there were {len(hold)} drop-off combis found")
                    permutations |= hold

            self.event_graph.add_events(permutations)
            # unnecessary all nodes should be valid by construction, could use for debugging though
            self.event_graph.check_connectivity(idle_event)

        Global.COMPUTATION_TIME_BUILDING = round(time.time() - Global.COMPUTATION_START_TIME, 4)
        print(f"Created EventGraph after {Global.COMPUTATION_TIME_BUILDING} seconds")
        print(self.event_graph.data_in_string())
        Global.EVENT_GRAPH_NODES = len(self.event_graph.edge_dict.keys())
        Global.EVENT_GRAPH_EDGES = self.event_graph.get_number_of_edges()
        Global.NUMBER_OF_SPLITS = len(self.event_graph.request_dict.keys())
        Global.COMPUTATION_START_TIME = time.time()

        #for x in self.event_graph.edge_dict.keys():
        #    print(x)

        # build lin. model
        cplex_model: CplexSolver = CplexSolver(self.event_graph, all_active_requests, self.bus_list)

        Global.COMPUTATION_TIME_BUILDING_CPLEX = round(time.time() - Global.COMPUTATION_START_TIME, 4)
        print(f"Build the Cplex-Model after {Global.COMPUTATION_TIME_BUILDING_CPLEX} seconds")
        Global.COMPUTATION_START_TIME = time.time()

        # solve model
        cplex_model.solve_model()

        # convert to route solution
        self.curr_routes = cplex_model.convert_to_plan()
