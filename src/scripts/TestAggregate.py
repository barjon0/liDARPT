"""
Script to generate pyplot-plots from DARP and liDARPT solutions
"""

import json
from pathlib import Path
from typing import Dict, List
import re

from matplotlib import pyplot as plt

from models.Network import Stop
from utils import Timer
from utils.Timer import TimeImpl

translate_km = {"markt-karl": 2, "markt-karl-lohr": 2, "sw-geo_2": 3, "sw-geo_full": 3, "sw-schlee_2": 1.5, "sw-schlee_3": 1.5, "sw-schlee_full": 1.5}
translate_speed = {"markt-karl": 65.0, "markt-karl-lohr": 65.0, "sw-geo_2": 70.0, "sw-geo_full": 70.0, "sw-schlee_2": 65.0, "sw-schlee_3": 65.0, "sw-schlee_full": 65.0}

def add_to_dict(network_name, number_requests, time_span, method, val, val_dict):
    if network_name in val_dict:
        if (number_requests, time_span) in val_dict[network_name]:
            if method in val_dict[network_name][(number_requests, time_span)]:
                val_dict[network_name][(number_requests, time_span)][method] += [val]
            else:
                val_dict[network_name][(number_requests, time_span)][method] = [val]
        else:
            val_dict[network_name][(number_requests, time_span)] = {method: [val]}
    else:
        val_dict[network_name] = {(number_requests, time_span): {method: [val]}}

#def calc_dist(stop1, stop2, un):
#    unit_dist = math.sqrt(
 #       (stop2.coordinates[0] - stop1.coordinates[0]) ** 2 + (stop2.coordinates[1] - stop1.coordinates[1]) ** 2)
 #   return unit_dist * un
"""
def calculate_km_booked_instance(network_name: str, req_file_lines: List[str]):
    network_path = "../../input/bus_networks/real_networks/"
    network_file_path = network_path + network_name + ".json"
    with open(network_file_path, 'r') as network_file:
        network_dict: dict = json.load(network_file)

    stops: Dict[int, Stop] = {}
    stop_list = network_dict.get('stops')
    for single_stop in stop_list:
        stops[single_stop["id"]] = Stop(single_stop["id"], tuple(single_stop["coordinates"]))

    km_booked = 0
    for req_line in req_file_lines[1:]:
        # Split by commas not inside brackets or quotes
        idx_1 = req_line.rfind("[")
        idx_2 = req_line.rfind("]")
        if idx_1 != -1:
            enc = req_line[idx_1 + 1:idx_2].split(", ")
            km_booked += calc_dist(stops[int(enc[0])], stops[int(enc[-1])], translate_km[network_name])

    return km_booked
    """

def vehUtil_perInst(parent_folder: Path, val_dict: dict, overall_lines: List[str], req_lines: List[str],
                          bus_names: List[str]):
    network_name = str(parent_folder).split("\\")[-3]
    time_span = int(parent_folder.name[1])
    number_req = len(req_lines) - 1

    acc_time_travel = calculate_acc_km_req(network_name, time_span, number_req, req_lines)

    interesting_lines = [x for x in overall_lines if "km travelled total:" in x]
    km_travel_total = float(interesting_lines[0].split(" ")[-1])

    time_travel_total = km_travel_total * 60 / translate_speed[network_name]

    add_to_dict(network_name, number_req, time_span, True, acc_time_travel / time_travel_total, val_dict)



def calculate_acc_km_req(network_name: str, time_span: int, number_req: int, req_file_lines_out: List[str]):
    request_path = "../../input/requests/random_requests/"
    folder_name: str
    if time_span == 3:
        folder_name = "short_window"
    elif time_span == 6:
        folder_name = "medium_window"
    elif time_span == 9:
        folder_name = "long_window"
    else:
        raise ValueError

    number_stops: int
    network_path = "../../input/bus_networks/real_networks/"
    network_file_path = network_path + network_name + ".json"
    with open(network_file_path, 'r') as network_file:
        network_dict: dict = json.load(network_file)
    number_stops = len(network_dict.get("stops"))

    request_file_path = request_path + network_name +"/" + folder_name + "/L" \
                        + str(time_span) + "-" + str(number_stops) + "-" + str(number_req) + ".csv"
    with open(request_file_path, 'r') as req_file:
        r_lines = req_file.readlines()

    req_to_pass_dict: dict = {}
    for i in range(1, len(r_lines)):
        split_up = r_lines[i].split(",")
        req_to_pass_dict[int(split_up[0])] = int(split_up[-1])

    time_driven = 0
    for idx in range(1, len(req_file_lines_out)):
        # Split by commas not inside brackets or quotes
        split_up = req_file_lines_out[idx].split(",")
        travel_time = split_up[len(split_up) - 3]
        if travel_time != "-":
            time_driven += req_to_pass_dict[idx - 1] * float(travel_time)
    return time_driven

def average_delay(parent_folder: Path, val_dict: dict, overall_lines: List[str], req_lines: List[str],
                          bus_names: List[str]):
    network_name = str(parent_folder).split("\\")[-3]
    time_span = float(parent_folder.name[1])
    number_req = len(req_lines) - 1

    #interesting_lines = [x for x in overall_lines if "km travelled total:" in x]
    #val = float(interesting_lines[0].split(" ")[-1]) *

    avg_delay = 0
    i = 0
    for r_line in req_lines[1:]:
        buf = r_line.split(",")
        wait_time = buf[-4]
        ride_time = buf[-3]
        short_time = buf[-2]
        if wait_time != "-":
            i += 1
            avg_delay += ((float(wait_time) + float(ride_time)) - float(short_time)) * 100 / float(short_time)

    add_to_dict(network_name, number_req, time_span, True, avg_delay / float(i), val_dict)

def get_time_window_length(bus_files: List[str], parent_folder: Path):
    if len(bus_files) > 0:

        earl_time = TimeImpl(23, 59)
        latest_time = TimeImpl(0, 0)
        for b_name in bus_files:
            b_file = parent_folder / b_name
            b_f = b_file.open("r", encoding="utf-8")
            b_lines = b_f.readlines()

            if len(b_lines) > 3:
                first_stop = b_lines[3]
                first_data = first_stop.split(",")
                start_time = Timer.conv_string_2_time(first_data[2])
                if start_time < earl_time:
                    earl_time = start_time

                last_line = b_lines[-2]
                last_data = last_line.split(",")
                end_time = Timer.conv_string_2_time(last_data[3])
                if end_time > latest_time:
                    latest_time = end_time
            b_f.close()

        duration = (latest_time - earl_time).get_in_seconds() / 3600

        return duration

def requests_to_efficiency(parent_folder: Path, val_dict: dict, overall_lines: List[str], req_lines: List[str],
                          bus_names: List[str], limit: int):
    network_name = str(parent_folder).split("/")[-3]
    time_span = float(parent_folder.name[1])
    number_req = len(req_lines) - 1
    '''
    empty_line = [x for x in overall_lines if "empty km total:" in x]
    empty_km = float(empty_line[0].split(" ")[-1])
    total_line = [x for x in overall_lines if "km travelled total:" in x]
    total_km = float(total_line[0].split(" ")[-1])
    share = empty_km / total_km
    '''
    interesting_lines = [x for x in overall_lines if "computation time" in x]
    comp_time = 0
    for t in interesting_lines[3:]:
        comp_time += Timer.conv_string_2_time(t.split(" ")[-1]).get_in_seconds()

    some_line = [x for x in overall_lines if "Event Graph Edges" in x]
    edges = int(get_val(some_line))

    some_line2 = [x for x in overall_lines if "Event Graph Nodes" in x]
    nodes = int(get_val(some_line2))

    if limit >= number_req:
        add_to_dict(network_name, number_req, time_span, True, (nodes, edges, comp_time), val_dict)


def event_graph_to_comp_time(parent_folder: Path, val_dict: dict, overall_lines: List[str], req_lines: List[str], bus_names: List[str]):
    network_name = str(parent_folder).split("/")[-3]
    interesting_lines = [x for x in overall_lines if "Event Graph Nodes:" in x]
    nNodes = int(interesting_lines[0].split(" ")[-1])

    int_line2 = [x for x in overall_lines if "Event Graph Edges:" in x]
    edges = int(int_line2[0].split(" ")[-1])

    interesting_lines = [x for x in overall_lines if "computation time" in x]
    comp_time = 0
    for t in interesting_lines:
        comp_time += Timer.conv_string_2_time(t.split(" ")[-1]).get_in_seconds()

    add_to_dict(network_name, nNodes, edges, comp_time, val_dict)

def get_val(lines: List[str]):
    return lines[0].split(" ")[-1]

def read_DARP(parent_folder: Path, val_dict: dict, overall_lines: List[str], file_name: str):
    sys_eff_line = [x for x in overall_lines if "System efficiency" in x]

    if "-nan" not in get_val(sys_eff_line):
        network_name = str(parent_folder).split("\\")[-2]
        time_span = float(file_name[1])
        number_req_line = [x for x in overall_lines if "Number of requests" in x]
        number_req = int(number_req_line[0].split(" ")[-1])

        interest_line = [x for x in overall_lines if "CPLEX Gap" in x]
        val = float(interest_line[0].split(" ")[-1]) * 100

        interest_line2 = [x for x in overall_lines if "EntireModel time (ms)" in x]
        val2 = float(interest_line[0].split(" ")[-1]) / 1000.0

        if val > 0 and val < 900:
            print("something stinks here")

        #acc_per = (number_req - val) * 100 / float(number_req)

        #per = (number_req - val) * 100 / float(number_req)
        #sys_eff = float(get_val(sys_eff_line)[0:-2])

        add_to_dict(network_name, number_req, time_span, False, val, val_dict)


def rec_check_folder(folder: Path, val_dict: Dict[str, Dict[int, List[float]]], duration: int, limit: int):
    files = list()
    for item in folder.iterdir():
        if item.is_dir():
            rec_check_folder(item, val_dict, duration, limit)
        if item.is_file():
            files.append(item.name)

    bus_files = [x for x in files if re.match("bus_.*", x)]
    overall_file = [x for x in files if x == "overall_out.csv"]
    request_file = [x for x in files if x == "requests_out.csv"]

    if len(overall_file) > 0:
        o_file = folder / overall_file[0]
        o_f = o_file.open("r", encoding="utf-8")
        o_lines = o_f.readlines()
        o_f.close()

        r_file = folder / request_file[0]
        r_f = r_file.open("r", encoding="utf-8")
        r_lines = r_f.readlines()
        r_f.close()
        print(folder)
        if duration is None or int(folder.name[1]) == duration:
           requests_to_efficiency(folder, val_dict, o_lines, r_lines, bus_files, limit)

def rec_check_folder_DARP(parent_folder, val_dict, duration):
    files = list()
    for item in parent_folder.iterdir():
        if item.is_dir():
            rec_check_folder_DARP(item, val_dict, duration)
        if item.is_file():
            files.append(item.name)

    for file in files:
        o_file = parent_folder / file
        o_f = o_file.open("r", encoding="utf-8")
        o_lines = o_f.readlines()
        o_f.close()

        if duration is None or int(file[1]) == duration:
            read_DARP(parent_folder, val_dict, o_lines, file)

# method receives path to folder root -> searches all subdirectories, looking for overall/request file -> extracts some value and makes plots
def aggregate_tests(folder_path: str, figure,  limit: int, duration: int=None):
    root_folder = Path(folder_path)
    val_dict = {}

    rec_check_folder(root_folder, val_dict, duration, limit)
    #rec_check_folder_DARP(root_folder, val_dict, duration)
    count = 0
    sum_all = 0

    short_colors = ['b', 'g', 'r', 'c', 'm', 'y', 'k', 'w']
    i = 0

    x = list()
    y = list()
    z = list()
    n_list = sorted(list(val_dict.keys()))
    for key in n_list:
        key_list = sorted(list(val_dict[key].keys()), key=lambda x: x[0])
        for val in key_list:
            #if val_dict[key][val][0] > sumAll:
            #    sumAll = val_dict[key][val][0]
            x.append(val_dict[key][val][True][0][0])
            y.append(val_dict[key][val][True][0][1])
            z.append(val_dict[key][val][True][0][2])
    sc = ax.scatter(x, y, c=z, cmap='viridis')
    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label('seconds')
    #print("number instances: " + str(sumAll))
    """
    for network in val_dict.keys():
        x = list()
        y = list()
        all_ident = sorted(list(val_dict[network].keys()), key=lambda x: x[0])
        for ident in all_ident:
            for method in val_dict[network][ident].keys():
                summed = sum(val_dict[network][ident][method])
                res = summed / float(len(val_dict[network][ident][method]))
                y.append(res)
                sum_all += res
                x.append(ident[0])
                count += 1
                #print(network + " " + str(ident) + " " + str(res))
                #if res > sum_all:
                #    sum_all = res
        figure.plot(x, y, 'o', color=short_colors[i], label=network)
        #figure.plot(x, y, marker='o', linestyle="-", color=short_colors[i], label=network)
        i += 1
    print(f"Counted {count} instances that have optimal solutions, Avg was: {sum_all / count}")
    """

# method receives path to folder root -> searches all subdirectories, looking for overall/request file -> extracts some value and makes plots
"""
def aggregate_difference(folder_path_1: str, folder_path_DARP: str, figure, duration: int = None):
    root_folder_1 = Path(folder_path_1)
    val_dict = {}

    rec_check_folder(root_folder_1, val_dict, duration)

    root_folder_DARP = Path(folder_path_DARP)
    rec_check_folder_DARP(root_folder_DARP, val_dict, duration)

    short_colors = ['b', 'g', 'r', 'c', 'm', 'y', 'k', 'w']
    i = 0
    count = 0
    count_all = 0
    sum_all = 0

    # val_dict:[network_name, [number requests, List[value]]]
    for network in val_dict.keys():
        x = list()
        y = list()
        #request_numbers = sorted(list(val_dict[network].keys()))
        for tup in val_dict[network].keys():
            if len(val_dict[network][tup].keys()) > 1 and (len(val_dict[network][tup][True]) > 0 \
                    and len(val_dict[network][tup][False]) > 0):
                sum_li = sum(val_dict[network][tup][True])
                sum_darp = sum(val_dict[network][tup][False])
                sum_li = sum_li / float(len(val_dict[network][tup][True]))
                sum_darp = sum_darp / float(len(val_dict[network][tup][False]))
                x.append(tup[0] / tup[1])
                res = sum_li - sum_darp
                y.append(res)
                count_all += 1
                if res > sum_all:
                    count += 1
                    sum_all = res

        figure.plot(x, y, 'o', color=short_colors[i], label=network)
        i += 1
    print(f"Counted {count} instances that were faster, Average was: {sum_all / float(count)}")
    print(f"overall number of instances: {count_all}")
    """

def average_networks(path: str, duration: int):
    root_folder = Path(path)
    val_dict = {}

    rec_check_folder(root_folder, val_dict, duration, 100)

    first = list(val_dict.keys())[0]
    avg_dict = {x: 0 for x in val_dict[first].keys()}
    for network in val_dict.keys():
        for instance in val_dict[network]:
            entries = val_dict[network][instance][True]
            if len(entries) == 3:
                if len(set(entries)) != 1:
                    raise ValueError("There are different number of events")
                avg_dict[instance] += sum(entries) / 3.0
            else:
                print(f"Missing: Instance {instance} for network {network}")

    for key in avg_dict:
        print(f"For {key[0]} requests, average is: {avg_dict[key] / 5.0}")



def find_output_path(base_output_path: str):
    max_number = 0
    out_folder = Path(base_output_path)
    for item in out_folder.iterdir():
        if item.is_file() and "agg_plots_" in item.name:
            index = int(item.name.split(".")[0].split("_")[-1])
            if index > max_number:
                max_number = index

    result_path = f"{base_output_path}/agg_plots_{max_number + 1}.pdf"

    return result_path

fig, ax = plt.subplots()
ax.set_ylim(1, 10**6)

#ax.axhline(y=1.0, color='gray', linestyle='--', linewidth=1)
ax.set_yscale('log')
ax.set_xscale('log')

#aggregate_difference("../output/liDARPT", "../output/DARP", ax, None)
aggregate_tests("../../output/liDARPT", ax, 100, None)

#average_networks("../../output/liDARPT", 3)

#ax.set_xlabel("Temporal Density")
ax.set_xlabel("Number of Nodes")
ax.set_ylabel("Number of Edges")

y_limits = ax.get_ylim()
print("Y range:", y_limits)

#ax.legend(loc="lower right")
plt.savefig(find_output_path("../../output/agg_plots/new_plots"), bbox_inches='tight')
