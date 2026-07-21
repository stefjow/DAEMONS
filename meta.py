"""DAEMONS meta-layer (DESIGN.md §5): the city map, corp clocks,
publish-or-fence. Campaign state that persists across runs.

Curses-free, like game.py — the campaign is drivable headless. The city
is a rhizome that draws itself: jacking out of a server spawns its
connected servers (deeper, richer, nastier); backdoor escapes reveal
secret edges two levels down.
"""

import random

from ice import ICE_POOL
from game import Run

CORPS = ("KERN", "INIT", "LIBC")
CLOCK_MAX = 15              # a corp finishing its project = campaign loss
EXPOSURE_GOAL = 6           # published files needed to take a corp down
FENCE_RATE = 2              # creds per fenced file
RUMOR_TRUTH = 0.7           # how often a node's ICE rumor is honest

HOSTS = ("darkstar", "mailhub", "ns1", "wopr", "buildfarm", "printq",
         "relay", "vault0", "timeshare", "devnull", "swapfile", "lpd",
         "uucp", "gopherd", "cvsroot", "nfs2", "modembank", "tapesilo")


class Node:
    """One corp server on the city map."""

    def __init__(self, corp, host, level, seed, rumor):
        self.corp = corp
        self.host = host
        self.level = level
        self.seed = seed        # fixed: revisiting a node replays its board
        self.rumor = rumor      # ring 0 ICE, RUMOR_TRUTH of the time
        self.raided = 0
        self.spawned = False    # children revealed yet?

    @property
    def name(self):
        return f"{self.corp.lower()}.{self.host}"


class Campaign:
    """City graph, corp clocks, exposure, and the runner's bank."""

    def __init__(self, seed=None):
        if seed is None:
            seed = random.randrange(10 ** 6)
        self.seed = seed
        self.rng = random.Random(seed)
        self.clock = {c: 0 for c in CORPS}
        self.exposure = {c: 0 for c in CORPS}
        self.bank = 0
        self.result = None      # None = live, else "won" / "lost"
        self.hosts_left = list(HOSTS)
        self.known = [self.new_node(corp, 1) for corp in CORPS]

    def new_node(self, corp, level):
        host = (self.hosts_left.pop(self.rng.randrange(len(self.hosts_left)))
                if self.hosts_left else f"node{self.rng.randrange(100)}")
        seed = self.rng.randrange(10 ** 6)
        # mirror of Run.__init__'s first rng draw, so an honest rumor is
        # exactly what the boot banner will say (see test_campaign)
        truth = random.Random(seed).choice(sorted(ICE_POOL))
        rumor = (truth if self.rng.random() < RUMOR_TRUTH
                 else self.rng.choice(sorted(ICE_POOL)))
        return Node(corp, host, level, seed, rumor)

    def fallen(self, corp):
        return self.exposure[corp] >= EXPOSURE_GOAL

    def targets(self):
        """Nodes that can still be raided (their corp is standing)."""
        return [n for n in self.known if not self.fallen(n.corp)]

    def start_run(self, node, loadout):
        return Run(level=node.level, seed=node.seed, loadout=loadout)

    def end_run(self, node, run, publish=False):
        """Bank or publish the haul, grow the map, tick every corp clock.
        Returns human-readable event lines for the city screen."""
        node.raided += 1
        events = []

        if run.won:
            if publish and run.carried:
                corp = node.corp
                self.clock[corp] = max(0, self.clock[corp] - run.carried)
                self.exposure[corp] += run.carried
                events.append(f"Published {run.carried} files — {corp} "
                              f"clock set back, exposure "
                              f"{self.exposure[corp]}/{EXPOSURE_GOAL}.")
                if self.fallen(corp):
                    events.append(f"{corp} COLLAPSES under the leaks. Its "
                                  f"servers go dark.")
            elif run.carried:
                self.bank += run.carried * FENCE_RATE
                events.append(f"Fenced {run.carried} files for "
                              f"{run.carried * FENCE_RATE} creds.")
            self.bank += run.creds_taken

            if not node.spawned:
                node.spawned = True
                for _ in range(self.rng.randint(1, 3)):
                    corp = (node.corp if self.rng.random() < 0.75
                            else self.rng.choice(CORPS))
                    child = self.new_node(corp, node.level + 1)
                    self.known.append(child)
                    events.append(f"Map: {node.name} links to {child.name} "
                                  f"(depth {child.level}).")
            if run.via == "a backdoor":
                secret = self.new_node(node.corp, node.level + 2)
                self.known.append(secret)
                events.append(f"Backdoor intel: secret edge to "
                              f"{secret.name} (depth {secret.level}).")
        else:
            self.bank = 0
            events.append("Runner flatlined. A new one picks up the deck — "
                          "the city remembers what you mapped.")

        # the run fee (DESIGN §5): every run, however shallow, ticks
        # every standing corp's project clock
        for corp in CORPS:
            if not self.fallen(corp):
                self.clock[corp] += 1
                if self.clock[corp] >= CLOCK_MAX:
                    self.result = "lost"
                    events.append(f"{corp} completes its project. "
                                  f"The city belongs to them now.")
        if all(self.fallen(c) for c in CORPS):
            self.result = "won"
            events.append("Every corp is rubble and headlines. You win.")
        return events
