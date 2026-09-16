"""
Deterministic action-outcome-to-experience interpreter.
"""

from .outcome_interpreter import (  # noqa: F401
    FAILURE_MOOD_OFFSET,
    SUCCESS_MOOD_OFFSET,
    interpret_outcome,
)
