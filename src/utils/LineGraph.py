"""
© 2025 Jonas Barth

This file is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0).

You may share and adapt the material for non-commercial use, provided you give appropriate credit,
indicate if changes were made, and distribute your contributions under the same license.

License: https://creativecommons.org/licenses/by-nc-sa/4.0/

File: LineGraph.py
Description: Graph structure for a network of lines and stops.
            Enables DFS and Dijkstra-Search
"""
from typing import List, Set, Dict, Tuple

from utils import Timer, RequestPreprocessing
from models.Network import Bus, Stop, Line


class LineEdge:
    """
    Edge for the LineGraph class, consists of two stops and a line,
    Only instantiated between transfer stops, transfer to pick-up/drop-off location or pick-up and drop-off location of request.
    """
    def __init__(self, v1: Stop, v2: Stop, line: Line, duration: int = -1):
        self.v1: Stop = v1
        self.v2: Stop = v2
        self.line: Line = line
        if duration == -1:
            self.duration: int = Timer.calc_time(v1.calc_distance(v2))
        else:
            self.duration: int = duration

    def contains_stop(self, v: Stop):
        if self.v1 == v or self.v2 == v:
            return True
        else:
            return False


# only aggregated edges of graph, specific for each request(add s -> transfer, transfer -> end, s -> t separately)
# edges are directed, unique for every line and linked to in both directions
# incoming edges are at 0, outgoing at 1
class LineGraph:
    """
    Models directed Graph for network of lines and stops.
    Graph is altered for every request to incorporate individual drop-off and pick-up location.
    """
    def __init__(self, network: List[Bus]):
        self.all_lines: Set[Line] = {bus.line for bus in network}
        self._graph_dict: Dict[Stop, Tuple[Set[LineEdge], Set[LineEdge]]] = {}
        self.transfer_nodes: Set[Stop] = set()
        self._make_graph()

        self.temp_edges: Set[LineEdge] | None = None
        self.all_stops: Set[Stop] = set().union(*[set(x.stops) for x in self.all_lines])

    def get_nodes(self):
        return self._graph_dict.keys()

    def get_edges(self):
        return set().union(*[x[0] | x[1] for x in self._graph_dict.values()])

    def get_edges_in(self, node: Stop):
        return self._graph_dict[node][0]

    def get_edges_out(self, node: Stop):
        return self._graph_dict[node][1]

    def _make_graph(self):
        """
        Builds graph based on given set of lines.
        Only adding transfer Stop to transfer Stop edges (in both directions).
        """
        # creates basic aggregated edges to be reused
        for line_a in self.all_lines:
            transfer_stops_a: Set[Stop] = set()
            for other_line in (self.all_lines - {line_a}):
                transfer_stops_a |= set(line_a.stops) & set(other_line.stops)

            # make lineEdge for all pairs of a line
            for transfer_a in transfer_stops_a:
                if transfer_a not in self._graph_dict:
                    self._graph_dict[transfer_a] = (set(), set())

                for other_stop in (transfer_stops_a - {transfer_a}):
                    duration: int = Timer.calc_time(transfer_a.calc_distance(other_stop))
                    edge_to = LineEdge(transfer_a, other_stop, line_a, duration)
                    self._graph_dict[transfer_a][1].add(edge_to)

                    if other_stop in self._graph_dict:
                        self._graph_dict[other_stop][0].add(edge_to)
                    else:
                        self._graph_dict[other_stop] = ({edge_to}, set())

            self.transfer_nodes |= transfer_stops_a

    def add_request(self, pick_up: Stop, drop_off: Stop):
        """
        For next request add: pick-up -  transfer, transfer - drop-off and pick-up - drop-off edges.
        :param pick_up: pick-up stop of request
        :param drop_off: drop-off stop of request
        """
        self.temp_edges = []
        # add request stops to graph

        if pick_up not in self._graph_dict:
            # look for the single line of pick-up spot
            pick_up_line = next((x for x in self.all_lines if pick_up in x.stops))
            # get all intersection of this line
            transfer_stops: Set[Stop] = self.get_nodes() & set(pick_up_line.stops)

            self._graph_dict[pick_up] = (set(), set())
            for stop in transfer_stops:
                duration: int = Timer.calc_time(pick_up.calc_distance(stop))
                edge_to = LineEdge(pick_up, stop, pick_up_line, duration)
                self._graph_dict[pick_up][1].add(edge_to)
                self._graph_dict[stop][0].add(edge_to)
                self.temp_edges += [edge_to]

        if drop_off not in self._graph_dict:
            drop_off_line = next((x for x in self.all_lines if drop_off in x.stops))
            transfer_stops: Set[Stop] = self.get_nodes() & set(drop_off_line.stops)

            self._graph_dict[drop_off] = (set(), set())
            for stop in transfer_stops:
                duration: int = Timer.calc_time(stop.calc_distance(drop_off))
                edge_from = LineEdge(stop, drop_off, drop_off_line, duration)
                self._graph_dict[drop_off][0].add(edge_from)
                self._graph_dict[stop][1].add(edge_from)
                self.temp_edges += [edge_from]

    def delete_request(self, pick_up: Stop, drop_off: Stop):
        """
        After finished with request: delete pick-up -  transfer, transfer - drop-off and pick-up - drop-off edges.
        :param pick_up: pick-up stop of request
        :param drop_off: drop-off stop of request
        """
        # delete edges and nodes of old request when finished
        for edge in self.temp_edges:
            self._graph_dict[edge.v1][1].remove(edge)
            self._graph_dict[edge.v2][0].remove(edge)

        for node in {pick_up, drop_off}:
            if not (node in self.transfer_nodes) and len(self._graph_dict[node][0]) == 0 and len(self._graph_dict[node][1]) == 0:
                del self._graph_dict[node]

        self.temp_edges = None
