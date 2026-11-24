"""Errors the data layer raises for the CLI to report with exit code 1."""


class WorqueueError(Exception):
    """An error caused by the data, the environment, or a request the data cannot satisfy."""
