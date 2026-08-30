from __future__ import annotations

"""
Keep this package import-light.

`core.agents.registry` imports many agent modules, and those agents import parts
of `core.pipeline`. Importing the registry here caused circular imports when
users imported any `core.agents.*` module.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable


def create_agent(agent_id: str, config: dict[str, Any] | None = None):
    from core.agents.registry import create_agent as _create_agent

    return _create_agent(agent_id, config)


def list_agents() -> list[str]:
    from core.agents.registry import list_agents as _list_agents

    return _list_agents()


__all__ = ["create_agent", "list_agents"]
