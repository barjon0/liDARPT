"""
© 2025 Jonas Barth

This file is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0).

You may share and adapt the material for non-commercial use, provided you give appropriate credit,
indicate if changes were made, and distribute your contributions under the same license.

License: https://creativecommons.org/licenses/by-nc-sa/4.0/

File: DataConverter.py
Description: convert liDARPT test instances to DARP
            readable by implementation from https://git.uni-wuppertal.de/dgaul/a-tight-formulation-for-the-darp
"""
import json
from pathlib import Path

from typing import List

from scripts.IOHandler import read_bus_network, read_requests
from utils import Global
from models.Demand import Request
from utils.LineGraph import LineGraph
from models.Network import Bus, Stop


def createDistanceFile(requests: List[Request], depot: Stop, output_path: str, name: str):
    req_stops_pick = [x.pick_up_location for x in requests]
    req_stops_drop = [x.drop_off_location for x in requests]

    all_stops = [depot] + req_stops_pick + req_stops_drop

    output_list = []
    for i in range(len(all_stops)):
        output_line = []
        for j in range(len(all_stops)):
            output_line.append(round(all_stops[i].calc_distance(all_stops[j]), 2))
        output_list.append(output_line)

    #write file to output
    with open(output_path + "/" + name + "_c_a.txt", 'w') as f:
        for sublist in output_list:
            # Join each sublist's values with a space and write to file
            f.write(" ".join(map(str, sublist)) + "\n")

def createRequestFile(requests: List[Request], network: List[Bus], output_path: str, name: str):
    # find time for requests
    number = int(name[1])
    tw_length = (number+5)*60
    first_out = [len(network), 2*len(requests), tw_length, Global.CAPACITY_PER_LINE, 0]

    depot_out_first = [0, 0.0, 0, 0.0, tw_length, tw_length]
    depot_out_last = [2*len(requests)+1, 0.0, 0, 0.0, tw_length, tw_length]
    conversion_value = 7 * 60

    pick_out = []
    for i in range(len(requests)):
        # make output for pick up stops
        # convert time windows
        earliest = (requests[i].earl_start_time.get_in_seconds() - (conversion_value * 60)) / 60
        latest = (requests[i].latest_start_time.get_in_seconds() - (conversion_value * 60)) / 60
        max_ride_time = (requests[i].latest_arr_time - requests[i].latest_start_time).get_in_seconds() / 60

        pick_out.append([i + 1, Global.TRANSFER_SECONDS / 60, requests[i].number_of_passengers, round(earliest, 2), round(latest, 2), round(max_ride_time, 2)])

    drop_out = []
    for i in range(len(requests)):
        # make output for pick up stops
        # convert time windows
        earliest = (requests[i].earl_arr_time.get_in_seconds() - (conversion_value * 60)) / 60
        latest = (requests[i].latest_arr_time.get_in_seconds() - (conversion_value * 60)) / 60
        max_ride_time = (requests[i].latest_arr_time - requests[i].latest_start_time).get_in_seconds() / 60

        drop_out.append(
            [i + 1 + len(requests), Global.TRANSFER_SECONDS / 60, -requests[i].number_of_passengers, round(earliest, 2), round(latest, 2), round(max_ride_time, 2)])

    all_out = pick_out + drop_out
    all_out.append(depot_out_last)
    all_out.insert(0,depot_out_first)
    all_out.insert(0, first_out)

    #write file to output
    with open(output_path + "/" + name + ".txt", 'w') as f:
        for sublist in all_out:
            # Join each sublist's values with a space and write to file
            f.write(" ".join(map(str, sublist)) + "\n")


def convert(path_to_config):
    with open(path_to_config, 'r') as config_file:
        config: dict = json.load(config_file)

    Global.AVERAGE_KMH = config.get('averageKmH')
    Global.KM_PER_UNIT = config.get('KmPerUnit')
    Global.COST_PER_KM = config.get('costPerKM')
    Global.CO2_PER_KM = config.get('co2PerKM')
    Global.CAPACITY_PER_LINE = config.get('capacityPerLine')
    Global.NUMBER_OF_EXTRA_TRANSFERS = config.get('numberOfExtraTransfers')
    Global.MAX_DELAY_EQUATION = config.get('maxDelayEquation')
    Global.TRANSFER_SECONDS = config.get('transferMinutes') * 60
    Global.TIME_WINDOW_SECONDS = config.get('timeWindowMinutes') * 60
    Global.CPLEX_PATH = config.get('pathCPLEX')

    request_files_path: str = config.get('pathRequestFile')
    network_path: str = config.get('pathNetworkFile')
    output_path: str = config.get('outputPath')

    network: List[Bus] = read_bus_network(network_path)
    lines = list({x.line for x in network})
    network_graph = LineGraph(network)

    req_folder = Path(request_files_path)
    for req_file in req_folder.iterdir():
        if req_file.is_file():
            name = req_file.name.split(".")[0]
            requests: List[Request] = sorted(read_requests(str(req_file), network_graph), key=lambda k: k.id)

            createDistanceFile(requests, lines[0].depot, output_path, name)
            createRequestFile(requests, network, output_path, name)


convert("../../input/config.json")