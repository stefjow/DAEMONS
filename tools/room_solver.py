#!/usr/bin/env python3
"""Exhaustive solver for authored rooms — the room-design tool.

BFS over the full deterministic game state, moves and waits only (no
programs), so any solution it prints is a loadout-independent guarantee.
Use it to prove a draft room is solvable, measure par, and pin the
solution strings for tests/test_rooms.py.

Usage:
    python3 tools/room_solver.py rooms/foo.txt              # exit-only
    python3 tools/room_solver.py rooms/foo.txt --route \
        1,9 15,9 15,1 7,2 1,1                               # loot legs
"""
import copy
import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import game
import rooms

KEYS = "hjklyubn."


def state_key(run):
    return (run.player, frozenset(run.hunters), frozenset(run.killers),
            frozenset(run.junk), frozenset(run.files),
            frozenset(run.creds_tiles), run.turn % game.SENTRY_PERIOD)


def fresh(room, trace=0):
    return game.Run(ring=0, ice=room.ice, room=room, charges={}, seed=1,
                    trace=trace)


def solve_leg(start, goal, max_depth=22, max_states=300_000):
    """Shortest key string from `start` until the runner stands on
    `goal`, alive. Returns (keys, end_state) or (None, None)."""
    if start.player == goal:
        return "", start
    seen = {state_key(start)}
    frontier = deque([("", start)])
    expanded = 0
    while frontier and expanded < max_states:
        keys, base = frontier.popleft()
        if len(keys) >= max_depth or base.over:
            continue
        for k in KEYS:
            expanded += 1
            run = game.dispatch(copy.deepcopy(base), k)
            if run.over:
                continue
            if run.player == goal:
                return keys + k, run
            skey = state_key(run)
            if skey not in seen:
                seen.add(skey)
                frontier.append((keys + k, run))
    return None, None


def solve_route(room, waypoints, trace=0):
    """Chain legs through waypoints, then the port. Greedy per leg —
    a None result does not prove impossibility, only failure to chain."""
    run = fresh(room, trace)
    total = ""
    for goal in list(waypoints) + [room.port]:
        keys, run = solve_leg(run, goal)
        if keys is None:
            return None, goal
        total += keys
    if run.port_open:
        return total + "<", run
    return None, "port sealed"


def main():
    room = rooms.parse_room(Path(sys.argv[1]).read_text(encoding="utf-8"))
    if "--route" in sys.argv:
        idx = sys.argv.index("--route")
        waypoints = [tuple(map(int, a.split(",")))
                     for a in sys.argv[idx + 1:]]
        keys, end = solve_route(room, waypoints)
        if keys is None:
            print(f"route failed at {end}")
        else:
            print(f"route line ({len(keys)} keys): {keys}")
            print(f"end: trace={end.trace} carried={end.carried} "
                  f"creds={end.creds_taken} killers={len(end.killers)}")
    else:
        keys, end = solve_route(room, [])
        if keys is None:
            print("no exit line found within limits")
        else:
            print(f"scout line ({len(keys)} keys): {keys}")


if __name__ == "__main__":
    main()
