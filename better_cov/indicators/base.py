"""Base interface for function importance indicators."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ImportanceIndicator(ABC):
    """Abstract interface for computing module/function importance.

    Each indicator receives the list of source files to analyze and
    returns an importance score per module (relative file path).

    The score is normalized between 0.0 and 1.0 by the implementation.
    Modules not present in the returned dict receive a score of 0.0
    (minimum importance is handled on the scorer side via a configurable floor).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the indicator (for reports and logs)."""

    @abstractmethod
    def compute(self, source_dirs: list[str]) -> dict[str, float]:
        """Computes the importance score for each source file.

        Args:
            source_dirs: List of directories to scan for computing importance.

        Returns:
            Dict mapping relative_file_path → normalized score [0.0, 1.0].
            Keys must match the ``file`` values of FunctionCoverage.
        """
