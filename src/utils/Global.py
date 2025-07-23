"""
© 2025 Jonas Barth

This file is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0).

You may share and adapt the material for non-commercial use, provided you give appropriate credit,
indicate if changes were made, and distribute your contributions under the same license.

License: https://creativecommons.org/licenses/by-nc-sa/4.0/

File: Global.py
Description: Constant variables shared across different files.
"""
AVERAGE_KMH: int
TRANSFER_SECONDS: int
NUMBER_OF_EXTRA_TRANSFERS: int
TIME_WINDOW_SECONDS: int
INFINITE_INT: int = 10**18
KM_PER_UNIT: int
COST_PER_KM: int
CO2_PER_KM: int
CAPACITY_PER_LINE: int
MAX_DELAY_EQUATION: str
CPLEX_PATH: str
COMPUTATION_START_TIME: float
COMPUTATION_TIME_READING: float
COMPUTATION_TIME_BUILDING: float
COMPUTATION_TIME_SOLVING_FIRST: float
COMPUTATION_TIME_SOLVING_SECOND: float
COMPUTATION_TIME_BUILDING_CPLEX: float
EVENT_GRAPH_NODES: int
EVENT_GRAPH_EDGES: int
NUMBER_OF_SPLITS: int
INTEGRALITY_GAP_FIRST: int
INTEGRALITY_GAP_SECOND: int = 0
