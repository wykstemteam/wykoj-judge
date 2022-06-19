from enum import Enum


class Verdict(str, Enum):
    AC = 'ac'
    CE = 'ce'
    WA = 'wa'
    RE = 're'
    TLE = 'tle'
    SE = 'se'
    PS = 'ps'
