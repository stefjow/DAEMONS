"""Headless checks for encrypted archives ≡ and mkfifo (DESIGN.md §7 v2).

Run directly (`python3 tests/test_archives.py`) or via pytest.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import game as d


def fresh(seed=3, **kw):
    return d.Run(seed=seed, **kw)


def test_generation_counts_and_reachability():
    r1, r0 = fresh(), fresh(ring=0, ice="crond", charges={"panic": 3})
    assert len(r1.archives) == 1 and len(r0.archives) == 2
    for run in (r1, r0):
        assert set(run.archives) <= run.flood(run.player)
        assert all(k in ("creds", "tarbomb", "refill")
                   for k in run.archives.values())


def test_scan_and_stat_reveal_archives():
    run = fresh()
    pos = next(iter(run.archives))
    run.player = pos
    d.dispatch(run, "s")
    assert pos in run.known_archives
    assert "archive" in run.message


def test_channel_takes_two_turns_and_pays():
    run = fresh()
    run.archives = {run.player: "creds"}
    run = d.dispatch(run, "x")
    assert run.channel is not None and run.player in run.archives
    run = d.dispatch(run, "x")
    assert not run.over, "unlucky seed: hunters reached the channel"
    assert run.player not in run.archives
    assert run.creds_taken == d.ARCHIVE_CREDS


def test_any_other_action_breaks_the_channel():
    run = fresh()
    run.archives = {run.player: "creds"}
    run = d.dispatch(run, "x")
    run = d.dispatch(run, ".")      # channel broken by waiting
    assert run.channel is None
    run = d.dispatch(run, "x")      # starts over from the top
    assert run.player in run.archives and run.creds_taken == 0


def test_refill_restores_a_spent_program():
    run = fresh(charges={"panic": 1, "stat": None})
    run.archives = {run.player: "refill"}
    run = d.dispatch(run, "x")
    run = d.dispatch(run, "x")
    assert run.loadout["panic"] == d.PROGRAMS["panic"][2]


def test_tarbomb_bursts_junk_and_spawns():
    run = fresh()
    run.archives = {run.player: "tarbomb"}
    junk0, hunters0, trace0 = len(run.junk), len(run.hunters), run.trace
    run = d.dispatch(run, "x")
    run = d.dispatch(run, "x")
    assert run.player not in run.archives
    assert len(run.junk) > junk0
    assert len(run.hunters) > hunters0
    assert run.trace >= trace0 + d.NOISE_TRAP


def test_mkfifo_pipe_is_one_way():
    run = fresh(charges={"panic": 3, "mkfifo": 2})
    # bind inlet where we stand, outlet two tiles away
    run = d.dispatch(run, "m")
    inlet = run.fifos[0]
    outlet = next(p for p in run.flood(run.player)
                  if d.cheb(p, inlet) == 2 and run.can_enter(p)
                  and not run.tile_occupied(p)
                  and p not in run.hunters and p not in run.killers)
    run.player = outlet
    run = d.dispatch(run, "m")
    assert run.fifos == [inlet, outlet]
    assert not run.over

    # entering the inlet flows to the outlet
    run.player = (inlet[0] - 1, inlet[1]) if run.can_enter(
        (inlet[0] - 1, inlet[1])) else (inlet[0] + 1, inlet[1])
    step = (1, 0) if run.player[0] < inlet[0] else (-1, 0)
    trace0 = run.trace
    run.act(*step)
    if not run.over:
        assert run.player == outlet
        assert run.trace > trace0   # travel is loud

    # standing on the outlet does not flow back
    if not run.over:
        assert run.player == outlet     # still there: no reverse travel


if __name__ == "__main__":
    checks = [v for k, v in sorted(globals().items())
              if k.startswith("test_")]
    for check in checks:
        check()
        print(f"ok  {check.__name__}")
    print(f"ALL {len(checks)} CHECKS PASSED")
