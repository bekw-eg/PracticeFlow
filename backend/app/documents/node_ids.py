"""Stable node identifiers (rule: 'Do NOT use array index as a permanent identity').

IDs are generated once, when a node is created, and never change for the
life of that node — even if it moves within the tree. This is what will let
Phase 3 comments anchor to `blockId` and survive reordering/reflow.
"""
import secrets


def new_node_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(4)}"
