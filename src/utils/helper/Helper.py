import math
from typing import Dict, Set, List, Tuple

from utils import Global
from utils.demand.AbstractRequest import SplitRequest, Request
from utils.helper import Timer
from utils.helper.LineGraph import LineGraph, LineEdge
from utils.helper.PriorityQueue import PriorityQueue
from utils.helper.Timer import TimeImpl
from utils.network.Stop import Stop
from utils.network.Line import Line
from utils.plan.RouteStop import RouteStop


def calc_distance(stop1: Stop, stop2: Stop) -> float:
    # calculate euclidean distance
    unit_dist = math.sqrt(
        (stop2.coordinates[0] - stop1.coordinates[0]) ** 2 + (stop2.coordinates[1] - stop1.coordinates[1]) ** 2)
    return unit_dist * Global.KM_PER_UNIT


def check_dir(split_req: SplitRequest):
    line: Line = split_req.line
    start_idx = line.stops.index(split_req.pick_up_location)
    end_idx = line.stops.index(split_req.drop_off_location)
    if start_idx < end_idx:
        return 0
    else:
        return 1


# need to calculate number of transfers as well
def calc_fastest(pick_up_location: Stop, drop_off_location: Stop, network_graph: LineGraph, number_of_passengers: int) -> Tuple[int, int]:
    # dijkstra alg.
    pred_dict: Dict[Stop, (
        Set[Line], int)] = {}  # contains poss. lines request is in at stop v and number of transfers at this point
    for stop in network_graph.get_nodes():
        pred_dict[stop] = (set(), 0)

    pick_lines: frozenset = frozenset(
        [edge.line for edge in network_graph.get_edges_out(pick_up_location) if
         edge.line.capacity >= number_of_passengers])
    pred_dict[pick_up_location] = (pick_lines, 1)

    queue: PriorityQueue = PriorityQueue(network_graph.get_nodes())
    queue.replace(pick_up_location, Global.TRANSFER_SECONDS)

    while (not queue.is_empty()) and (queue.get_priority(drop_off_location) is not None):
        v, dist_v = queue.pop()
        for adj_edge in network_graph.get_edges_out(v):
            if adj_edge.line.capacity >= number_of_passengers:
                u = adj_edge.v2
                dist_u = queue.get_priority(u)
                if dist_u is not None:
                    # need to know in which lines u could be here -> if way to v is another line -> transfer time
                    numb_transfer: int = pred_dict[v][1]
                    alter: int = dist_v + adj_edge.duration

                    if adj_edge.line not in pred_dict[v][0]:
                        alter += Global.TRANSFER_SECONDS
                        numb_transfer += 1

                    # if equal decide by number of transfers
                    if alter == dist_u and numb_transfer == pred_dict[u][1]:
                        pred_dict[u][0].add(adj_edge.line)
                    elif alter < dist_u or (alter == dist_u and numb_transfer < pred_dict[u][1]):
                        queue.replace(u, alter)
                        pred_dict[u] = ({adj_edge.line}, numb_transfer)

    fast_time, transfers = queue.final_vals[drop_off_location], pred_dict[drop_off_location][1]
    return fast_time, transfers

def complete_request(pick_up: Stop, drop_off: Stop, network_graph: LineGraph, number_of_passengers: int):
    # calculate fastest time -> account for transfers -> plug into max_delay_equation, return corresp. km
    fastest_time, numb_transfers = calc_fastest(pick_up, drop_off, network_graph, number_of_passengers)
    assert fastest_time is not Global.INFINITE_INT
    long_delay: int = 60 * max(0, round(eval(Global.MAX_DELAY_EQUATION, {"math": math, "x": (fastest_time/60)})))

    return long_delay + fastest_time, numb_transfers, fastest_time


# check if hop-count exceeded -> add current stop to all open lists -> if not source: recursive call to neighbours
def rec_dfs(last_line: LineEdge, curr_seconds: int, curr_transfers: int, prev_visited: Set[Stop],
            curr_open: List[List[SplitRequest]], look_up_dict: Dict[LineEdge, SplitRequest], max_time: int,
            max_hop_count: int, target: Stop, network_graph: LineGraph, number_of_passengers: int):
    if curr_transfers > max_hop_count or curr_seconds > max_time:
        return []
    else:
        for combi in curr_open:
            combi.append(look_up_dict[last_line])
        if last_line.v2 == target:
            return curr_open
        else:
            prev_visited.add(last_line.v1)
            # find all successors of v2, that are not yet explored and operate on new line
            successors: List[LineEdge] = [x for x in network_graph.get_edges_out(last_line.v2)
                                          if (x.v2 not in prev_visited) and (x.line != last_line.line) and (
                                                  x.line.capacity >= number_of_passengers)]

            combined_poss: List[List[SplitRequest]] = []
            for suc in successors:
                combined_poss += rec_dfs(suc, curr_seconds + Global.TRANSFER_SECONDS + suc.duration, curr_transfers + 1,
                                         prev_visited.copy(), [x.copy() for x in curr_open], look_up_dict, max_time,
                                         max_hop_count, target, network_graph, number_of_passengers)

            return combined_poss


def calc_time_multi(v1: Stop, v2: Stop, line: Line):
    index_v1: int = line.stops.index(v1)
    index_v2: int = line.stops.index(v2)

    # swap values if needed
    if index_v2 < index_v1:
        buf = index_v2
        index_v2 = index_v1
        index_v1 = buf

    duration: float = 0
    for i in range(index_v1, index_v2):
        duration += Timer.calc_time(calc_distance(line.stops[i], line.stops[i + 1]))

    return duration


# Algo to retrieve all possible Subroutes in network from transfer point to transfer point(call only once store in LineGraph?)
# + Per request: make SplitRequest for all pick-up/drop-off to transfer points subroutes(for every request) and for all subroutes in network -> store in dict

# only call dfs once with split-req dict, starting at all subroutes of start -> check time and transfer constraints
def find_split_requests(request: Request, network_graph: LineGraph) -> List[List[SplitRequest]]:
    pick_up_edges: List[LineEdge] = network_graph.get_edges_out(request.pick_up_location)
    drop_off_edges: List[LineEdge] = network_graph.get_edges_in(request.drop_off_location)

    pick_up_lines: Set[Line] = {x.line for x in pick_up_edges}
    drop_off_lines: Set[Line] = {x.line for x in drop_off_edges}

    pick_up_trans: Set[Stop] = set()
    # only need to look into further sub-lines if node is not a transfer point
    if len(pick_up_lines) == 1:
        # find all transfer points and store with in set
        line: Line = next(iter(pick_up_lines))
        for other in (network_graph.all_lines - {line}):
            pick_up_trans |= (set(line.stops) & set(other.stops))

    drop_off_trans: Set[Stop] = set()
    if len(drop_off_lines) == 1:
        # same for drop-off point
        line: Line = next(iter(drop_off_lines))
        # just check line against all other lines -> look for stops appearing mult. times
        for other in (network_graph.all_lines - {line}):
            drop_off_trans |= (set(line.stops) & set(other.stops))

    # fill dict of LineEdge to SplitRequest for all aggregated routes in network
    agg_edges_dict: Dict[LineEdge, SplitRequest] = {}
    for agg_edge in network_graph.get_edges():
        agg_edges_dict[agg_edge] = SplitRequest(request, agg_edge.v1, agg_edge.v2, agg_edge.line,
                                                request.number_of_passengers)

    # now do dfs with dictionary of split-requests, account for max. number of transfers and time constraints
    max_time: int = (request.latest_arr_time - request.latest_start_time).get_in_seconds()

    # depth-first search to retrieve all combinations, starting at start-position
    result: List[List[SplitRequest]] = []
    start_tupels: List[LineEdge] = network_graph.get_edges_out(request.pick_up_location)

    for start_sub_line in start_tupels:
        if start_sub_line.line.capacity >= request.number_of_passengers:
            result += rec_dfs(start_sub_line, Global.TRANSFER_SECONDS + start_sub_line.duration, 1,
                              {request.pick_up_location},
                              [[]], agg_edges_dict, max_time, request.numb_transfer + Global.NUMBER_OF_EXTRA_TRANSFERS,
                              request.drop_off_location, network_graph, request.number_of_passengers)

    return result


# check if there are feasible routes regarding time windows,
# if event_user is pick-up/drop-off and others are already in car
# use best case time ->
def get_event_window(event_user: SplitRequest, other_users: Set[SplitRequest], event_type: bool) -> (
        TimeImpl, TimeImpl):
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
            duration: int = Timer.calc_time(calc_distance(curr_stop, key))
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
        duration = Timer.calc_time(calc_distance(curr_stop, event_user.drop_off_location))
        rem_travel_time = -duration - Global.TRANSFER_SECONDS
        earl_time = curr_time.add_seconds(duration)

    # need to check for all remaining if latest_arr time is satisfied,
    # -> also check latest possible departure: sum travel times from here, check latest_arr time - travel time, choose leftmost

    for key in key_list_drop:
        if key in cand_dict:
            drop_off_users: Set[SplitRequest] = cand_dict[key]
            duration: int = Timer.calc_time(calc_distance(curr_stop, key))

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


def check_overlap(interval_1_start: TimeImpl, interval_1_end: TimeImpl, interval_2_start: TimeImpl,
                  interval_2_end: TimeImpl):
    if interval_1_start > interval_2_end:
        return False
    elif interval_1_end < interval_2_start:
        return False
    else:
        return True


def calc_total_network_size(line_set: Set[Line]):
    total_sum = 0
    for line in line_set:
        for i in range(len(line.stops) - 1):
            total_sum += calc_distance(line.stops[i], line.stops[i + 1])

    return total_sum


def insert_sorted(waiting_bus_stops: List[RouteStop], r_stop: RouteStop):
    i = 0
    while i < len(waiting_bus_stops) and waiting_bus_stops[i].depart_time < r_stop.depart_time:
        i += 1
    waiting_bus_stops.insert(i, r_stop)
