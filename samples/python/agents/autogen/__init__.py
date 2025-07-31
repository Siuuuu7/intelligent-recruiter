"""AutoGen Currency Agent

This package provides a currency conversion agent built with AutoGen.
It enables querying exchange rates between different currencies.
"""

from agents.autogen.agent import AutogenAgent
from agents.autogen.task_manager import TaskManager


__all__ = ['TaskManager', 'AutogenAgent']
