"""
© 2025 Jonas Barth

This file is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0).

You may share and adapt the material for non-commercial use, provided you give appropriate credit,
indicate if changes were made, and distribute your contributions under the same license.

License: https://creativecommons.org/licenses/by-nc-sa/4.0/

File: RequestPreprocessing.py
Description: Handles basic preprocessing of requests,
            finds shortest route and different route options for request
"""
import math
from typing import Dict, Set, List, Tuple

from models.Network import Stop, Line
from utils import Global, Timer
from models.Demand import SplitRequest, Request
from utils.LineGraph import LineGraph, LineEdge
from utils.PriorityQueue import PriorityQueue
from utils.Timer import TimeImpl
from models.Plan import RouteStop


def calc_fastest(pick_up_location: Stop, drop_off_location: Stop, network_graph: LineGraph, number_of_passengers: int) -> Tuple[int, int]:
    """
    Calculates the fastest route of a request from pick-up to drop-off with Dijkstra-Algorithm.
    :param pick_up_location: pick-up stop of request
    :param drop_off_location: drop-off stop of request
    :param network_graph: LineGraph with request-specific edges
    :param number_of_passengers: number of passengers connected to request
    :return: Tuple of fastest time to arrive at destination and the number of transfers required.
    """
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
    """
    Fills out required info from data input of request
    :param pick_up: pick-up stop of request
    :param drop_off: drop-off stop of request
    :param network_graph: LineGraph with request-specific edges
    :param number_of_passengers: number of passengers connected to request
    :return: maximum travel time, number of transfers in shortest route, duration of shortest route
    """
    # calculate fastest time -> account for transfers -> plug into max_delay_equation, return corresp. km
    fastest_time, numb_transfers = calc_fastest(pick_up, drop_off, network_graph, number_of_passengers)
    assert fastest_time is not Global.INFINITE_INT
    long_delay: int = 60 * max(0, round(eval(Global.MAX_DELAY_EQUATION, {"math": math, "x": (fastest_time/60)})))

    return long_delay + fastest_time, numb_transfers, fastest_time


def rec_dfs(last_line: LineEdge, curr_seconds: int, curr_transfers: int, prev_visited: Set[Stop],
            curr_open: List[SplitRequest], look_up_dict: Dict[LineEdge, SplitRequest], max_time: int,
            max_hop_count: int, target: Stop, network_graph: LineGraph, number_of_passengers: int):
    """
    Finds all route options for a request
    Recursive method for Depth-First-Search on LineGraph
    :param curr_open: list of SplitRequest already added
    :param last_line: previous LineEdge
    :param curr_seconds: current number of seconds needed
    :param curr_transfers: current number of transfers needed
    :param prev_visited: set of previously visited stops
    :param look_up_dict: dictionary of LineEdge to SplitRequest
    :param max_time: maximum travel time of request
    :param max_hop_count: maximum number of transfers allowed for request
    :param target: drop-off location of request
    :param network_graph: request-specific LineGraph
    :param number_of_passengers: number of passengers of request
    :return: List of List of SplitRequests
    """
    if curr_transfers > max_hop_count or curr_seconds > max_time:
        return []
    else:
        curr_open.append(look_up_dict[last_line])
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
                                         prev_visited.copy(), curr_open.copy(), look_up_dict, max_time,
                                         max_hop_count, target, network_graph, number_of_passengers)

            return combined_poss


# Algo to retrieve all possible Subroutes in network from transfer point to transfer point(call only once store in LineGraph?)
# + Per request: make SplitRequest for all pick-up/drop-off to transfer points subroutes(for every request) and for all subroutes in network -> store in dict

# only call dfs once with split-req dict, starting at all subroutes of start -> check time and transfer constraints
def find_split_requests(request: Request, network_graph: LineGraph) -> List[List[SplitRequest]]:
    """
    Finds all SplitRequests for given request. Builds look-up-dictionary of LineEdge to SplitRequest, before calling rec_dfs
    :param request: object of request
    :param network_graph: request-specific LineGraph
    :return: List of List of SplitRequests (each list is a route option)
    """
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
    net_graph_edges = sorted(list(network_graph.get_edges()), key=lambda x: hash(x))
    for agg_edge in net_graph_edges:
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
                              [], agg_edges_dict, max_time, request.numb_transfer + Global.NUMBER_OF_EXTRA_TRANSFERS,
                              request.drop_off_location, network_graph, request.number_of_passengers)

    return result


def fill_time_windows(request: Request, split_req_list: List[SplitRequest]):
    """
    Fill the time windows of split requests of a route option
    :param request: Object of a request
    :param split_req_list: list of split requests of route option
    """
    # go through split_req_list and fill time windows (as big as possible)

    total_distance: float = sum(x.pick_up_location.calc_distance(x.drop_off_location) for x in split_req_list)

    shortest_time: int = Timer.calc_time(total_distance) + (len(split_req_list) * Global.TRANSFER_SECONDS)
    curr_earl_time: int = 0

    # special case for first split, because of fixed time window for pick-up
    start_split = split_req_list[0]
    start_split.earl_start_time = request.earl_start_time.add_seconds(0)
    start_split.latest_start_time = request.earl_start_time.add_seconds(Global.TIME_WINDOW_SECONDS)

    curr_earl_time += Global.TRANSFER_SECONDS + Timer.calc_time(
        start_split.pick_up_location.calc_distance(start_split.drop_off_location))

    start_split.earl_arr_time = start_split.earl_start_time.add_seconds(curr_earl_time)
    prop_lat_arr: TimeImpl = request.latest_arr_time.sub_seconds(shortest_time - curr_earl_time)
    if start_split.latest_arr_time is None or start_split.latest_arr_time < prop_lat_arr:
        start_split.latest_arr_time = prop_lat_arr

    assert start_split.earl_arr_time < start_split.latest_arr_time

    for split_req in split_req_list[1:]:
        prop_time_earl_start: TimeImpl = request.earl_start_time.add_seconds(curr_earl_time)
        if split_req.earl_start_time is None or split_req.earl_start_time > prop_time_earl_start:
            split_req.earl_start_time = prop_time_earl_start

        intermediate_time = Global.TRANSFER_SECONDS + Timer.calc_time(
            split_req.pick_up_location.calc_distance(split_req.drop_off_location))

        prop_time_earl_arr = prop_time_earl_start.add_seconds(intermediate_time)
        if split_req.earl_arr_time is None or split_req.earl_arr_time > prop_time_earl_arr:
            split_req.earl_arr_time = prop_time_earl_arr

        curr_earl_time += intermediate_time
        prop_time_lat_arr: TimeImpl = request.latest_arr_time.sub_seconds(shortest_time - curr_earl_time)
        if split_req.latest_arr_time is None or split_req.latest_arr_time < prop_time_lat_arr:
            split_req.latest_arr_time = prop_time_lat_arr

        prop_time_lat_start = prop_time_lat_arr.sub_seconds(intermediate_time)
        if split_req.latest_start_time is None or split_req.latest_start_time < prop_time_lat_start:
            split_req.latest_start_time = prop_time_lat_start
