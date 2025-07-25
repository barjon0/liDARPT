"""
© 2025 Jonas Barth

This file is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0).

You may share and adapt the material for non-commercial use, provided you give appropriate credit,
indicate if changes were made, and distribute your contributions under the same license.

License: https://creativecommons.org/licenses/by-nc-sa/4.0/

File: IOHandler.py
Description: Script for starting a liDARPT instance solve
            Reading in configuration file and linked request and network instance,
            managing control flow, creating output and writing to file
"""

import csv
import json
import sys
import os
import time

import matplotlib.pyplot as plt
from typing import List, Dict, Tuple, Set

from models.Plan import Route
from utils import Global, Timer, RequestPreprocessing
from main.plan.EventBasedMILP import EventBasedMILP
from main.plan.Planner import Planner
from main.scope.Context import Context, Static
from main.scope.Executor import Executor
from models.Demand import Request, SplitRequest
from utils.LineGraph import LineGraph
from utils.Timer import TimeImpl
from models.Network import Bus, Stop, Line


def find_planner(solver_str: str, network: List[Bus], network_graph: LineGraph):
    if solver_str == 'eventMILP':
        return EventBasedMILP(network, network_graph)
    else:
        raise ValueError("the given solver string is not registered in the system")


def find_context(context_str, requests: Set[Request], executor: Executor, planner: Planner):
    if context_str == 'static':
        return Static(requests, executor, planner)
    else:
        raise ValueError("the given context string is not registered in the system")


def read_requests(request_path, network_graph: LineGraph):
    """
    Reads in the request file and creates Request objects with time windows, route options and splits
    :param request_path: Path to request file
    :param network_graph: Basic LineGraph (only transfer Stop - transfer Stop edges)
    :return: Set of Request objects
    """
    request_set: Set[Request] = set()

    stops: Dict[int, Stop] = {}
    for stop in network_graph.all_stops:
        stops[stop.id] = stop

    with open(request_path, 'r') as request_file:
        csv_requests = csv.reader(request_file)

        next(csv_requests)
        for row in csv_requests:
            earl_time = Timer.conv_string_2_time(row[2])
            pick_up: Stop = stops[int(row[3])]
            drop_off: Stop = stops[int(row[4])]

            network_graph.add_request(pick_up, drop_off)

            delay_time, numb_transfers, fastest_time = \
                RequestPreprocessing.complete_request(pick_up, drop_off, network_graph,int(row[5]))
            request = Request(int(row[0]), int(row[5]), pick_up, drop_off,
                              earl_time, earl_time.add_seconds(delay_time + Global.TIME_WINDOW_SECONDS),
                              Timer.conv_string_2_time(row[1]), numb_transfers, fastest_time)
            print(request.id)
            split_lists: List[List[SplitRequest]] = RequestPreprocessing.find_split_requests(request, network_graph)
            for variation_numb in range(len(split_lists)):
                request.split_requests[variation_numb] = split_lists[variation_numb]
                RequestPreprocessing.fill_time_windows(request, split_lists[variation_numb])

            network_graph.delete_request(pick_up, drop_off)

            request_set.add(request)

    return request_set


def read_bus_network(network_path: str):
    """
    Reads in bus network file to generate classes
    :param network_path: Path to network file
    :return: List of buses (with reference to lines and stops)
    """
    with open(network_path, 'r') as network_file:
        network_dict: dict = json.load(network_file)

    max_id: int = 0
    stops: Dict[int, Stop] = {}
    stop_list = network_dict.get('stops')
    for single_stop in stop_list:
        if single_stop["id"] > max_id:
            max_id = single_stop["id"]
        stops[single_stop["id"]] = Stop(single_stop["id"], tuple(single_stop["coordinates"]))

    lines: Dict[int, Line] = {}
    line_list = network_dict.get('lines')
    depot_dict: Dict[Tuple[int, int], Stop] = {x.coordinates: x for x in stops.values()}
    for line in line_list:
        depot_stop: Stop
        depot_coord: Tuple[int, int] = tuple(line["depot"])

        if depot_coord in depot_dict:
            depot_stop = depot_dict[depot_coord]
        else:
            max_id = max_id + 1
            depot_stop = Stop(max_id, depot_coord)
            depot_dict[depot_coord] = depot_stop

        stops_of_line: List[Stop] = []
        for stop_id in line["stops"]:
            stops_of_line.append(stops[stop_id])
        if Global.CAPACITY_PER_LINE is None:
            if "capacity" in line:
                lines[line["id"]] = Line(line["id"], stops_of_line, depot_stop, int(line["capacity"]),
                                         Timer.conv_string_2_time(line["startTime"]),
                                         Timer.conv_string_2_time(line["endTime"]))
            else:
                raise ValueError("No Global Capacity or individual given")
        else:
            lines[line["id"]] = Line(line["id"], stops_of_line, depot_stop, Global.CAPACITY_PER_LINE,
                                     Timer.conv_string_2_time(line["startTime"]),
                                     Timer.conv_string_2_time(line["endTime"]))

    buses: List[Bus] = []
    bus_list = network_dict.get('buses')

    for bus in bus_list:
        buses.append(Bus(bus["id"], lines[bus["line"]]))

    return buses


def main(path_2_config: str):
    """
    Starting a solve with information from config file.
    :param path_2_config: Path to configuration file
    """
    with open(path_2_config, 'r') as config_file:
        config: dict = json.load(config_file)

    Global.COMPUTATION_START_TIME = time.time()
    Global.AVERAGE_KMH = config.get('averageKmH')
    Global.KM_PER_UNIT = config.get('KmPerUnit')
    Global.COST_PER_KM = config.get('costPerKM')
    Global.CO2_PER_KM = config.get('co2PerKM')
    Global.CAPACITY_PER_LINE = config.get('capacityPerLine')
    Global.NUMBER_OF_EXTRA_TRANSFERS = config.get('numberOfExtraTransfers')
    Global.MAX_DELAY_EQUATION = config.get('maxDelayEquation')
    Global.TRANSFER_SECONDS = config.get('transferMinutes') * 60
    Global.TIME_WINDOW_SECONDS = config.get('timeWindowMinutes') * 60

    request_path: str = config.get('pathRequestFile')
    network_path: str = config.get('pathNetworkFile')
    output_path: str = config.get('outputPath')
    context_str: str = config.get('context')
    solver_str: str = config.get('solver')

    network: List[Bus] = read_bus_network(network_path)
    network_graph = LineGraph(network)
    requests: Set[Request] = read_requests(request_path, network_graph)

    plann: Planner = find_planner(solver_str, network, network_graph)
    context: Context = find_context(context_str, requests, Executor(network, requests), plann)

    Global.COMPUTATION_TIME_READING = round(time.time() - Global.COMPUTATION_START_TIME, 4)
    print(
        f"Done with reading in; finding shortest routes and all route options after {Global.COMPUTATION_TIME_READING} seconds.")
    Global.COMPUTATION_START_TIME = time.time()

    #output_network({x.line for x in network})

    context.start_context()

    create_output(requests, context.executor.routes, output_path)

    print(
        f"Converted and validated plan; generated output in {round(time.time() - Global.COMPUTATION_START_TIME, 4)} seconds")


def find_output_path(base_output_path: str):
    max_number = 0
    subdirectories = [name for name in os.listdir(base_output_path)
                      if os.path.isdir(os.path.join(base_output_path, name))]

    for sub_name in subdirectories:
        split_name = sub_name.split("_")
        index: int
        try:
            index = int(split_name[-1])
            if max_number < index:
                max_number = index
        except ValueError:
            pass

    result_path = f"{base_output_path}/run_{max_number + 1}"
    os.makedirs(result_path)

    return result_path


def output_network(lines: Set[Line]):
    """
    Visualization of network lines and stops in 2d.
    :param lines: set of all lines
    """
    all_stop_cords: Set[Stop] = set()
    transfer_points = set()
    for line in lines:
        all_stop_cords |= set(line.stops)
        for lB in (lines - {line}):
            transfer_points |= set(line.stops) & set(lB.stops)
    all_stop_cords_list = list(all_stop_cords)

    x = [i.coordinates[0] for i in all_stop_cords_list]
    y = [i.coordinates[1] for i in all_stop_cords_list]

    #plt.plot(x, y, 'ro')

    xT = [i.coordinates[0] for i in transfer_points]
    yT = [i.coordinates[1] for i in transfer_points]

    #color_set = ['red', 'green', 'blue', 'yellow', 'black', 'purple', 'pink', 'brown'] * 3
    color_set2 = ['green', 'blue', 'black']
    color_iter = iter(color_set2)
    ia = 0
    line_order = list(lines)
    line_order.sort(key=lambda x: x.id, reverse=True)

    for line in line_order:
        color_name = next(color_iter)
        for i in range(len(line.stops) - 1):
            x1, y1 = line.stops[i].coordinates
            x2, y2 = line.stops[i + 1].coordinates
            if ia == 0:
                plt.plot([x1, x2], [y1, y2], marker='s', color=color_name, label=line.id)
                ia = 1
            else:
                plt.plot([x1, x2], [y1, y2], marker='s', color=color_name)
        ia = 0

    plt.plot(xT, yT, 's', color="lightgreen", markersize=10)

    plt.ylim([-5, 20])
    plt.xlim([-5, 20])
    plt.xticks(ticks=plt.xticks()[0], labels=[])
    plt.yticks(ticks=plt.yticks()[0], labels=[])
    plt.legend()
    plt.show()


def create_output(requests: Set[Request], plans: List[Route], base_output_path: str):
    """
    Outputs the plan to number of csv files with key performance indicators.
    CSV-file for each bus plan, CSV-file for request information, overall output file and visualization of plan
    :param requests: set of all requests
    :param plans: list of bus plans
    :param base_output_path: path to output directory
    """
    buses = [x.bus for x in plans]
    lines = {x.line for x in buses}

    numb_denied = 0
    km_booked = 0
    bus_overall_km_dict: Dict[Bus, float] = dict.fromkeys(buses, 0)
    bus_empty_km_dict: Dict[Bus, float] = dict.fromkeys(buses, 0)
    req_km_dict: Dict[Request, float] = dict.fromkeys(requests, 0)
    request_stop_dict: Dict[Request, List[Tuple[TimeImpl, int, int]]] = {}

    csv_out_bus: Dict[Bus, List[List[str]]] = {
        x: [["number", "stop ID", "arrival time", "departure time", "pick up users", "drop of users"]] for x in
        buses}
    csv_out_req: List[List[str]] = [["user ID", "used buses", "used transfer points", "waiting time", "ride time", "shortest time possible" ,"number of transfers(for shortest)"]]

    for req in requests:
        if req.act_start_time is not None:
            km_booked += req.pick_up_location.calc_distance(req.drop_off_location)
            request_stop_dict[req] = [(req.act_start_time, req.pick_up_location.id, -1)]
        else:
            numb_denied += 1

    for plan in plans:
        if len(plan.stop_list) > 0:
            prev_stop = plan.stop_list[0]
            passengers: Set[Request] = set(prev_stop.pick_up)
            bus_overall_km_dict[plan.bus] = 0
            csv_out_bus[plan.bus].append([1] + prev_stop.to_output())
            counter = 2

            for curr_stop in plan.stop_list[1:]:
                csv_out_bus[plan.bus].append([counter] + curr_stop.to_output())
                km_between = prev_stop.stop.calc_distance(curr_stop.stop)
                bus_overall_km_dict[plan.bus] += km_between
                if len(passengers) == 0:
                    bus_empty_km_dict[plan.bus] += km_between
                else:
                    for user in passengers:
                        req_km_dict[user] += km_between

                for u_dropped in curr_stop.drop_off:
                    request_stop_dict[u_dropped].append(
                        (curr_stop.arriv_time, curr_stop.stop.id, curr_stop.bus.id))

                passengers = (passengers - curr_stop.drop_off) | curr_stop.pick_up
                prev_stop = curr_stop
                counter += 1

    sorted_requests = sorted(requests, key=lambda x: x.id)

    count_accepted = 0
    for req in sorted_requests:
        km_req = Timer.conv_time_to_dist(req.fastest_time - (Global.TRANSFER_SECONDS * req.numb_transfer))
        if req.act_start_time is not None:
            count_accepted += 1
            wait_time = req.act_end_time.get_in_seconds() - req.act_start_time.get_in_seconds() - Timer.calc_time(req_km_dict[req])
            request_stop_dict[req].sort(key=lambda x: x[0])
            csv_out_req.append(
                [str(req), str([x[2] for x in request_stop_dict[req][1:]]), str([x[1] for x in request_stop_dict[req]]),
                 str(round(wait_time / 60, 1)), round(Timer.calc_time(req_km_dict[req]) / 60, 2),
                 round((Timer.calc_time(km_req) + req.numb_transfer * Global.TRANSFER_SECONDS) / 60, 2), req.numb_transfer])
        else:
            csv_out_req.append([str(req), "-", "-", "-", "-", round((
                                                                                Timer.calc_time(km_req) + req.numb_transfer * Global.TRANSFER_SECONDS) / 60, 2),
                                req.numb_transfer])

    overall_numbers: List[List[str]] = []
    km_travel_total = round(sum(bus_overall_km_dict.values()), 3)
    km_empty_total = round(sum(bus_empty_km_dict.values()), 3)
    km_used_total = round(km_travel_total - km_empty_total, 3)
    overall_numbers += [[f"km travelled total: {km_travel_total}"], [f"empty km total: {km_empty_total}"],
                        [f"used km total: {km_used_total}"]]
    acc_km_req = sum(req_km_dict.values())

    try:
        overall_numbers.append([f"system efficiency: {round(km_booked / km_travel_total, 3)}"])
        overall_numbers.append([f"deviation factor: {round(acc_km_req / km_booked, 3)}"])
        overall_numbers.append([f"vehicle utilization: {round(acc_km_req / km_used_total, 3)}"])
        overall_numbers.append([f"empty km share: {round(km_empty_total / km_travel_total, 3)}"])
        overall_numbers.append([f"Number of Requests accepted: {count_accepted}"])
    except ZeroDivisionError:
        pass
    overall_numbers.append([f"Relative MIP Gap Number Requests: {Global.INTEGRALITY_GAP_FIRST}"])
    overall_numbers.append([f"Relative MIP Gap KM travelled: {Global.INTEGRALITY_GAP_SECOND}"])
    overall_numbers.append([f"Number of Split Requests: {Global.NUMBER_OF_SPLITS}"])
    overall_numbers.append([f"Event Graph Nodes: {Global.EVENT_GRAPH_NODES}"])
    overall_numbers.append([f"Event Graph Edges: {Global.EVENT_GRAPH_EDGES}"])
    overall_numbers.append(
        [f"computation time for reading in: {time.strftime('%H:%M:%S', time.gmtime(Global.COMPUTATION_TIME_READING))}"])
    overall_numbers.append([
        f"computation time for building event graph: {time.strftime('%H:%M:%S', time.gmtime(Global.COMPUTATION_TIME_BUILDING))}"])
    overall_numbers.append([
        f"computation time for building model: {time.strftime('%H:%M:%S', time.gmtime(Global.COMPUTATION_TIME_BUILDING_CPLEX))}"])
    overall_numbers.append([
        f"computation time for solving first model: {time.strftime('%H:%M:%S', time.gmtime(Global.COMPUTATION_TIME_SOLVING_FIRST))}"])
    overall_numbers.append([
        f"computation time for solving second model: {time.strftime('%H:%M:%S', time.gmtime(Global.COMPUTATION_TIME_SOLVING_SECOND))}"])

    path_to_output = find_output_path(base_output_path)
    fig = visualize_plan(plans, lines)
    fig.savefig(f"{path_to_output}/plan.png")

    for bus in buses:
        with open(f"{path_to_output}/bus_{bus.id}_out.csv", mode="w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerows(csv_out_bus[bus])

    with open(f"{path_to_output}/requests_out.csv", mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerows(csv_out_req)

    with open(f"{path_to_output}/overall_out.csv", mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerows(overall_numbers)


def visualize_plan(plan: List[Route], lines: Set[Line]):
    """
    Creates plot to visualize plan, draws route of buses.
    :param plan: list of routes
    :param lines: set of all lines
    """
    segment_dict: Dict[frozenset[Stop], list] = {}  # dictionary for segment in network, count occurence
    km_overall: float = 0

    # count occurence of each segment -> calc overall km and normalize
    color_set = ['red', 'green', 'blue', 'purple', 'pink', 'brown', 'orange'] * 3
    color_iter = iter(color_set)
    color_dict: Dict[Line, str] = {}
    for line in lines:
        color_dict[line] = next(color_iter)

    for route in plan:
        for i in range(len(route.stop_list) - 1):
            stop1 = route.stop_list[i].stop
            stop2 = route.stop_list[i + 1].stop
            stop_set: frozenset = frozenset({stop1, stop2})
            km_needed = Timer.calc_time(stop1.calc_distance(stop2))
            km_overall += km_needed

            if len(stop_set) == 2:
                if stop_set not in segment_dict:
                    segment_dict[stop_set] = [km_needed, route.bus.line]
                else:
                    segment_dict[stop_set][0] += km_needed

    fig, ax = plt.subplots()

    max_thickness = 10.0
    sorted_seg = sorted(list(segment_dict.keys()), key=lambda u: segment_dict[u][0], reverse=True)

    for stop_set in sorted_seg:
        stop_set_iter = iter(stop_set)
        x1, y1 = next(stop_set_iter).coordinates
        x2, y2 = next(stop_set_iter).coordinates
        ax.plot([x1, x2], [y1, y2], color=color_dict[segment_dict[stop_set][1]],
                 lw=max_thickness * (segment_dict[stop_set][0] / km_overall))

    # build pyplot graph
    all_stop_cords: Set[Stop] = set()
    for line in lines:
        all_stop_cords |= set(line.stops)
    all_stop_cords_list = list(all_stop_cords)

    x = [i.coordinates[0] for i in all_stop_cords_list]
    y = [i.coordinates[1] for i in all_stop_cords_list]

    ax.plot(x, y, 'ko')

    return fig


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # The first argument is the file path
        config_path = sys.argv[1]
        main(config_path)
    else:
        print("Please provide the file path to the config file as an argument.")
