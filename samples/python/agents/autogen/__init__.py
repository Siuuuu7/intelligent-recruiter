"""AutoGen Candidate Evaluation Agent

This package provides a multi-agent candidate evaluation system built with AutoGen.
It enables comprehensive assessment of candidates for AI Scientist positions using
specialized Tech Rater, Inclusion Rater, and Reporter agents.
"""

from agents.autogen.agent import AutogenAgent
from agents.autogen.task_manager import TaskManager


__all__ = ["TaskManager", "AutogenAgent"]
