"""Detent: a strictly passive, deterministic leverage layer for coding agents.

It never initiates an LLM call. It reads structural signal the harness already emits on every
hook event (documented, bounded, model-agnostic — see detent/contract.py) and, where the event
supports it, rewrites the call or its result before either costs anything. See LAW.md.
"""
