"""
© 2025 Jonas Barth

This file is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0).

You may share and adapt the material for non-commercial use, provided you give appropriate credit,
indicate if changes were made, and distribute your contributions under the same license.

License: https://creativecommons.org/licenses/by-nc-sa/4.0/

File: EventGraph.py
Description: Modelling class of Events and EventGraph
"""
from typing import List, Set, Tuple, Dict

from models.Network import Stop, Line
from utils import Global, Timer, RequestPreprocessing
from models.Demand import SplitRequest
from utils.Timer import TimeImpl


class Event:
    """
    Abstract basic event class, formed over a split action and set of other splits in the vehicle.
    """
    id_counter: int = 0

    def __init__(self, first: SplitRequest = None, remaining: Set[SplitRequest] = None):
        if remaining is None:
            remaining = set()
        self.remaining_id: Set[int] = {x.id for x in remaining}
        self.remaining_split_id: Set[int] = {x.split_id for x in remaining}
        self.first: SplitRequest = first
        self.earl_depart: TimeImpl | None = None
        self.lat_depart: TimeImpl  | None = None
        self.location: Stop | None = None
        self.id: int = Event.id_counter
        Event.id_counter += 1

    def set_before_event(self):
        pass

    def set_after_event(self):
        pass


class IdleEvent(Event):
    """
    Event for a given line, marking a bus starting or ending its tour at the depot.
    """
    def __init__(self, line: Line):
        super().__init__()
        self.location: Stop = line.depot
        self.line: Line = line
        self.earl_depart: TimeImpl = TimeImpl(0, 0)
        self.lat_depart: TimeImpl = TimeImpl(23, 59)

    def set_before_event(self):
        return frozenset()

    def set_after_event(self):
        return frozenset()

    def __repr__(self):
        return f"IdleEvent(user:-; others:[]; location:{self.location.id}; line:{self.line.id})"

    def __str__(self):
        return f"(-,-,{self.location.id},{self.line.id})"


class PickUpEvent(Event):
    """
    Event where the first request is picked up.
    """
    def __init__(self, first: SplitRequest, remaining: Set[SplitRequest], earl_time: TimeImpl, lat_time: TimeImpl):
        super().__init__(first, remaining)
        self.location: Stop = first.pick_up_location
        self.earl_depart: TimeImpl = earl_time
        self.lat_depart: TimeImpl = lat_time

    def set_before_event(self):
        return frozenset(self.remaining_split_id)

    def set_after_event(self):
        return frozenset(self.remaining_split_id | {self.first.split_id})

    def __repr__(self):
        return f"PickUpEvent(user:{self.first.id}; others:{self.remaining_id}; location:{self.location.id}; line:{self.first.line.id})"

    def __str__(self):
        return f"({self.first.id},{self.remaining_id},{self.location.id},{self.first.line.id})+"

class DropOffEvent(Event):
    """
    Event where the first request is dropped off.
    """
    def __init__(self, first: SplitRequest, remaining: Set[SplitRequest], earl_time: TimeImpl, lat_time: TimeImpl):
        super().__init__(first, remaining)
        self.location: Stop = first.drop_off_location
        self.earl_depart: TimeImpl = earl_time
        self.lat_depart: TimeImpl = lat_time

    def set_before_event(self):
        return frozenset(self.remaining_split_id | {self.first.split_id})

    def set_after_event(self):
        return frozenset(self.remaining_split_id)

    def __repr__(self):
        return f"DropOffEvent(user:{self.first.id}; others:{self.remaining_id}; location:{self.location.id}; line:{self.first.line.id})"

    def __str__(self):
        return f"({self.first.id},{self.remaining_id},{self.location.id},{self.first.line.id})-"


class EventGraph:
    """
    Nodes are the Events, with directed edges between possibly subsequent events.
    """
    def __init__(self):
        self.request_dict: Dict[SplitRequest, Tuple[Set[Event], Set[Event]]] = {}
        self.edge_dict: Dict[Event, Tuple[List[Event], List[Event]]] = {}

    def data_in_string(self):
        nodes = len(self.edge_dict.keys())
        split_requests = len(self.request_dict.keys())

        return f"Number of split_requests: {split_requests}; Number of nodes: {nodes}; Number of edges: {self.get_number_of_edges()}."

    def get_edges_in(self, event: Event):
        return self.edge_dict[event][0]

    def get_edges_out(self, event: Event):
        return self.edge_dict[event][1]


    def check_connectivity(self, idle_event: IdleEvent):
        """
        Checks if all events have a path to and from idle event.
        """
        look_up_dict: Dict[Event, List[bool]] = {x: [False, False] for x in self.edge_dict.keys()
                                                 if not isinstance(x, IdleEvent) and x.first.line == idle_event.line}
        look_up_dict |= {idle_event: [True, True]}

        # do breadth-search for incoming and outgoing edges, respectively
        # conjunct per idle_event -> delete all others
        found_sets: Tuple[Set[Event], Set[Event]] = ({idle_event}, {idle_event})

        for i in {0, 1}:
            last_found: Set[Event] = {idle_event}
            while len(last_found) > 0:
                new_found = set()
                for event in last_found:
                    for neighbour in self.edge_dict[event][i]:
                        if not look_up_dict[neighbour][i]:
                            new_found.add(neighbour)
                            look_up_dict[neighbour][i] = True
                last_found = new_found
                found_sets[i].update(last_found)

        overall_found = found_sets[0] & found_sets[1]

        unconnected_events = set(look_up_dict.keys()) - overall_found
        if len(unconnected_events) > 0:
            raise ValueError("There are events in EventGraph not connected to idle event")


    def add_events(self, event_set_line: Set[Event]):
        """
        Adds events to the graph and connects them accordingly.
        :param event_set_line: set of events that can occur on a specific line, to be added to event graph
        """
        self.edge_dict |= {x: ([], []) for x in event_set_line}
        split_requests = {x.first for x in event_set_line if not isinstance(x, IdleEvent)}
        self.request_dict |= {x: (set(), set()) for x in split_requests}

        hash_dict: Dict[int, Set[Tuple[bool, Event]]] = {}

        for event in event_set_line:
            if isinstance(event, PickUpEvent):
                self.request_dict[event.first][0].add(event)
            elif isinstance(event, DropOffEvent):
                self.request_dict[event.first][1].add(event)

            key_before: int = hash(event.set_before_event())
            key_after: int = hash(event.set_after_event())

            # hash function does not have collisions
            if key_before in hash_dict:
                hash_dict[key_before].add((True, event))
            else:
                hash_dict[key_before] = {(True, event)}

            if key_after in hash_dict:
                hash_dict[key_after].add((False, event))
            else:
                hash_dict[key_after] = {(False, event)}

        for key in hash_dict:
            same_pass_events_succ: Set[Event] = {x[1] for x in hash_dict[key] if x[0]}
            same_pass_events_pred: Set[Event] = {x[1] for x in hash_dict[key] if not x[0]}

            for event_before in same_pass_events_pred:
                for event_after in same_pass_events_succ:
                    duration = Timer.calc_time(event_before.location.calc_distance(event_after.location))
                    service_time = Global.TRANSFER_SECONDS * int(bool(duration))
                    #if event_before.first is not None and event_before.first.id == 2 and event_after.first is not None and event_after.first.id == 2:
                    #    print("hi")
                    if (event_before is not event_after) and event_before.earl_depart.add_seconds(
                            duration + service_time) <= event_after.lat_depart:
                        self.edge_dict[event_after][0].append(event_before)
                        self.edge_dict[event_before][1].append(event_after)

    def get_number_of_edges(self):
        """

        :return: Number of edges in the event graph
        """
        return sum(len(self.edge_dict[x][1]) for x in self.edge_dict.keys())
