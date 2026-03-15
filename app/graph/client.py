"""
Neo4j connection and session management for graph storage and query.
Uses app.config for URI, user, password.
"""
from typing import Optional

from neo4j import GraphDatabase, Driver

from app.config import get_settings

_driver: Optional[Driver] = None


def get_driver() -> Driver:
    """Return a Neo4j driver instance (cached). Neo4j env vars are validated at settings load."""
    global _driver
    if _driver is None:
        s = get_settings()
        _driver = GraphDatabase.driver(
            s.neo4j_uri,
            auth=(s.neo4j_user, s.neo4j_password),
        )
    return _driver


def close_driver() -> None:
    """Close the global driver if open."""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None
