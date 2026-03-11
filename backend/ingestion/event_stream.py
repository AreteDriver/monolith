"""MUD event stream reader — subscribes to real-time events from EVE Frontier's MUD indexer."""

import logging

logger = logging.getLogger(__name__)


class EventStream:
    """Placeholder for MUD event stream subscription.

    MUD indexer URL and event format TBD — will be discovered via explore_chain.py.
    This skeleton exists so the import graph is stable.
    """

    def __init__(self, indexer_url: str = ""):
        self.indexer_url = indexer_url
        self._running = False

    async def connect(self) -> None:
        """Connect to MUD event stream. Implementation pending chain exploration."""
        logger.info("EventStream connect called — implementation pending chain exploration")

    async def disconnect(self) -> None:
        """Disconnect from event stream."""
        self._running = False

    async def listen(self):
        """Yield events from the stream. Generator pattern."""
        logger.info("EventStream listen called — implementation pending chain exploration")
        return
        yield  # makes this an async generator
