#!/usr/bin/env python3
"""Search seeds for scripted solution strings (DESIGN.md §6 replay tests).

A simple bot replans every turn: BFS to the port over enterable tiles,
refusing tiles that hug a hunter or killer, then walks the first step.
At the ring-1 port it jacks out — or, with --deep, descends and repeats
on ring 0. Every candidate is validated by driving the keys through the
real dispatch, so a printed solution is ready to embed in test_replay.py.

Usage: python3 tests/find_solution.py [--deep] [max_seed]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import game as d

KEY_FOR = {(-1, 0): "h", (1, 0): "l", (0, -1): "k", (0, 1): "j",
           (-1, -1): "y", (1, -1): "u", (-1, 1): "b", (1, 1): "n"}


def safe_step(run):
    """First step of a shortest path to the port that hugs no hunters."""
    threats = run.hunters | run.killers

    def ok(p):
        return (run.can_enter(p)
                and all(d.cheb(p, t) > 1 for t in threats))

    prev = {run.player: None}
    front = [run.player]
    while front:
        nxt = []
        for x, y in front:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    p = (x + dx, y + dy)
                    if p in prev or not ok(p):
                        continue
                    prev[p] = (x, y)
                    if p == run.port:
                        while prev[p] != run.player:
                            p = prev[p]
                        return p
                    nxt.append(p)
        front = nxt
    return None


def solve(seed, deep):
    run = d.Run(seed=seed)
    keys = []
    for _ in range(300):
        if run.over:
            return None
        if run.player == run.port and run.port_open:
            key = ">" if deep and run.ring > 0 else "<"
        else:
            step = safe_step(run)
            if step is None:
                return None
            key = KEY_FOR[(step[0] - run.player[0],
                           step[1] - run.player[1])]
        keys.append(key)
        run = d.dispatch(run, key)
        if run.won:
            if deep and run.ring != 0:
                return None     # backdoor fluke: doesn't test the descent
            return "".join(keys), run
    return None


def main():
    deep = "--deep" in sys.argv[1:]
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    max_seed = int(args[0]) if args else 500
    for seed in range(max_seed):
        got = solve(seed, deep)
        if got:
            keys, run = got
            print(f"seed={seed} ring={run.ring} trace={run.trace} "
                  f"turn={run.turn} carried={run.carried}")
            print(keys)
            return
    print("no solution found — raise max_seed or improve the bot")


if __name__ == "__main__":
    main()
