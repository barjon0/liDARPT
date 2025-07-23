"""
© 2025 Jonas Barth

This file is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0).

You may share and adapt the material for non-commercial use, provided you give appropriate credit,
indicate if changes were made, and distribute your contributions under the same license.

License: https://creativecommons.org/licenses/by-nc-sa/4.0/

File: CplexModel.py
Description: Builds CPLEX model via python API from event graph
"""
import time
import cplex
from typing import Set, List, Tuple, Dict
from utils import Global, Timer
from models.Demand import Request, SplitRequest
from utils.EventGraph import EventGraph, IdleEvent, PickUpEvent, Event
from models.Network import Bus, Line
from models.Plan import RouteStop, Route


class CplexSolver:
    """
    Class that builds Cplex model from eventgraph, set of requests and buses.
    """

    def __init__(self, event_graph: EventGraph, requests: Set[Request], bus_list: List[Bus]):
        self.event_graph = event_graph
        self.requests = requests
        self.buses = bus_list
        self.multi_objective = False  # enables two solves with separate objectives if True
        self.model = self.build_model()

    def build_model(self):
        """
        Builds Cplex model
        :return: python cplex class
        """
        model = cplex.Cplex()
        # add variables
        # q_r for every request, acceptance variable
        model.variables.add(names=[f'q_{x.id}' for x in self.requests],
                            types=[model.variables.type.binary] * len(self.requests))

        # z_i for route option selection
        for req in self.requests:
            for key in req.split_requests.keys():
                model.variables.add(names=[f'z_{req.id},{key}'], types=[model.variables.type.binary])

        # B_e for every split request (shared B_e variables) -> relative based on lower bound
        for key in self.event_graph.request_dict:
            variable_args = [{"names": [f"B_{key.split_id}+"], "lb": [Global.TRANSFER_SECONDS],
                              "ub": [
                                  key.latest_start_time.get_in_seconds() - key.earl_start_time.get_in_seconds() + Global.TRANSFER_SECONDS]},
                             {"names": [f"B_{key.split_id}-"], "lb": [Global.TRANSFER_SECONDS],
                              "ub": [
                                  key.latest_arr_time.get_in_seconds() - key.earl_arr_time.get_in_seconds() + Global.TRANSFER_SECONDS]}]

            model.variables.add(**variable_args[0])
            model.variables.add(**variable_args[1])

        # x_a for every edge
        for first in self.event_graph.edge_dict:
            for second in self.event_graph.edge_dict[first][1]:
                model.variables.add(names=[f'x_{first.id},{second.id}'], types=[model.variables.type.binary])

        lines = {x.line for x in self.buses}

        if self.multi_objective:
            # maximize number of requests first
            model.objective.set_sense(model.objective.sense.maximize)
            obj_pairs = [(f"q_{x.id}", 1) for x in self.requests]

            model.objective.set_linear(obj_pairs)

        else:
            # minimize weighted objective function
            model.objective.set_sense(model.objective.sense.minimize)
            penalty = (int(2 * calc_total_network_size(lines)) * len(self.requests)) + 1
            obj_pairs = [(f"q_{x.id}", -penalty) for x in self.requests]
            for first_event in self.event_graph.edge_dict.keys():
                for second_event in self.event_graph.edge_dict[first_event][1]:
                    obj_pairs += [(f"x_{first_event.id},{second_event.id}",
                                   first_event.location.calc_distance(second_event.location))]

            model.objective.set_linear(obj_pairs)

        # set up constraints:
        # for all events: sum out - sum in = 0
        for key in self.event_graph.edge_dict.keys():
            var_names = [f'x_{x.id},{key.id}' for x in self.event_graph.edge_dict[key][0]] \
                        + [f'x_{key.id},{x.id}' for x in self.event_graph.edge_dict[key][1]]

            coeffs = [1] * len(self.event_graph.edge_dict[key][0]) + [-1] * len(self.event_graph.edge_dict[key][1])
            model.linear_constraints.add(
                lin_expr=[cplex.SparsePair(ind=var_names, val=coeffs)],
                senses=["E"],
                rhs=[0]
            )

        # for all split_options: sum of incoming edges x_a to first event >= z_i
        for req in self.requests:
            for option in req.split_requests:
                for split_req in req.split_requests[option]:
                    var_names = []
                    for event in self.event_graph.request_dict[split_req][0]:
                        var_names += [f"x_{x.id},{event.id}" for x in self.event_graph.edge_dict[event][0]]
                    var_names += [f"z_{req.id},{option}"]
                    coeffs = [1] * (len(var_names) - 1) + [-1]
                    model.linear_constraints.add(
                        lin_expr=[cplex.SparsePair(ind=var_names, val=coeffs)],
                        senses=["G"],
                        rhs=[0]
                    )

        # for line: sum of outgoing from idle event <= number of buses
        for line in lines:
            amount = sum(1 for x in self.buses if x.line == line)
            idle_event = next(
                iter(x for x in self.event_graph.edge_dict.keys() if isinstance(x, IdleEvent) and x.line == line))

            var_names = [f"x_{idle_event.id},{x.id}" for x in self.event_graph.edge_dict[idle_event][1]]
            model.linear_constraints.add(
                lin_expr=[cplex.SparsePair(ind=var_names, val=[1] * len(var_names))],
                senses=["L"],
                rhs=[amount]
            )

        # add timing constraints for every bus from and to idle event (earliest start and latest arrival time of buses)
        for line in lines:
            idle_event = next(
                iter(x for x in self.event_graph.edge_dict.keys() if isinstance(x, IdleEvent) and x.line == line))

            # check incoming edges / previous event was drop-off (enforces earliest start time of bus)
            var_dict: Dict[SplitRequest, List[str]] = {}
            for sub_event in self.event_graph.edge_dict[idle_event][0]:
                if sub_event.first in var_dict:
                    var_dict[sub_event.first] += [f"x_{sub_event.id},{idle_event.id}"]
                else:
                    var_dict[sub_event.first] = [f"x_{sub_event.id},{idle_event.id}"]

            for found_split in var_dict.keys():
                var_names = [f"B_{found_split.split_id}-"]
                duration = Timer.calc_time(found_split.drop_off_location.calc_distance(idle_event.location))
                coeffs = [duration] * len(var_dict[found_split]) + [1]
                model.linear_constraints.add(
                    lin_expr=[cplex.SparsePair(ind=var_dict[found_split] + var_names, val=coeffs)],
                    senses=["L"],
                    rhs=[line.end_time.get_in_seconds() - found_split.earl_arr_time.get_in_seconds()]
                )

            # check outgoing edges / start at idle_event (enforces latest arrival time of bus)
            for sub_event in self.event_graph.edge_dict[idle_event][1]:
                if sub_event.first in var_dict:
                    var_dict[sub_event.first] += [f"x_{idle_event.id},{sub_event.id}"]
                else:
                    var_dict[sub_event.first] = [f"x_{idle_event.id},{sub_event.id}"]

            for found_split in var_dict.keys():
                var_names = [f"B_{found_split.split_id}+"]
                duration = Timer.calc_time(idle_event.location.calc_distance(found_split.pick_up_location))
                coeffs = [-duration] * len(var_dict[found_split]) + [1]
                model.linear_constraints.add(
                    lin_expr=[cplex.SparsePair(ind=var_dict[found_split] + var_names, val=coeffs)],
                    senses=["G"],
                    rhs=[
                        line.start_time.get_in_seconds() + Global.TRANSFER_SECONDS - found_split.earl_start_time.get_in_seconds()]
                )

        # make timing constraints for all subsequent splits in event_graph
        for split_req in self.event_graph.request_dict.keys():

            for i in {0, 1}:
                var_dict: Dict[
                    Tuple[SplitRequest, bool], List[str]] = {}  # dict of form: {(request.id, type): [var_names]}
                for req_event in self.event_graph.request_dict[split_req][i]:
                    for sub_event in self.event_graph.edge_dict[req_event][1]:
                        if not isinstance(sub_event, IdleEvent):
                            if isinstance(sub_event, PickUpEvent):
                                type_bool = True
                            else:
                                type_bool = False
                            poss_tuple = (sub_event.first, type_bool)

                            if poss_tuple in var_dict:
                                var_dict[poss_tuple] += [f"x_{req_event.id},{sub_event.id}"]
                            else:
                                var_dict[poss_tuple] = [f"x_{req_event.id},{sub_event.id}"]

                for found_tuple in var_dict.keys():
                    other_split, type_bool = found_tuple
                    var_names = []
                    bool_first: bool
                    low_bound_pred: float
                    up_bound_pred: float
                    low_bound_suc: float
                    if i == 0:
                        split_first_location = split_req.pick_up_location
                        var_names += [f"B_{split_req.split_id}+"]
                        low_bound_pred = split_req.earl_start_time.get_in_seconds()
                        up_bound_pred = split_req.latest_start_time.get_in_seconds()
                    else:
                        split_first_location = split_req.drop_off_location
                        var_names += [f"B_{split_req.split_id}-"]
                        low_bound_pred = split_req.earl_arr_time.get_in_seconds()
                        up_bound_pred = split_req.latest_arr_time.get_in_seconds()

                    if type_bool:
                        split_sec_location = other_split.pick_up_location
                        var_names += [f"B_{other_split.split_id}+"]
                        low_bound_suc = other_split.earl_start_time.get_in_seconds()
                    else:
                        split_sec_location = other_split.drop_off_location
                        var_names += [f"B_{other_split.split_id}-"]
                        low_bound_suc = other_split.earl_arr_time.get_in_seconds()

                    duration = Timer.calc_time(split_first_location.calc_distance(split_sec_location))
                    big_m = get_big_m(up_bound_pred, low_bound_suc, duration)
                    coeffs = [-big_m] * len(var_dict[found_tuple]) + [-1] + [1]

                    service_time = Global.TRANSFER_SECONDS * (int(bool(duration)))
                    model.linear_constraints.add(
                        lin_expr=[cplex.SparsePair(ind=var_dict[found_tuple] + var_names, val=coeffs)],
                        senses=["G"],
                        rhs=[service_time - big_m + duration + low_bound_pred - low_bound_suc]
                    )

        for req in self.requests:
            found_tuples = set()
            for key in req.split_requests.keys():
                start_split = req.split_requests[key][0]
                end_split = req.split_requests[key][-1]
                if (start_split, end_split) not in found_tuples:
                    found_tuples |= {(start_split, end_split)}
                    var_names = [f"B_{start_split.split_id}+"]
                    max_ride_time = (req.latest_arr_time - req.latest_start_time).get_in_seconds()

                    # max ride time constraint
                    model.linear_constraints.add(
                        lin_expr=[cplex.SparsePair(ind=var_names + [f"B_{end_split.split_id}-"], val=[-1, 1])],
                        senses=["L"],
                        rhs=[max_ride_time + start_split.earl_start_time.get_in_seconds()
                             - end_split.earl_arr_time.get_in_seconds()]
                    )

                # add timing constraint for subsequent split actions at same stop
                for i in range(0, len(req.split_requests[key]) - 1):
                    prev_split = req.split_requests[key][i]
                    sub_split = req.split_requests[key][i + 1]
                    var_names = [f"B_{prev_split.split_id}-", f"B_{sub_split.split_id}+", f"z_{req.id},{key}"]
                    sub_m = max(0, (prev_split.latest_arr_time - sub_split.earl_start_time).get_in_seconds())
                    model.linear_constraints.add(
                        lin_expr=[cplex.SparsePair(ind=var_names, val=[-1, 1, -sub_m])],
                        senses=["G"],
                        rhs=[prev_split.earl_arr_time - sub_split.earl_start_time.get_in_seconds() - sub_m]
                    )

            # z variables for request sum to p_r
            var_names = [f"z_{req.id},{x}" for x in req.split_requests.keys()] + [f"q_{req.id}"]
            coeffs = [1] * len(req.split_requests.keys()) + [-1]
            model.linear_constraints.add(
                lin_expr=[cplex.SparsePair(ind=var_names, val=coeffs)],
                senses=["E"],
                rhs=[0]
            )

        return model

    def solve_model(self):
        """
        Starts solve of the model with specific Cplex Parameters.
        """
        # self.model.parameters.randomseed.set(2)
        # self.model.write("model.lp")

        self.model.parameters.mip.tolerances.mipgap.set(0.0)
        self.model.parameters.threads.set(31)  # specify number of threads
        self.model.parameters.workmem.set(27000)  # Up to 27 GB of RAM
        if self.multi_objective:
            self.model.parameters.timelimit.set(600)
        else:
            self.model.parameters.timelimit.set(900)

        # self.model.parameters.emphasis.mip.set(3)

        self.model.parameters.mip.strategy.nodeselect.set(
            2)  # (check 1-3)select strategy for selecting node for branching
        self.model.parameters.mip.strategy.variableselect.set(
            0)  # (check 0 /-1 - 4) select on which variable to branch on

        self.model.parameters.mip.strategy.lbheur.set(0)  # check(0,1)local branching heuristic
        self.model.parameters.mip.strategy.heuristicfreq.set(0)  # (check 0/-1) disable use of heuristic
        self.model.parameters.mip.strategy.rinsheur.set(0)  # 50 = apply every 50 nodes
        self.model.parameters.preprocessing.presolve.set(1)  # decide if presolve heuristic is used
        self.model.parameters.preprocessing.numpass.set(-1)  # check(-1, 0) limits number of presolves
        # self.model.parameters.mip.strategy.presolvenode.set(2) # check(0, -1, 3) decides if presolve at node

        # self.model.parameters.mip.cuts.nodecuts.set(3)
        # self.model.parameters.mip.cuts.flowcovers.set(2)
        self.model.parameters.mip.cuts.gomory.set(2)
        # self.model.parameters.mip.cuts.mircut.set(2)
        # self.model.parameters.mip.cuts.implied.set(-1)
        # self.model.parameters.mip.cuts.localimplied.set(-1)
        # self.model.parameters.mip.cuts.disjunctive.set(2)  # check(0 -1 - 3) choose to use more aggressive cuts

        self.model.parameters.mip.display.set(3)  # set extent of logging

        var_names = self.model.variables.get_names()
        var_names_set = set(var_names)
        if len(var_names) != len(var_names_set):
            print("There are duplicate variable names")

        self.model.solve()

        print("Objective Value: " + str(self.model.solution.get_objective_value()))
        Global.INTEGRALITY_GAP_FIRST = int(self.model.solution.MIP.get_mip_relative_gap() * 100)

        Global.COMPUTATION_TIME_SOLVING_FIRST = round(time.time() - Global.COMPUTATION_START_TIME, 4)
        print(f"Solved model after {Global.COMPUTATION_TIME_SOLVING_FIRST} seconds")
        Global.COMPUTATION_START_TIME = time.time()

        if self.multi_objective:
            # solve again with minimizing travel time
            req_vars = [f"q_{x.id}" for x in self.requests]
            value = sum(self.model.solution.get_values(req_vars))
            self.model.linear_constraints.add(
                lin_expr=[cplex.SparsePair(ind=req_vars, val=[1] * len(self.requests))],
                senses=["G"],
                rhs=[value * 0.99999]
            )

            self.model.parameters.mip.tolerances.mipgap.set(0.0)
            self.model.parameters.timelimit.set(900 - int(Global.COMPUTATION_TIME_SOLVING_FIRST))

            # self.model.parameters.mip.strategy.nodeselect.set(2)
            # self.model.parameters.mip.strategy.lbheur.set(1)
            # self.model.parameters.mip.strategy.rinsheur.set(50)
            # self.model.parameters.mip.cuts.gomory.set(2)
            # self.model.parameters.mip.cuts.flowcovers.set(2)

            self.model.objective.set_sense(self.model.objective.sense.minimize)
            # reset obj function
            self.model.objective.set_linear([(f"q_{x.id}", 0) for x in self.requests])
            obj_pairs = []
            for first_event in self.event_graph.edge_dict.keys():
                for second_event in self.event_graph.edge_dict[first_event][1]:
                    obj_pairs += [(f"x_{first_event.id},{second_event.id}",
                                   first_event.location.calc_distance(second_event.location))]

            self.model.objective.set_linear(obj_pairs)
            self.model.solve()

            Global.INTEGRALITY_GAP_SECOND = int(self.model.solution.MIP.get_mip_relative_gap() * 100)

        Global.COMPUTATION_TIME_SOLVING_SECOND = round(time.time() - Global.COMPUTATION_START_TIME, 4)
        print(f"Solved model after {Global.COMPUTATION_TIME_SOLVING_SECOND} seconds")
        Global.COMPUTATION_START_TIME = time.time()

    def convert_to_plan(self):
        """
        Retrieves Cplex Solution values and builds Bus routes.
        Postprocessing required to disregard unnecessarily selected events.
        :return: list of bus routes
        """
        # for every bus -> start at idle_event and walk along path
        processed_pick_up: Set[SplitRequest] = set()
        processed_drop_off: Set[SplitRequest] = set()
        request_order = list(self.requests)
        # arc_names = []
        solution_ints = self.model.solution.get_values([f"q_{x.id}" for x in request_order])
        combi = []
        for i in range(len(request_order)):
            combi.append(f"Request: {request_order[i].id} has value {solution_ints[i]}")

        line_set: Set[Line] = {x.line for x in self.buses}
        line_bus_dict: Dict[Line, List[Bus]] = {x: [y for y in self.buses if y.line == x] for x in line_set}
        all_plans: List[Route] = []

        for line in line_bus_dict.keys():
            prev_visited = {}  # stores events that are visited multiple times (and amount)
            idle_event: IdleEvent = next(
                iter(x for x in self.event_graph.edge_dict.keys() if isinstance(x, IdleEvent) and x.line == line))
            sub_names = [f"x_{idle_event.id},{x.id}" for x in self.event_graph.edge_dict[idle_event][1]]
            edge_vals = self.model.solution.get_values(sub_names)
            round_edge_vals = [round(x) for x in edge_vals]

            # for each bus on line
            for i in range(len(line_bus_dict[line])):
                bus = line_bus_dict[line][i]
                bus_plan = Route(bus)

                # loop over edge_val with j, for every bus 1 found incr. counter, until counter == i
                counter = -1  # counter for amount of 1s already found
                j = -1  # j iterates over edge values
                while counter < i and j < len(round_edge_vals) - 1:  # if
                    j += 1
                    if round_edge_vals[j] == 1:
                        counter += 1
                # if counter is smaller then i => no 1 found so bus just stays in place
                if counter < i:
                    bus_plan.stop_list.append(
                        RouteStop(idle_event.location, bus.line.start_time, bus.line.end_time, bus))
                else:
                    curr_route_stop = RouteStop(idle_event.location, bus.line.start_time,
                                                bus.line.start_time, bus)
                    bus_plan.stop_list.append(curr_route_stop)

                    next_event = get_next_event(idle_event, self.event_graph.edge_dict, self.model.solution,
                                                prev_visited)

                    while next_event is not idle_event:
                        # check selected option for request -> if event fits with option:
                        z_options = list(next_event.first.parent.split_requests.keys())
                        z_options_vals = self.model.solution.get_values(
                            [f"z_{next_event.first.id},{x}" for x in z_options])
                        z_options_vals_round = [round(x) for x in z_options_vals]

                        if 1 in z_options_vals_round and next_event.first in next_event.first.parent.split_requests[
                            z_options[z_options_vals_round.index(1)]]:

                            if next_event.location != curr_route_stop.stop:

                                duration = Timer.calc_time(
                                    curr_route_stop.stop.calc_distance(next_event.location))
                                if isinstance(next_event, PickUpEvent):
                                    if next_event.first not in processed_pick_up:
                                        time_var = round(
                                            self.model.solution.get_values(f"B_{next_event.first.split_id}+"))
                                        curr_route_stop = RouteStop(next_event.location,
                                                                    curr_route_stop.depart_time.add_seconds(duration),
                                                                    Timer.create_time_object(
                                                                        time_var + next_event.first.earl_start_time.get_in_seconds()),
                                                                    bus)
                                        bus_plan.stop_list.append(curr_route_stop)
                                        curr_route_stop.pick_up.add(next_event.first.parent)
                                        processed_pick_up.add(next_event.first)
                                    else:
                                        print(f"Double serviced request removed: {next_event}")
                                else:
                                    if next_event.first not in processed_drop_off:
                                        time_var = round(
                                            self.model.solution.get_values(f"B_{next_event.first.split_id}-"))
                                        curr_route_stop = RouteStop(next_event.location,
                                                                    curr_route_stop.depart_time.add_seconds(duration),
                                                                    Timer.create_time_object(time_var
                                                                    + next_event.first.earl_arr_time.get_in_seconds()),
                                                                    bus)
                                        bus_plan.stop_list.append(curr_route_stop)
                                        curr_route_stop.drop_off.add(next_event.first.parent)
                                        processed_drop_off.add(next_event.first)
                                    else:
                                        print(f"Double serviced request removed: {next_event}")
                            else:
                                if isinstance(next_event, PickUpEvent):
                                    if next_event.first not in processed_pick_up:
                                        time_var = (round(
                                            self.model.solution.get_values(f"B_{next_event.first.split_id}+"))
                                                    + next_event.first.earl_start_time.get_in_seconds())
                                        curr_route_stop.pick_up.add(next_event.first.parent)
                                        processed_pick_up.add(next_event.first)
                                    else:
                                        print(f"Double serviced request removed: {next_event}")
                                else:
                                    if next_event.first not in processed_drop_off:
                                        time_var = (self.model.solution.get_values(f"B_{next_event.first.split_id}-")
                                                    + next_event.first.earl_arr_time.get_in_seconds())
                                        curr_route_stop.drop_off.add(next_event.first.parent)
                                        processed_drop_off.add(next_event.first)
                                    else:
                                        print(f"Double serviced request removed: {next_event}")

                                curr_route_stop.depart_time = Timer.create_time_object(time_var)
                        else:
                            print(f"Unnecessary event removed: {next_event}")

                        next_event = get_next_event(next_event, self.event_graph.edge_dict, self.model.solution,
                                                    prev_visited)

                    # handle final idle_event stop
                    if curr_route_stop.stop == bus.line.depot:
                        curr_route_stop.depart_time = bus.line.end_time
                    else:
                        duration = Timer.calc_time(curr_route_stop.stop.calc_distance(next_event.location))
                        bus_plan.stop_list.append(
                            RouteStop(next_event.location, curr_route_stop.depart_time.add_seconds(duration),
                                      bus.line.end_time, bus))
                    if len(bus_plan.stop_list) > 1:
                        duration = Timer.create_time_object(Timer.calc_time(
                            bus_plan.stop_list[0].stop.calc_distance(bus_plan.stop_list[1].stop)))
                        bus_plan.stop_list[0].depart_time = (bus_plan.stop_list[1].arriv_time - duration)
                all_plans.append(bus_plan)

        return all_plans


def get_next_event(prev_event: Event, edge_dict: dict, solution, prev_visited: dict):
    """
    Find next event from current event and activated edges.
    Can be problematic if multiple bus tours choose the same event. Store number of times an event is visited overall.
    :param prev_event: current event
    :param edge_dict: dictionary representing event graph
    :param solution: cplex solution
    :param prev_visited: dictionary of already visited events
    :return: next event
    """
    sub_names = [f"x_{prev_event.id},{x.id}" for x in edge_dict[prev_event][1]]
    edge_vals = solution.get_values(sub_names)
    next_round_edge_vals = [round(x) for x in edge_vals]
    indices = [i for i, val in enumerate(next_round_edge_vals) if val == 1]

    number_visited = 0
    if len(indices) > 1:
        if prev_event in prev_visited:
            number_visited = prev_visited[prev_event]
            prev_visited[prev_event] += 1
        else:
            prev_visited[prev_event] = 1

    next_event_idx = indices[number_visited]
    next_event = edge_dict[prev_event][1][next_event_idx]

    return next_event


def calc_total_network_size(line_set: Set[Line]):
    total_sum = 0
    for line in line_set:
        for i in range(len(line.stops) - 1):
            total_sum += line.stops[i].calc_distance(line.stops[i + 1])

    return total_sum


def get_big_m(pred_up_bound: float, suc_low_bound: float, duration: float):
    return pred_up_bound - suc_low_bound + duration + Global.TRANSFER_SECONDS
