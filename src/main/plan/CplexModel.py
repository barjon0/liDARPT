import time
import cplex
from typing import Set, List, Tuple, Dict

from utils import Global
from main.plan.TimeConstraints import RelativeConstraints
from utils.demand.AbstractRequest import Request, SplitRequest
from utils.helper import Helper, Timer
from utils.helper.EventGraph import EventGraph, IdleEvent, PickUpEvent
from utils.network.Bus import Bus
from utils.network.Line import Line
from utils.plan.Route import Route
from utils.plan.RouteStop import RouteStop


class CplexSolver:
    def __init__(self, event_graph: EventGraph, requests: Set[Request], bus_list: List[Bus]):
        self.event_graph = event_graph
        self.requests = requests
        self.buses = bus_list
        self.time_const_maker = RelativeConstraints()
        self.multi_objective = False
        self.model = self.build_model()

    def build_model(self):
        model = cplex.Cplex()
        # add variables
        # q_r for every request

        model.variables.add(names=[f'q_{x.id}' for x in self.requests],
                            types=[model.variables.type.binary] * len(self.requests))

        # z_i for route option
        for req in self.requests:
            for key in req.split_requests.keys():
                model.variables.add(names=[f'z_{req.id},{key}'], types=[model.variables.type.binary])

        # B_e for every split request (shared B_e variables) -> time of departure for split_request (drop-off/pick-up)
        for key in self.event_graph.request_dict:
            variable_args = self.time_const_maker.create_variables(key)
            model.variables.add(**variable_args[0])
            model.variables.add(**variable_args[1])

        # 2 * B_e per bus / not needed can actually infer from solution
        # for bus in self.buses:
        #    model.variables.add(names=[f'B_b{bus.id}+', f'B_b{bus.id}-'])

        # x_a for every edge
        for first in self.event_graph.edge_dict:
            for second in self.event_graph.edge_dict[first][1]:
                model.variables.add(names=[f'x_{first.id},{second.id}'], types=[model.variables.type.binary])

        lines = {x.line for x in self.buses}
        # set objective function: minimize distance covered but add penalty if request not accepted

        if self.multi_objective:
            model.objective.set_sense(model.objective.sense.maximize)
            obj_pairs = [(f"q_{x.id}", 1) for x in self.requests]

            model.objective.set_linear(obj_pairs)

        else:
            model.objective.set_sense(model.objective.sense.minimize)
            penalty = int(3 * Helper.calc_total_network_size(lines)) * len(self.requests)
            obj_pairs = [(f"q_{x.id}", -penalty) for x in self.requests]
            for first_event in self.event_graph.edge_dict.keys():
                for second_event in self.event_graph.edge_dict[first_event][1]:
                    obj_pairs += [(f"x_{first_event.id},{second_event.id}",
                                   Helper.calc_distance(first_event.location, second_event.location))]

            model.objective.set_linear(obj_pairs)

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

        # for line: sum of outgoing from idle <= number of buses
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

        # think about idle_events!!!
        # add timing constraints for every bus(idle_event)
        for line in lines:
            idle_event = next(
                iter(x for x in self.event_graph.edge_dict.keys() if isinstance(x, IdleEvent) and x.line == line))

            # check incoming edges / previous event was drop-off
            var_dict: Dict[SplitRequest, List[str]] = {}
            for sub_event in self.event_graph.edge_dict[idle_event][0]:
                if sub_event.first in var_dict:
                    var_dict[sub_event.first] += [f"x_{sub_event.id},{idle_event.id}"]
                else:
                    var_dict[sub_event.first] = [f"x_{sub_event.id},{idle_event.id}"]

            for found_split in var_dict.keys():
                var_names = [f"B_{found_split.split_id}-"]
                duration = Timer.calc_time(Helper.calc_distance(found_split.drop_off_location, idle_event.location))
                coeffs = [duration] * len(var_dict[found_split]) + [1]
                model.linear_constraints.add(
                    lin_expr=[cplex.SparsePair(ind=var_dict[found_split] + var_names, val=coeffs)],
                    senses=["L"],
                    rhs=[line.end_time.get_in_seconds() - self.time_const_maker.add_value(found_split, False)]
                )

            # check outgoing edges / start at idle_event
            for sub_event in self.event_graph.edge_dict[idle_event][1]:
                if sub_event.first in var_dict:
                    var_dict[sub_event.first] += [f"x_{idle_event.id},{sub_event.id}"]
                else:
                    var_dict[sub_event.first] = [f"x_{idle_event.id},{sub_event.id}"]

            for found_split in var_dict.keys():
                var_names = [f"B_{found_split.split_id}+"]
                duration = Timer.calc_time(Helper.calc_distance(idle_event.location, found_split.pick_up_location))
                coeffs = [-duration] * len(var_dict[found_split]) + [1]
                model.linear_constraints.add(
                    lin_expr=[cplex.SparsePair(ind=var_dict[found_split] + var_names, val=coeffs)],
                    senses=["G"],
                    rhs=[line.start_time.get_in_seconds() + Global.TRANSFER_SECONDS - self.time_const_maker.add_value(
                        found_split, True)]
                )

        # make timing constraints for all subsequent splits in event_graph...(for doc look into thesis)
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
                    bool_second: bool
                    if i == 0:
                        split_first_location = split_req.pick_up_location
                        var_names += [f"B_{split_req.split_id}+"]
                        bool_first = True
                    else:
                        split_first_location = split_req.drop_off_location
                        var_names += [f"B_{split_req.split_id}-"]
                        bool_first = False

                    if type_bool:
                        split_sec_location = other_split.pick_up_location
                        var_names += [f"B_{other_split.split_id}+"]
                        bool_second = True
                    else:
                        split_sec_location = other_split.drop_off_location
                        var_names += [f"B_{other_split.split_id}-"]
                        bool_second = False

                    duration = Timer.calc_time(Helper.calc_distance(split_first_location, split_sec_location))
                    big_m = self.time_const_maker.get_big_m(split_req, bool_first, duration,
                                                            self.time_const_maker.add_value(other_split, bool_second))
                    coeffs = [-big_m] * len(var_dict[found_tuple]) + [-1] + [1]

                    service_time = Global.TRANSFER_SECONDS * (int(bool(duration)))
                    model.linear_constraints.add(
                        lin_expr=[cplex.SparsePair(ind=var_dict[found_tuple] + var_names, val=coeffs)],
                        senses=["G"],
                        rhs=[service_time - big_m + duration + self.time_const_maker.add_value(split_req, bool_first)
                             - self.time_const_maker.add_value(other_split, bool_second)]
                    )
                    '''
                    # constraint for enforcing time window on first pick up splits, when picked up after others
                    if service_time == 0 and split_req.earl_start_time == split_req.parent.earl_start_time:
                        if bool_second:
                            diff_other = (other_split.latest_start_time - other_split.earl_start_time).get_in_minutes()
                        else:
                            diff_other = (other_split.latest_arr_time - other_split.earl_arr_time).get_in_minutes()

                        some_m = diff_other - split_req.latest_start_time.get_in_minutes() + self.time_const_maker.add_value(other_split, bool_second)
                        rhs = split_req.latest_start_time.get_in_minutes() + Global.TRANSFER_MINUTES + some_m - self.time_const_maker.add_value(other_split, bool_second)
                        vars_namen = var_dict[found_tuple] + var_names[:-1]
                        vals = [some_m]*len(var_dict[found_tuple]) + [1]

                        model.linear_constraints.add(
                            lin_expr=[cplex.SparsePair(ind=vars_namen, val=vals)],
                            senses=["L"],
                            rhs=[rhs]
                        )
                        '''

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
                        rhs=[max_ride_time + self.time_const_maker.add_value(start_split,True)
                             - self.time_const_maker.add_value(end_split, False)]
                    )

                # add timing constraint for subsequent route stops
                for i in range(0, len(req.split_requests[key]) - 1):
                    prev_split = req.split_requests[key][i]
                    sub_split = req.split_requests[key][i + 1]
                    var_names = [f"B_{prev_split.split_id}-", f"B_{sub_split.split_id}+"]
                    model.linear_constraints.add(
                        lin_expr=[cplex.SparsePair(ind=var_names, val=[-1, 1])],
                        senses=["G"],
                        rhs=[self.time_const_maker.add_value(prev_split, False) - self.time_const_maker.add_value(
                            sub_split, True)]
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

        self.model.parameters.mip.strategy.nodeselect.set(2)  # (check 1-3)select strategy for selecting node for branching
        self.model.parameters.mip.strategy.variableselect.set(0)  # (check 0 /-1 - 4) select on which variable to branch on

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

        var_names = self.model.variables.get_names()
        var_names_set = set(var_names)
        if len(var_names) != len(var_names_set):
            print("There are duplicate variable names")
        self.model.parameters.mip.display.set(3)  # set extent of logging
        self.model.solve()

        print("Objective Value: " + str(self.model.solution.get_objective_value()))
        Global.INTEGRALITY_GAP_FIRST = int(self.model.solution.MIP.get_mip_relative_gap() * 100)

        Global.COMPUTATION_TIME_SOLVING_FIRST = round(time.time() - Global.COMPUTATION_START_TIME, 4)
        print(f"Solved model after {Global.COMPUTATION_TIME_SOLVING_FIRST} seconds")
        Global.COMPUTATION_START_TIME = time.time()

        if self.multi_objective:

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
            #reset obj function
            self.model.objective.set_linear([(f"q_{x.id}", 0) for x in self.requests])
            obj_pairs = []
            for first_event in self.event_graph.edge_dict.keys():
                for second_event in self.event_graph.edge_dict[first_event][1]:
                    obj_pairs += [(f"x_{first_event.id},{second_event.id}",
                                   Helper.calc_distance(first_event.location, second_event.location))]

            self.model.objective.set_linear(obj_pairs)
            self.model.solve()

            Global.INTEGRALITY_GAP_SECOND = int(self.model.solution.MIP.get_mip_relative_gap() * 100)

        # solve one more time and minimize B*-variables
        # add constraint for km variables
        '''
        obj_pairs = []
        for first_event in self.event_graph.edge_dict.keys():
            for second_event in self.event_graph.edge_dict[first_event][1]:
                obj_pairs += [(f"x_{first_event.id},{second_event.id}",
                               Helper.calc_distance(first_event.location, second_event.location))]
        values = self.model.solution.get_values([x[0] for x in obj_pairs])

        summed_value = 0
        for i in range(len(values)):
            summed_value += (values[i] * obj_pairs[i][1])

        self.model.linear_constraints.add(
            lin_expr=[cplex.SparsePair(ind=[x[0] for x in obj_pairs], val=[x[1] for x in obj_pairs])],
            senses=["L"],
            rhs=[summed_value * 1.0001]
        )

        self.model.objective.set_sense(self.model.objective.sense.minimize)
        time_pairs = [(f"B_{x.split_id}+", 1.0) for x in self.event_graph.request_dict.keys()]
        time_pairs += [(f"B_{x.split_id}-", 1.0) for x in self.event_graph.request_dict.keys()]

        self.model.objective.set_linear(time_pairs)
        self.model.solve()
        '''

        Global.COMPUTATION_TIME_SOLVING_SECOND = round(time.time() - Global.COMPUTATION_START_TIME, 4)
        print(f"Solved model after {Global.COMPUTATION_TIME_SOLVING_SECOND} seconds")
        Global.COMPUTATION_START_TIME = time.time()

    def convert_to_plan(self):
        # for every bus -> start at idle_event and walk along path
        # -> (build RouteStop, check when finished!!, add users to pick-up and drop-off and times)
        processed_pick_up: Set[SplitRequest] = set()
        processed_drop_off: Set[SplitRequest] = set()
        request_order = list(self.requests)
        #arc_names = []
        solution_ints = self.model.solution.get_values([f"q_{x.id}" for x in request_order])
        combi = []
        for i in range(len(request_order)):
            combi.append(f"Request: {request_order[i].id} has value {solution_ints[i]}")

        line_set: Set[Line] = {x.line for x in self.buses}
        line_bus_dict: Dict[Line, List[Bus]] = {x: [y for y in self.buses if y.line == x] for x in line_set}
        all_plans: List[Route] = []

        for line in line_bus_dict.keys():
            idle_event: IdleEvent = next(
                iter(x for x in self.event_graph.edge_dict.keys() if isinstance(x, IdleEvent) and x.line == line))
            sub_names = [f"x_{idle_event.id},{x.id}" for x in self.event_graph.edge_dict[idle_event][1]]
            edge_vals = self.model.solution.get_values(sub_names)
            round_edge_vals = [round(x) for x in edge_vals]
            for i in range(len(line_bus_dict[line])):
                bus = line_bus_dict[line][i]
                bus_plan = Route(bus)

                # i is curr. bus idx(starting at 0)
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
                    next_event = self.event_graph.edge_dict[idle_event][1][j]
                    #arc_names.append(sub_names[j])
                    time_var = round(self.model.solution.get_values(f"B_{next_event.first.split_id}+"))

                    duration = Timer.calc_time(Helper.calc_distance(idle_event.location, next_event.location))
                    curr_route_stop = RouteStop(idle_event.location, bus.line.start_time,
                                                Timer.create_time_object(time_var - Global.TRANSFER_SECONDS - duration
                                                + self.time_const_maker.add_value(next_event.first, True)), bus)
                    bus_plan.stop_list.append(curr_route_stop)

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
                                    Helper.calc_distance(curr_route_stop.stop, next_event.location))
                                if isinstance(next_event, PickUpEvent):
                                    if next_event.first not in processed_pick_up:
                                        time_var = round(self.model.solution.get_values(f"B_{next_event.first.split_id}+"))
                                        curr_route_stop = RouteStop(next_event.location,
                                                                    curr_route_stop.depart_time.add_seconds(duration),
                                                                    Timer.create_time_object(
                                                                        time_var + self.time_const_maker.add_value(
                                                                            next_event.first, True)), bus)
                                        bus_plan.stop_list.append(curr_route_stop)
                                        curr_route_stop.pick_up.add(next_event.first.parent)
                                        processed_pick_up.add(next_event.first)
                                    else:
                                        print(f"Double serviced request removed: {next_event}")
                                else:
                                    if next_event.first not in processed_drop_off:
                                        time_var = round(self.model.solution.get_values(f"B_{next_event.first.split_id}-"))
                                        curr_route_stop = RouteStop(next_event.location,
                                                                    curr_route_stop.depart_time.add_seconds(duration),
                                                                    Timer.create_time_object(
                                                                        time_var + self.time_const_maker.add_value(
                                                                            next_event.first, False)), bus)
                                        bus_plan.stop_list.append(curr_route_stop)
                                        curr_route_stop.drop_off.add(next_event.first.parent)
                                        processed_drop_off.add(next_event.first)
                                    else:
                                        print(f"Double serviced request removed: {next_event}")
                            else:
                                if isinstance(next_event, PickUpEvent):
                                    if next_event.first not in processed_pick_up:
                                        time_var = (round(self.model.solution.get_values(f"B_{next_event.first.split_id}+"))
                                                    + self.time_const_maker.add_value(next_event.first, True))
                                        curr_route_stop.pick_up.add(next_event.first.parent)
                                        processed_pick_up.add(next_event.first)
                                    else:
                                        print(f"Double serviced request removed: {next_event}")
                                else:
                                    if next_event.first not in processed_drop_off:
                                        time_var = (self.model.solution.get_values(f"B_{next_event.first.split_id}-")
                                                    + self.time_const_maker.add_value(next_event.first, False))
                                        curr_route_stop.drop_off.add(next_event.first.parent)
                                        processed_drop_off.add(next_event.first)
                                    else:
                                        print(f"Double serviced request removed: {next_event}")

                                curr_route_stop.depart_time = Timer.create_time_object(time_var)
                        else:
                            print(f"Unnecessary event removed: {next_event}")

                        sub_names = [f"x_{next_event.id},{x.id}" for x in self.event_graph.edge_dict[next_event][1]]
                        edge_vals = self.model.solution.get_values(sub_names)
                        next_round_edge_vals = [round(x) for x in edge_vals]
                        next_event_idx = next_round_edge_vals.index(1)
                        next_event = self.event_graph.edge_dict[next_event][1][next_event_idx]
                        #arc_names.append(sub_names[next_event_idx])

                    # handle final idle_event stop
                    if curr_route_stop.stop == bus.line.depot:
                        curr_route_stop.depart_time = bus.line.end_time
                    else:
                        duration = Timer.calc_time(Helper.calc_distance(curr_route_stop.stop, next_event.location))
                        bus_plan.stop_list.append(
                            RouteStop(next_event.location, curr_route_stop.depart_time.add_seconds(duration),
                                      bus.line.end_time, bus))
                all_plans.append(bus_plan)

        '''
        all_names = []
        km_all = []
        for first in self.event_graph.edge_dict.keys():
            for second in self.event_graph.edge_dict[first][1]:
                all_names.append(f"x_{first.id},{second.id}")
                km_all.append(Helper.calc_distance(first.location, second.location))
        vals = [round(x) for x in self.model.solution.get_values(all_names)]
        filtered = [item for item, m in zip(all_names, vals) if m == 1]
        filtered_kms = [item for item, u in zip(km_all, vals) if u == 1]
        print(sum(filtered_kms))
        print(self.model.solution.get_objective_value())

        intersect = set(filtered) - set(arc_names)
        if len(intersect) > 0:
            print("what is happening")
            '''

        return all_plans
