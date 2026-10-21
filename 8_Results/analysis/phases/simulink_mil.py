"""Simulink MIL (4-module ideal model) phase: the same CSV format from run_scenarios('mil', ...)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from phases import simulink   # noqa: E402


def cases(scenario):
    return simulink._cases("mil", scenario)


def settled_stats():
    return []
