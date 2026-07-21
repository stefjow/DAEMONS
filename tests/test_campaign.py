"""Headless checks for the meta-layer (DESIGN.md §5): city map rhizome,
corp clocks as run fee, publish-or-fence, backdoor secret edges.

Run directly (`python3 tests/test_campaign.py`) or via pytest.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import game
import meta


def won_run(node, carried=3, creds=2, via=None):
    """A finished run on this node without playing it out."""
    run = game.Run(level=node.level, seed=node.seed)
    run.carried, run.creds_taken = carried, creds
    run.jack_out(via)
    return run


def dead_run(node):
    run = game.Run(level=node.level, seed=node.seed)
    run.carried, run.creds_taken = 2, 2
    run.die("test")
    return run


def test_campaign_is_seed_deterministic():
    a, b = meta.Campaign(seed=5), meta.Campaign(seed=5)
    assert [(n.name, n.level, n.seed, n.rumor) for n in a.known] \
        == [(n.name, n.level, n.seed, n.rumor) for n in b.known]


def test_starts_with_one_entry_node_per_corp():
    c = meta.Campaign(seed=5)
    assert sorted(n.corp for n in c.known) == sorted(meta.CORPS)
    assert all(n.level == 1 for n in c.known)


def test_honest_rumors_match_the_boot_banner():
    c = meta.Campaign(seed=5)
    hits = sum(n.rumor == game.Run(seed=n.seed).next_ice
               for n in (c.new_node(corp, 1) for corp in meta.CORPS * 20))
    assert hits >= 30, "rumors should be honest most of the time"


def test_jacking_out_grows_the_map_and_ticks_clocks():
    c = meta.Campaign(seed=5)
    node = c.known[0]
    before = len(c.known)
    events = c.end_run(node, won_run(node), publish=False)
    assert len(c.known) > before
    assert all(child.level == node.level + 1 for child in c.known[before:])
    assert all(c.clock[corp] == 1 for corp in meta.CORPS)
    assert node.spawned and node.raided == 1
    assert any("links to" in e for e in events)
    # children spawn only once
    grown = len(c.known)
    c.end_run(node, won_run(node), publish=False)
    assert len(c.known) == grown


def test_fence_pays_publish_exposes():
    c = meta.Campaign(seed=5)
    node = c.known[0]
    c.end_run(node, won_run(node, carried=3, creds=2), publish=False)
    assert c.bank == 3 * meta.FENCE_RATE + 2
    c.clock[node.corp] = 5
    c.end_run(node, won_run(node, carried=3, creds=0), publish=True)
    assert c.exposure[node.corp] == 3
    assert c.clock[node.corp] == 5 - 3 + 1     # setback, then the run fee


def test_backdoor_reveals_a_secret_edge():
    c = meta.Campaign(seed=5)
    node = c.known[0]
    node.spawned = True                        # isolate the secret edge
    before = len(c.known)
    events = c.end_run(node, won_run(node, via="a backdoor"), publish=False)
    secret = c.known[before:]
    assert len(secret) == 1 and secret[0].level == node.level + 2
    assert any("secret edge" in e for e in events)


def test_death_wipes_the_bank_but_not_the_map():
    c = meta.Campaign(seed=5)
    node = c.known[0]
    c.bank = 9
    known_before = len(c.known)
    c.end_run(node, dead_run(node))
    assert c.bank == 0
    assert len(c.known) == known_before        # nothing revealed
    assert all(c.clock[corp] == 1 for corp in meta.CORPS)   # fee still due


def test_campaign_loss_and_win():
    c = meta.Campaign(seed=5)
    node = c.known[0]
    for corp in meta.CORPS:
        c.clock[corp] = meta.CLOCK_MAX - 1
    c.end_run(node, dead_run(node))
    assert c.result == "lost"

    c = meta.Campaign(seed=5)
    node = c.known[0]
    for corp in meta.CORPS:
        c.exposure[corp] = meta.EXPOSURE_GOAL
    c.end_run(node, won_run(node, carried=0), publish=False)
    assert c.result == "won"
    assert c.targets() == []


def test_fallen_corps_stop_ticking_and_leave_the_map():
    c = meta.Campaign(seed=5)
    node = c.known[0]
    c.exposure[node.corp] = meta.EXPOSURE_GOAL
    c.end_run(node, won_run(node, carried=0), publish=False)
    assert c.clock[node.corp] == 0             # frozen at its setback
    assert node not in c.targets()


if __name__ == "__main__":
    checks = [v for k, v in sorted(globals().items())
              if k.startswith("test_")]
    for check in checks:
        check()
        print(f"ok  {check.__name__}")
    print(f"ALL {len(checks)} CHECKS PASSED")
