"""
© 2025 Jonas Barth

This file is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0).

You may share and adapt the material for non-commercial use, provided you give appropriate credit,
indicate if changes were made, and distribute your contributions under the same license.

License: https://creativecommons.org/licenses/by-nc-sa/4.0/

File: Timer.py
Description: Basic Implementation of Time class based on seconds
        Enables simple addition of two time objects.
"""
from dataclasses import dataclass
from typing import List

from utils import Global


def convert_2_time_from_sec(duration_sec: int):
    h = int(duration_sec // 3600)
    m = int((duration_sec % 3600) // 60)
    s = int(duration_sec % 60)

    return TimeImpl(h, m, s)


# gives duration in seconds
def calc_time(distance: float) -> int:
    return round((distance * 3600) / Global.AVERAGE_KMH)


# can lead to issues with distance
def conv_time_to_dist(duration: int):
    return (duration * Global.AVERAGE_KMH) / 3600


def conv_string_2_time(time_string: str):
    attr = time_string.split(":")
    assert len(attr) == 3
    return TimeImpl(int(attr[0]), int(attr[1]), int(attr[2]))


def create_time_object(seconds: int):
    return TimeImpl(0, 0).add_seconds(seconds)


@dataclass(frozen=True)
class TimeImpl:
    hour: int
    minute: int
    second: int = 0

    def __post_init__(self):
        if 0 <= self.hour <= 23:
            if 0 <= self.minute <= 59:
                if not (0 <= self.second <= 59):
                    raise ValueError(f"second not in range 0 to 59; was {self.second}")
            else:
                raise ValueError(f"minute not in range 0 to 59; was {self.minute}")
        else:
            raise ValueError(f"hour not in range 0 to 23; was {self.hour}")

    def get_in_seconds(self):
        sum_sec: int = 0

        sum_sec += 3600 * self.hour
        sum_sec += 60 * self.minute
        sum_sec += self.second

        return sum_sec

    def __add__(self, other):
        assert isinstance(other, TimeImpl)
        return convert_2_time_from_sec(self.get_in_seconds() + other.get_in_seconds())

    def __sub__(self, other):
        assert isinstance(other, TimeImpl)
        return convert_2_time_from_sec(self.get_in_seconds() - other.get_in_seconds())

    def __str__(self):
        string_list: List[str] = [str(self.hour), str(self.minute), str(self.second)]
        for i in range(3):
            if len(string_list[i]) == 1:
                string_list[i] = "0" + string_list[i]

        return f"{string_list[0]}:{string_list[1]}:{string_list[2]}"

    def __lt__(self, other):
        assert isinstance(other, TimeImpl)
        if self.get_in_seconds() < other.get_in_seconds():
            return True
        else:
            return False

    def __gt__(self, other):
        assert isinstance(other, TimeImpl), f"Assertion failed: other is: {other} of type: {type(other)}"
        if self.get_in_seconds() > other.get_in_seconds():
            return True
        else:
            return False

    def __eq__(self, other):
        assert isinstance(other, TimeImpl)
        if self.get_in_seconds() == other.get_in_seconds():
            return True
        else:
            return False

    def __le__(self, other):
        assert isinstance(other, TimeImpl)
        if self.get_in_seconds() <= other.get_in_seconds():
            return True
        else:
            return False

    def __ge__(self, other):
        assert isinstance(other, TimeImpl)
        if self.get_in_seconds() >= other.get_in_seconds():
            return True
        else:
            return False

    def add_seconds(self, seconds: int):
        return convert_2_time_from_sec(self.get_in_seconds() + seconds)

    def sub_seconds(self, seconds: int):
        return convert_2_time_from_sec(self.get_in_seconds() - seconds)
