from typing import List, Set, Dict, Tuple

from utils.helper import Timer
from utils.network import Stop
from utils.network.Bus import Bus
from utils.network.Line import Line


class LineEdge:
    def __init__(self, v1: Stop, v2: Stop, line: Line, duration: int = -1):
        from utils.helper import Helper
        self.v1: Stop = v1
        self.v2: Stop = v2
        self.line: Line = line
        if duration == -1:
            self.duration: int = Timer.calc_time(Helper.calc_distance(v1, v2))
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
        from utils.helper import Helper
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
                    duration: int = Timer.calc_time(Helper.calc_distance(transfer_a, other_stop))
                    edge_to = LineEdge(transfer_a, other_stop, line_a, duration)
                    self._graph_dict[transfer_a][1].add(edge_to)

                    if other_stop in self._graph_dict:
                        self._graph_dict[other_stop][0].add(edge_to)
                    else:
                        self._graph_dict[other_stop] = ({edge_to}, set())

            self.transfer_nodes |= transfer_stops_a

    def add_request(self, search_pick_up: Stop, search_drop_off: Stop):
        from utils.helper import Helper
        self.temp_edges = []
        # add request stops to graph

        if search_pick_up not in self._graph_dict:
            # look for the single line of pick-up spot
            pick_up_line = next((x for x in self.all_lines if search_pick_up in x.stops))
            # get all intersection of this line
            transfer_stops: Set[Stop] = self.get_nodes() & set(pick_up_line.stops)

            self._graph_dict[search_pick_up] = (set(), set())
            for stop in transfer_stops:
                duration: int = Timer.calc_time(Helper.calc_distance(search_pick_up, stop))
                edge_to = LineEdge(search_pick_up, stop, pick_up_line, duration)
                self._graph_dict[search_pick_up][1].add(edge_to)
                self._graph_dict[stop][0].add(edge_to)
                self.temp_edges += [edge_to]

        if search_drop_off not in self._graph_dict:
            drop_off_line = next((x for x in self.all_lines if search_drop_off in x.stops))
            transfer_stops: Set[Stop] = self.get_nodes() & set(drop_off_line.stops)

            self._graph_dict[search_drop_off] = (set(), set())
            for stop in transfer_stops:
                duration: int = Timer.calc_time(Helper.calc_distance(stop, search_drop_off))
                edge_from = LineEdge(stop, search_drop_off, drop_off_line, duration)
                self._graph_dict[search_drop_off][0].add(edge_from)
                self._graph_dict[stop][1].add(edge_from)
                self.temp_edges += [edge_from]

    def delete_request(self, pick_up: Stop, drop_off: Stop):
        # delete edges and nodes of old request when finished
        for edge in self.temp_edges:
            self._graph_dict[edge.v1][1].remove(edge)
            self._graph_dict[edge.v2][0].remove(edge)

        for node in {pick_up, drop_off}:
            if not (node in self.transfer_nodes) and len(self._graph_dict[node][0]) == 0 and len(self._graph_dict[node][1]) == 0:
                del self._graph_dict[node]

        self.temp_edges = None
