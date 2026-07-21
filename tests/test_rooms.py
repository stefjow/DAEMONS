"""Headless checks for authored rooms (the anti-randomness experiment).

The solution strings were found by exhaustive search (BFS over the full
deterministic state space, moves and waits only — no programs), so they
are loadout-independent guarantees. If the room file or the rules change,
re-derive them with the design-time solver.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import game
import rooms

KENNEL_SCOUT = "llllnllllllluu<"
KENNEL_FULL = "jjjuukkkkyylnnnnnlluuluuuhhbbbbykyljjnllnnnnkkkk<"


def kennel_run(trace=0):
    room = rooms.room_for("watchdogd")
    return game.Run(ring=0, ice="watchdogd", room=room, charges={},
                    seed=1, trace=trace)


def play(run, keys):
    for k in keys:
        run = game.dispatch(run, k)
        if run.over:
            break
    return run


def test_kennel_parses():
    room = rooms.room_for("watchdogd")
    assert room is not None and room.name == "kennel"
    assert (room.w, room.h) == (17, 11)
    assert len(room.files) == 4 and len(room.creds) == 1
    assert len(room.hunters) == 2 and len(room.killers) == 1
    assert len(room.sentries) == 1 and room.sentries[0]["axis"] == "h"
    assert room.player == (1, 6) and room.port == (15, 5)


def test_room_is_fully_visible():
    run = kennel_run()
    assert not run.hidden and not run.archives
    assert run.total_files == 4


def test_waiting_dies_to_the_watchdog():
    run = play(kennel_run(), "." * 20)
    assert run.over and not run.won
    assert "hunter-killer" in run.over


def test_scout_line_reaches_the_port():
    run = play(kennel_run(), KENNEL_SCOUT)
    assert run.won and run.carried == 0


def test_full_loot_line_fries_the_watchdog():
    run = play(kennel_run(), KENNEL_FULL)
    assert run.won
    assert run.carried == 4 and run.creds_taken == 1
    assert not run.killers, "the K should die on the sentry beam"


def test_descend_loads_the_authored_room():
    seed = next(s for s in range(200)
                if game.Run(seed=s).next_ice == "watchdogd")
    ring1 = game.Run(seed=seed)
    ring1.player = ring1.port
    ring0 = game.dispatch(ring1, ">")
    assert ring0.room is not None and ring0.W == 17
    assert ring0.retry_args is not None
    # retry rebuilds the identical descent state
    again = game.Run(**ring0.retry_args)
    assert (again.player, again.hunters, again.killers, again.trace) \
        == (ring0.player, ring0.hunters, ring0.killers, ring0.trace)


def test_procedural_rings_have_no_retry():
    seed = next(s for s in range(200)
                if game.Run(seed=s).next_ice == "crond")
    ring1 = game.Run(seed=seed)
    ring1.player = ring1.port
    ring0 = game.dispatch(ring1, ">")
    assert ring0.room is None
    assert getattr(ring0, "retry_args", None) is None


if __name__ == "__main__":
    checks = [v for k, v in sorted(globals().items())
              if k.startswith("test_")]
    for check in checks:
        check()
        print(f"ok  {check.__name__}")
    print(f"ALL {len(checks)} CHECKS PASSED")
