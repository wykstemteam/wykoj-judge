from enum import Enum


class Verdict(str, Enum):
    AC = 'ac'
    CE = 'ce'
    WA = 'wa'
    RTE = 'rte'
    TLE = 'tle'
    IE = 'ie'
