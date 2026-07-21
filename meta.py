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
INTEL_PRICE = 3             # what the fixer charges to name a node's ICE

HOSTS = ("darkstar", "mailhub", "ns1", "wopr", "buildfarm", "printq",
         "relay", "vault0", "timeshare", "devnull", "swapfile", "lpd",
         "uucp", "gopherd", "cvsroot", "nfs2", "modembank", "tapesilo")


class Node:
    """One corp server on the city map. Its ring-0 ICE (`ice`) is the
    truth, but the map only shows it once `known` — earned by reading
    the boot banner, decrypting looted intel, or paying the fixer."""

    def __init__(self, corp, host, level, seed, ice):
        self.corp = corp
        self.host = host
        self.level = level
        self.seed = seed        # fixed: revisiting a node replays its board
        self.ice = ice
        self.known = False
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
        # mirror of Run.__init__'s first rng draw, so intel and the boot
        # banner always agree (see test_campaign)
        ice = random.Random(seed).choice(sorted(ICE_POOL))
        return Node(corp, host, level, seed, ice)

    def buy_intel(self, node):
        """The fixer names a node's ring-0 ICE, for a price."""
        if node.known:
            return f"You already know {node.name}'s stack."
        if self.bank < INTEL_PRICE:
            return f"Fixer wants {INTEL_PRICE} creds. You're short."
        self.bank -= INTEL_PRICE
        node.known = True
        return f"Fixer: {node.name} ring 0 runs {node.ice}."

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

        # reading the boot banner can't be undone, not even by dying:
        # the player saw ring 0's ICE with their own eyes
        if run.ring == 0 or run.banner_seen:
            node.known = True

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

            # looted intel files decrypt now — each names another
            # server's ICE, this corp's network first
            for _ in range(run.intel_found):
                pool = ([n for n in self.known
                         if not n.known and n.corp == node.corp]
                        or [n for n in self.known if not n.known])
                if pool:
                    hit = self.rng.choice(pool)
                    hit.known = True
                    events.append(f"Intel decrypted: {hit.name} ring 0 "
                                  f"runs {hit.ice}.")
                else:
                    self.bank += 1
                    events.append("Intel was stale — fenced for 1 cred.")
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
