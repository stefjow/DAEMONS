"""Headless checks for the ring/ICE mechanics (DESIGN.md §3.1, v0.5).

Run directly (`python3 tests/test_rings.py`) or via pytest.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import game as d


def test_stack_is_seed_deterministic():
    r1 = d.Run(seed=42)
    assert r1.ring == 1 and r1.ice == "crond"
    assert r1.next_ice in d.ICE_POOL
    assert d.Run(seed=42).next_ice == r1.next_ice


def test_ring1_banner_fits_and_names_the_ice():
    r1 = d.Run(seed=42)
    r1.player = r1.port
    banner = r1.port_message()
    assert r1.next_ice in banner and "[>]" in banner and "[<]" in banner
    assert len(banner) <= d.BOARD_W + 38, f"banner too long: {len(banner)}"


def test_state_carries_down_and_thresholds_stay_burned():
    for ice in d.ICE_POOL:
        r0 = d.Run(level=1, ring=0, ice=ice,
                   charges={"panic": 2, "stat": None}, seed=7,
                   trace=60, carried=2, creds=1)
        assert r0.trace == 60 and r0.carried == 2 and r0.creds_taken == 1
        assert r0.loadout == {"panic": 2, "stat": None}
        assert r0.waves_fired == {25, 50}
        assert r0.killer_woken
        assert len(r0.killers) >= 1, "a K follows you down at >=50% trace"
        if ice == "watchdogd":
            assert len(r0.killers) == 2


def test_banner_promise_matches_the_board():
    for ice in d.ICE_POOL:
        r0 = d.Run(ring=0, ice=ice, charges={"panic": 3}, seed=7)
        promised = d.ring0_files(ice)
        actual = len(r0.files) + sum(
            1 for k in r0.hidden.values() if k == "file")
        assert actual == promised, f"{ice}: banner ¤×{promised}, board {actual}"
        assert r0.total_files == r0.carried + actual
        r0.player = r0.port
        assert "jack out" in r0.port_message()


def test_auditd_doubles_every_trace_gain():
    r0 = d.Run(ring=0, ice="auditd", charges={"panic": 3}, seed=9)
    before = r0.trace
    r0.add_trace(3)
    assert r0.trace == before + 6


def test_calm_descent_spawns_no_killers():
    r0 = d.Run(ring=0, ice="crond", charges={"panic": 3}, seed=11, trace=20)
    assert not r0.killers and not r0.killer_woken
    assert r0.waves_fired == set()


def test_jack_out_keeps_loot_and_names_the_ring():
    r1 = d.Run(seed=5)
    r1.carried, r1.creds_taken = 3, 2
    r1.jack_out()
    assert r1.won and "ring 1 port" in r1.over and "3 files" in r1.over


def test_camping_never_wins():
    run = d.Run(seed=1)
    for _ in range(95):
        if run.over:
            break
        run.act(0, 0)
    if run.over:
        assert not run.won
    else:
        assert not run.port_open, "port should have sealed by turn 95"


if __name__ == "__main__":
    checks = [v for k, v in sorted(globals().items())
              if k.startswith("test_")]
    for check in checks:
        check()
        print(f"ok  {check.__name__}")
    print(f"ALL {len(checks)} CHECKS PASSED")
