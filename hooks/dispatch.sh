#!/usr/bin/env bash
# Plugin shim: the plugin root is not on PYTHONPATH when the harness invokes hooks, so put it
# there and exec the dispatcher. This file is the only bridge between hooks.json and the package.
exec env PYTHONPATH="${CLAUDE_PLUGIN_ROOT}${PYTHONPATH:+:$PYTHONPATH}" python3 -m lever.dispatch
