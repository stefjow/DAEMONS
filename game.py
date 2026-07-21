"""DAEMONS rules engine: the board, the Run, the input dispatch.

No curses in here — everything is drivable headless, which is what the
deterministic replay tests (DESIGN.md §6) and the solution-string bot rely
on. Rendering and input live in ui.py; ring content and balance in ice.py;
the playable entry point is daemons.py.
"""

import random

from ice import ICE_POOL, ring0_spec, ring0_files, VISIBLE_FILES

BOARD_W = 40
BOARD_H = 20

BASE_HUNTERS = 6            # server 1; each deeper server adds more
HUNTERS_PER_LEVEL = 2
MAX_HUNTERS = 18
MIN_SPAWN_DIST = 8          # Chebyshev distance hunters keep from @ at spawn
TRACE_MAX = 100
WAVE_THRESHOLDS = (25, 50)  # spawn waves; 50% also wakes a hunter-killer
FLICKER_AT = 75             # the ring's port starts flickering...
FLICKER_TURNS = 12          # ...and seals this many turns later
MAX_WAVE = 6                # wave size grows with server level
BURN_SPAWN_EVERY = 3        # at 100% trace, continuous edge spawns
SENTRY_PERIOD = 4
DECOY_TTL = 3
MU_MAX = 4
ARCHIVE_TURNS = 2           # channel this many turns in place to extract
ARCHIVE_CREDS = 2           # a creds archive pays this much
TARBOMB_JUNK = 3            # tiles of junk burst around a tarbomb

NOISE_CROWBAR = 4
NOISE_EMP = 6
NOISE_TUNNEL = 3
NOISE_TRAP = 12

GLYPH_RUNNER = "@"
GLYPH_HUNTER = "+"
GLYPH_KILLER = "K"
GLYPH_JUNK = "▒"
GLYPH_WALL = "#"
GLYPH_GATE = "G"
GLYPH_STATIC = "~"
GLYPH_FILE = "¤"
GLYPH_CRED = "$"
GLYPH_TRAP = "☠"
GLYPH_DOOR = "◊"
GLYPH_HIDDEN = "?"
GLYPH_PORT = "⌂"
GLYPH_TUNNEL = "∩"
GLYPH_ARCHIVE = "≡"
GLYPH_FIFO_IN = "∩"
GLYPH_FIFO_OUT = "∪"

# program name -> (hotkey, MU, charges per run; None = unlimited/passive)
PROGRAMS = {
    "panic":   ("p", 1, 3, "kernel panic: random teleport; desperate"),
    "ssh":     ("c", 2, 1, "connect to any open tile: targeted teleport"),
    "fork":    ("f", 1, 2, "decoy child @; dumb hunters chase it 3 turns"),
    "sigstop": ("e", 2, 1, "freeze adjacent processes 1 turn; loud"),
    "rm -rf":  ("d", 1, 2, "delete one adjacent # or ▒; loud"),
    "sudo":    ("-", 1, None, "passive: walk through G permission gates"),
    "stat":    ("-", 1, None, "passive: adjacent ? identified free"),
    "socat":   ("t", 2, 2, "bind a tunnel end; 2 ends = 2-way passage"),
    "mkfifo":  ("m", 1, 2, "budget socat: one-way pipe, inlet ∩ → outlet ∪"),
}
DEFAULT_LOADOUT = ("panic", "stat", "socat")


def sign(n):
    return (n > 0) - (n < 0)


def cheb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


MOVES = {
    "h": (-1, 0), "l": (1, 0), "k": (0, -1), "j": (0, 1),
    "y": (-1, -1), "u": (1, -1), "b": (-1, 1), "n": (1, 1),
    "z": (-1, -1),   # QWERTZ: the key left of U types z, not y
    "4": (-1, 0), "6": (1, 0), "8": (0, -1), "2": (0, 1),
    "7": (-1, -1), "9": (1, -1), "1": (-1, 1), "3": (1, 1),
}
WAIT_KEYS = {".", "5"}


class Run:
    """One ring of a server: board state and the turn rules of DESIGN.md §3.

    A server is a stack of two rings. Ring 1 always runs plain crond; its
    down-port leads to ring 0, whose ICE (`self.next_ice`, drawn at ring-1
    creation so the stack is fixed by the seed) is revealed only by the
    boot banner at that port. Trace, loot, and charges are passed down."""

    def __init__(self, level=1, ring=1, ice="crond", next_ice=None,
                 loadout=DEFAULT_LOADOUT, charges=None, seed=None,
                 trace=0, carried=0, creds=0):
        if seed is None:
            seed = random.randrange(10 ** 6)
        self.seed = seed
        self.rng = random.Random(seed)
        self.level = level
        self.ring = ring
        self.ice = ice
        self.spec = ring0_spec(ice) if ring == 0 else None
        if ring > 0 and next_ice is None:
            next_ice = self.rng.choice(sorted(ICE_POOL))
        self.next_ice = next_ice
        self.trace_mult = self.spec["trace_mult"] if self.spec else 1
        self.turn = 0
        self.trace = trace
        self.carried = carried
        self.creds_taken = creds
        self.over = None            # None = live, else end-of-run message
        self.won = False
        if ring == 0:
            self.message = f"Ring 0 boots: {ice} — {ICE_POOL[ice]}."
        else:
            self.message = "Jack in. Grab the paydata, reach the port."
        # thresholds already passed on the way down stay burned (§3.4)
        self.waves_fired = {t for t in WAVE_THRESHOLDS if trace >= t}
        self.killer_woken = trace >= 50
        self.port_open = True
        self.port_timer = None      # counts down once trace >= FLICKER_AT

        if charges is None:
            charges = {name: PROGRAMS[name][2] for name in loadout}
        self.loadout = dict(charges)
        self.known_archives = set()
        self.channel = None         # (archive pos, channel turns still needed)
        self.tunnels = []
        self.fifos = []             # [inlet, outlet] — one-way
        self.decoy = None           # (pos, turns left)
        self.stunned = set()
        self.beams = set()          # tiles hit by sentry fire last world step
        self.junk = set()
        self.killers = set()

        self.wave_size = min(MAX_WAVE, 2 + (level - 1) // 2)
        self.gen_board()
        self.auto_stat()

    # -- board generation ----------------------------------------------------

    def gen_board(self):
        for _ in range(80):
            if self.try_gen():
                return
        raise SystemExit(f"daemons: board generation failed (seed {self.seed})")

    def try_gen(self):
        rng = self.rng
        W, H = BOARD_W, BOARD_H

        walls = set()
        for _ in range(rng.randint(7, 10)):
            length = rng.randint(3, 7)
            x, y = rng.randint(2, W - 3), rng.randint(2, H - 3)
            dx, dy = rng.choice(((1, 0), (0, 1)))
            walls |= {(x + dx * i, y + dy * i) for i in range(length)
                      if 1 <= x + dx * i < W - 1 and 1 <= y + dy * i < H - 1}

        # one gated vault: wall shell, G door, loot inside
        vx, vy = rng.randint(2, W - 8), rng.randint(2, H - 7)
        shell = {(x, y) for x in range(vx, vx + 5) for y in range(vy, vy + 4)
                 if x in (vx, vx + 4) or y in (vy, vy + 3)}
        vault = {(x, y) for x in range(vx + 1, vx + 4)
                 for y in range(vy + 1, vy + 3)}
        door = rng.choice([p for p in shell
                           if p[1] in (vy, vy + 3) and vx < p[0] < vx + 4])
        shell.discard(door)
        walls -= vault | {door}
        walls |= shell
        gates = {door}

        static = set()
        n_patches = 4 if self.ring == 0 and self.ice == "snortd" else 2
        for _ in range(n_patches):
            p = (rng.randint(3, W - 4), rng.randint(3, H - 4))
            for _ in range(rng.randint(8, 14)):
                if p not in walls and p not in gates and p not in vault:
                    static.add(p)
                p = (min(W - 2, max(1, p[0] + rng.randint(-1, 1))),
                     min(H - 2, max(1, p[1] + rng.randint(-1, 1))))

        solid = walls | gates
        floor = [(x, y) for x in range(W) for y in range(H)
                 if (x, y) not in solid and (x, y) not in vault]

        centre = [c for c in floor
                  if W // 4 <= c[0] < 3 * W // 4 and H // 4 <= c[1] < 3 * H // 4
                  and c not in static]
        if not centre:
            return False
        self.player = rng.choice(centre)
        taken = {self.player}

        def claim(pool):
            pool = [c for c in pool if c not in taken]
            if not pool:
                raise IndexError
            pos = rng.choice(pool)
            taken.add(pos)
            return pos

        try:
            self.port = claim([c for c in floor if cheb(c, self.player) >= 12])
            n_visible = VISIBLE_FILES + (1 if self.ring == 0 else 0)
            self.files = {claim([c for c in floor if c not in static])
                          for _ in range(n_visible)}

            if self.ring == 0:
                kinds = list(self.spec["kinds"])
            else:
                kinds = ["file", "file", "cred", "trap"]
                if self.level >= 3:
                    kinds.append("trap")
            if rng.random() < 0.35:
                kinds.append("door")
            self.hidden = {}
            for kind in kinds:
                pos = claim([c for c in floor
                             if cheb(c, self.player) >= 3 and c not in static])
                self.hidden[pos] = kind
            # vault loot is hidden too, and only reachable through the gate
            for kind in ("file", "cred"):
                self.hidden[claim(sorted(vault))] = kind
            self.revealed = {}

            # encrypted archives: contents unknown until scanned or opened
            self.archives = {}
            for _ in range(2 if self.ring == 0 else 1):
                pos = claim([c for c in floor
                             if cheb(c, self.player) >= 3 and c not in static])
                roll = rng.random()
                self.archives[pos] = ("tarbomb" if roll < 0.30 else
                                      "creds" if roll < 0.65 else "refill")

            n_sentries = min(3, (self.level >= 2) + (self.level >= 4)
                             + (self.level >= 7))
            if self.ring == 0:
                n_sentries = (3 if self.ice == "snortd"
                              else min(3, n_sentries + 1))
            self.sentries = []
            for _ in range(n_sentries):
                pos = claim([c for c in floor
                             if c not in static and cheb(c, self.player) >= 5])
                self.sentries.append({"pos": pos,
                                      "axis": rng.choice("hv"),
                                      "phase": rng.randrange(SENTRY_PERIOD)})

            count = min(MAX_HUNTERS,
                        BASE_HUNTERS + HUNTERS_PER_LEVEL * (self.level - 1)
                        + (self.spec["hunters"] if self.ring == 0 else 0))
            self.hunters = {
                claim([c for c in floor
                       if cheb(c, self.player) >= MIN_SPAWN_DIST])
                for _ in range(count)
            }

            # ring 0 killers: one if watchdogd is the ICE, one more if you
            # descended at >= 50% trace (the corp's K followed you down)
            self.killers = set()
            n_killers = ((self.ring == 0 and self.ice == "watchdogd")
                         + (self.ring == 0 and self.trace >= 50))
            for _ in range(n_killers):
                self.killers.add(
                    claim([c for c in floor
                           if cheb(c, self.player) >= MIN_SPAWN_DIST]))
        except IndexError:
            return False

        self.walls, self.gates, self.vault, self.static = (
            walls, gates, vault, static)
        # denominator = best possible count at the end of this ring
        self.total_files = self.carried + len(self.files) + sum(
            1 for k in self.hidden.values() if k == "file")

        # everything outside the vault must be reachable on foot
        reach = self.flood(self.player)
        need = ({self.port} | self.files | set(self.archives)
                | {p for p in self.hidden if p not in vault})
        return need <= reach and len(reach) > len(floor) * 0.7

    def flood(self, start):
        blocked = self.walls | self.gates | {s["pos"] for s in self.sentries}
        seen, front = {start}, [start]
        while front:
            x, y = front.pop()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    p = (x + dx, y + dy)
                    if (0 <= p[0] < BOARD_W and 0 <= p[1] < BOARD_H
                            and p not in blocked and p not in seen):
                        seen.add(p)
                        front.append(p)
        return seen

    # -- helpers ---------------------------------------------------------------

    def has(self, prog):
        charges = self.loadout.get(prog)
        if prog not in self.loadout:
            return False
        return charges is None or charges > 0

    def spend(self, prog):
        if self.loadout[prog] is not None:
            self.loadout[prog] -= 1

    def add_trace(self, n):
        self.trace = min(TRACE_MAX, self.trace + n * self.trace_mult)

    def port_message(self):
        """The line shown while standing on this ring's port."""
        if not self.port_open:
            return "The port is dead. Find a backdoor or fry."
        if self.ring > 0:
            return (f"boot: {self.next_ice} — {ICE_POOL[self.next_ice]} — "
                    f"¤×{ring0_files(self.next_ice)}   [>] dive  [<] out")
        return "Root port. [<] jack out with everything you carry."

    def can_enter(self, pos):
        if not (0 <= pos[0] < BOARD_W and 0 <= pos[1] < BOARD_H):
            return False
        if pos in self.walls or pos in self.junk:
            return False
        if pos in {s["pos"] for s in self.sentries}:
            return False
        if pos in self.gates and not self.has("sudo"):
            return False
        return True

    def blocks_beam(self, pos):
        return (pos in self.walls or pos in self.junk or pos in self.static
                or pos in self.gates
                or pos in {s["pos"] for s in self.sentries})

    def beam_tiles(self, sentry):
        sx, sy = sentry["pos"]
        deltas = ((1, 0), (-1, 0)) if sentry["axis"] == "h" else ((0, 1), (0, -1))
        tiles = set()
        for dx, dy in deltas:
            x, y = sx + dx, sy + dy
            while 0 <= x < BOARD_W and 0 <= y < BOARD_H \
                    and not self.blocks_beam((x, y)):
                tiles.add((x, y))
                x, y = x + dx, y + dy
        return tiles

    def sentry_countdown(self, sentry):
        """Turns until this sentry fires; 0 = fires on the coming step."""
        return (-(self.turn + sentry["phase"])) % SENTRY_PERIOD

    def auto_stat(self):
        if not self.has("stat"):
            return
        for pos in [p for p in self.hidden if cheb(p, self.player) <= 1]:
            self.revealed[pos] = self.hidden.pop(pos)
        self.known_archives |= {p for p in self.archives
                                if cheb(p, self.player) <= 1}

    def die(self, why):
        self.won = False
        self.over = f"FLATLINED — {why} (seed {self.seed})"

    def jack_out(self, how=None):
        if how is None:
            how = f"the ring {self.ring} port"
        self.won = True
        self.over = (f"JACKED OUT via {how} — {self.carried} file"
                     f"{'s' if self.carried != 1 else ''}, "
                     f"{self.creds_taken} cred, trace {self.trace}%.")

    # -- player actions ----------------------------------------------------------

    def act(self, dx, dy):
        if self.over:
            return
        nx, ny = self.player[0] + dx, self.player[1] + dy
        if not self.can_enter((nx, ny)):
            if (nx, ny) in self.gates:
                self.message = "Permission denied. You need sudo."
            else:
                self.message = "Blocked."
            return
        self.player = (nx, ny)
        self.message = ""
        self.resolve("You walked into a hunter process.", moved=True)

    def act_scan(self):
        if self.over:
            return
        found = [p for p in self.hidden if cheb(p, self.player) <= 1]
        arch = [p for p in self.archives if cheb(p, self.player) <= 1
                and p not in self.known_archives]
        if not found and not arch:
            self.message = "Nothing unscanned in reach."
            return
        for pos in found:
            self.revealed[pos] = self.hidden.pop(pos)
        self.known_archives |= set(arch)
        names = ([self.revealed[p] for p in found]
                 + [f"archive: {self.archives[p]}" for p in arch])
        self.message = "Scan: " + ", ".join(names) + "."
        self.world_step()

    def act_panic(self):
        if self.over:
            return
        if not self.has("panic"):
            self.message = "panic: no charges left."
            return
        self.spend("panic")
        self.player = self.rng.choice(
            [(x, y) for x in range(BOARD_W) for y in range(BOARD_H)
             if self.can_enter((x, y))])
        self.message = f"kernel panic — {self.loadout['panic']} left."
        self.resolve("you teleported into a hunter process.", moved=False)

    def act_ssh(self, target):
        if self.over:
            return
        if not self.has("ssh"):
            self.message = "ssh: no charges left."
            return
        if (not self.can_enter(target) or target in self.hunters
                or target in self.killers):
            self.message = "ssh: connection refused."
            return
        self.spend("ssh")
        self.player = target
        self.message = "ssh: session opened."
        self.resolve("ssh misfire.", moved=False)

    def act_fork(self):
        if self.over:
            return
        if not self.has("fork"):
            self.message = "fork: no charges left."
            return
        self.spend("fork")
        self.decoy = (self.player, DECOY_TTL)
        self.message = "fork: child process spawned on your tile. Move!"
        self.world_step()

    def act_sigstop(self):
        if self.over:
            return
        if not self.has("sigstop"):
            self.message = "sigstop: no charges left."
            return
        self.spend("sigstop")
        self.stunned = {h for h in self.hunters | self.killers
                        if cheb(h, self.player) <= 1}
        self.add_trace(NOISE_EMP)
        self.message = (f"SIGSTOP sent — {len(self.stunned)} processes "
                        f"frozen. Loud.")
        self.world_step()

    def act_rm(self, dx, dy):
        if self.over:
            return
        if not self.has("rm -rf"):
            self.message = "rm -rf: no charges left."
            return
        target = (self.player[0] + dx, self.player[1] + dy)
        if target in self.walls and target not in self.vault_shell():
            self.walls.discard(target)
        elif target in self.walls:
            self.message = "rm -rf: vault plating is write-protected."
            return
        elif target in self.junk:
            self.junk.discard(target)
        else:
            self.message = "rm -rf: no such obstacle."
            return
        self.spend("rm -rf")
        self.add_trace(NOISE_CROWBAR)
        self.message = "rm -rf: deleted. Loud."
        self.world_step()

    def vault_shell(self):
        return {p for p in self.walls
                if any(cheb(p, v) <= 1 for v in self.vault)}

    def act_socat(self):
        if self.over:
            return
        if not self.has("socat"):
            self.message = "socat: no charges left."
            return
        if self.tile_occupied(self.player):
            self.message = "socat: address already in use."
            return
        self.spend("socat")
        self.tunnels.append(self.player)
        linked = " Link established." if len(self.tunnels) == 2 else ""
        self.message = f"socat: endpoint bound.{linked}"
        self.world_step()

    def act_mkfifo(self):
        if self.over:
            return
        if not self.has("mkfifo"):
            self.message = "mkfifo: no charges left."
            return
        if len(self.fifos) == 2:
            self.message = "mkfifo: pipe already open."
            return
        if self.tile_occupied(self.player):
            self.message = "mkfifo: address already in use."
            return
        self.spend("mkfifo")
        self.fifos.append(self.player)
        self.message = ("mkfifo: outlet bound — pipe open, one-way."
                        if len(self.fifos) == 2 else "mkfifo: inlet bound.")
        self.world_step()

    def tile_occupied(self, pos):
        return (pos in self.hidden or pos in self.revealed
                or pos in self.files or pos == self.port
                or pos in self.tunnels or pos in self.fifos
                or pos in self.archives or pos in self.gates)

    def act_extract(self):
        """Channel ARCHIVE_TURNS in place on an archive; any other action
        breaks the channel (dispatch resets it). Hunters keep coming."""
        if self.over:
            return
        pos = self.player
        if pos not in self.archives:
            self.message = "tar: no archive here."
            return
        left = (self.channel[1] if self.channel and self.channel[0] == pos
                else ARCHIVE_TURNS) - 1
        if left > 0:
            self.channel = (pos, left)
            self.message = f"tar -x: extracting… {left} more turn. Hold."
            self.world_step()
            return
        self.channel = None
        kind = self.archives.pop(pos)
        self.known_archives.discard(pos)
        if kind == "creds":
            self.creds_taken += ARCHIVE_CREDS
            self.message = f"Archive open: {ARCHIVE_CREDS} cred inside."
        elif kind == "refill":
            prog = next((n for n, c in self.loadout.items()
                         if c is not None and c < PROGRAMS[n][2]), None)
            if prog:
                self.loadout[prog] = PROGRAMS[prog][2]
                self.message = f"Archive open: {prog} charges refilled."
            else:
                self.creds_taken += 1
                self.message = "Archive open: spare parts — 1 cred."
        else:  # tarbomb
            self.add_trace(NOISE_TRAP)
            keep = (self.files | set(self.hidden) | set(self.revealed)
                    | set(self.archives) | set(self.tunnels)
                    | set(self.fifos) | {self.port}
                    | self.hunters | self.killers)
            free = [(pos[0] + dx, pos[1] + dy)
                    for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                    if (dx, dy) != (0, 0)
                    and self.can_enter((pos[0] + dx, pos[1] + dy))
                    and (pos[0] + dx, pos[1] + dy) not in keep]
            for p in self.rng.sample(free, min(TARBOMB_JUNK, len(free))):
                self.junk.add(p)
            self.spawn_wave(2)
            self.message = ("TARBOMB! Junk bursts around you and the trace "
                            "spikes.")
        self.world_step()

    # -- landing on a tile -----------------------------------------------------

    def resolve(self, contact_death, moved):
        """Everything that happens after the runner lands on a tile."""
        if self.player in self.hunters or self.player in self.killers:
            return self.die(contact_death)

        if moved and len(self.tunnels) == 2 and self.player in self.tunnels:
            other = self.tunnels[1 - self.tunnels.index(self.player)]
            self.player = other
            self.add_trace(NOISE_TUNNEL)
            self.message = "Through the tunnel. Loud."
            if self.player in self.hunters or self.player in self.killers:
                return self.die("a hunter was waiting at the tunnel mouth.")

        # a fifo pipe only flows inlet -> outlet; the outlet is plain floor
        if moved and len(self.fifos) == 2 and self.player == self.fifos[0]:
            self.player = self.fifos[1]
            self.add_trace(NOISE_TUNNEL)
            self.message = "Through the pipe. Loud."
            if self.player in self.hunters or self.player in self.killers:
                return self.die("a hunter was waiting at the pipe mouth.")

        pos = self.player
        kind = self.hidden.pop(pos, None) or self.revealed.pop(pos, None)
        if kind == "file":
            self.carried += 1
            self.message = f"Paydata secured ({self.carried})."
        elif kind == "cred":
            self.creds_taken += 1
            self.message = "Credits siphoned."
        elif kind == "trap":
            self.add_trace(NOISE_TRAP)
            self.message = (f"SNARE! Trace spikes "
                            f"+{NOISE_TRAP * self.trace_mult} and you reel.")
            self.step_hunters()      # the stumble: hunters get a free step
            if self.over:
                return
        elif kind == "door":
            return self.jack_out("a backdoor")

        if pos in self.files:
            self.files.discard(pos)
            self.carried += 1
            self.message = f"Paydata secured ({self.carried})."
        # landing on the port ends nothing: descending and jacking out are
        # explicit choices (> / <), made while hunters keep coming

        self.world_step()

    # -- world response ----------------------------------------------------------

    def world_step(self):
        self.beams = set()
        self.step_hunters()
        if self.over:
            return
        self.step_killers()
        if self.over:
            return
        self.tick_sentries()
        if self.over:
            return
        self.tick_trace()
        if self.over:
            return
        if self.decoy:
            pos, ttl = self.decoy
            self.decoy = (pos, ttl - 1) if ttl > 1 else None
        self.stunned = set()
        self.auto_stat()

    def step_hunters(self):
        """Classic Robots rule: every hunter takes one sign-step toward its
        target (the decoy, if one is live). Same-tile arrivals crash into
        junk; stepping into junk is fatal; walls just stop them."""
        tx, ty = self.decoy[0] if self.decoy else self.player
        blocked = self.walls | self.gates | {s["pos"] for s in self.sentries}

        def open_tile(p):
            return (0 <= p[0] < BOARD_W and 0 <= p[1] < BOARD_H
                    and p not in blocked)

        arrivals = {}
        for hx, hy in self.hunters:
            dx, dy = sign(tx - hx), sign(ty - hy)
            if (hx, hy) in self.stunned:
                dest = (hx, hy)
            else:
                # slide along walls: full step, else each axis alone
                for step in ((hx + dx, hy + dy), (hx + dx, hy), (hx, hy + dy)):
                    if step != (hx, hy) and open_tile(step):
                        dest = step
                        break
                else:
                    dest = (hx, hy)
            arrivals.setdefault(dest, 0)
            arrivals[dest] += 1

        survivors = set()
        for dest, count in arrivals.items():
            if dest == self.player:
                return self.die("a hunter caught you.")
            if (dest in self.junk or count > 1
                    or (self.decoy and dest == self.decoy[0])):
                self.junk.add(dest)
            else:
                survivors.add(dest)
        self.hunters = survivors - self.junk

    def step_killers(self):
        """Hunter-killers pathfind (BFS) around junk, walls, and gates."""
        for k in sorted(self.killers):
            if k in self.stunned:
                continue
            step = self.path_step(k, self.player)
            if step is None:
                continue
            if step == self.player:
                return self.die("the hunter-killer ran you down.")
            self.killers.discard(k)
            self.killers.add(step)

    def path_step(self, start, goal):
        blocked = (self.walls | self.gates | self.junk
                   | {s["pos"] for s in self.sentries})
        prev = {start: None}
        front = [start]
        while front:
            nxt = []
            for x, y in front:
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        p = (x + dx, y + dy)
                        if (p not in prev and 0 <= p[0] < BOARD_W
                                and 0 <= p[1] < BOARD_H and p not in blocked):
                            prev[p] = (x, y)
                            if p == goal:
                                while prev[p] != start:
                                    p = prev[p]
                                return p
                            nxt.append(p)
            front = nxt
        return None

    def tick_sentries(self):
        for s in self.sentries:
            if (self.turn + s["phase"]) % SENTRY_PERIOD == 0:
                self.beams |= self.beam_tiles(s)
        if self.beams:
            self.hunters -= self.beams
            self.killers -= self.beams
            if self.player in self.beams:
                return self.die("a sentry burst caught you.")

    def tick_trace(self):
        self.turn += 1
        self.add_trace(1)
        for t in WAVE_THRESHOLDS:
            if self.trace >= t and t not in self.waves_fired:
                self.waves_fired.add(t)
                self.spawn_wave(self.wave_size)
                self.message = f"TRACE {t}% — new hunters flood the edges!"
        if self.trace >= 50 and not self.killer_woken:
            self.killer_woken = True
            self.spawn_killer()
            self.message = "TRACE 50% — a hunter-killer wakes. It pathfinds."
        if self.trace >= FLICKER_AT and self.port_timer is None \
                and self.port_open:
            self.port_timer = FLICKER_TURNS
            self.message = (f"TRACE {FLICKER_AT}% — the port flickers: "
                            f"{FLICKER_TURNS} turns before it seals!")
        elif self.port_timer is not None and self.port_open:
            self.port_timer -= 1
            if self.port_timer <= 0:
                self.port_open = False
                self.message = "The port seals. Find a backdoor or fry."
        if self.trace >= TRACE_MAX and self.turn % BURN_SPAWN_EVERY == 0:
            self.spawn_wave(1)
            self.message = "TRACE 100% — they keep coming. Get out NOW."

    def edge_spawn_tiles(self):
        return [(x, y) for x in range(BOARD_W) for y in range(BOARD_H)
                if (x in (0, BOARD_W - 1) or y in (0, BOARD_H - 1))
                and self.can_enter((x, y)) and (x, y) != self.player
                and cheb((x, y), self.player) >= 4]

    def spawn_wave(self, n):
        edges = self.edge_spawn_tiles()
        for pos in self.rng.sample(edges, min(n, len(edges))):
            self.hunters.add(pos)

    def spawn_killer(self):
        edges = self.edge_spawn_tiles()
        if edges:
            self.killers.add(self.rng.choice(edges))


def dispatch(run, key, aux=None):
    """The real input dispatch (DESIGN.md §6): apply one input to a live
    run. aux is the second half of a two-step command — a (dx, dy)
    direction for rm -rf, a target tile for ssh — supplied by the UI
    prompts in main() or verbatim by scripted replays. Returns the active
    run: descending through a down-port returns the freshly booted ring 0."""
    if run.over:
        return run
    if key != "x":
        run.channel = None      # channeling breaks on any other action
    if key == ">":
        if run.player != run.port or not run.port_open:
            run.message = "descend: you need to stand on an open port."
        elif run.ring == 0:
            run.message = "Nothing runs deeper than ring 0."
        else:
            return Run(level=run.level, ring=0, ice=run.next_ice,
                       charges=run.loadout,
                       seed=run.rng.randrange(10 ** 6),
                       trace=run.trace, carried=run.carried,
                       creds=run.creds_taken)
    elif key == "<":
        if run.player == run.port and run.port_open:
            run.jack_out()
        else:
            run.message = "jack out: you need to stand on an open port."
    elif key in WAIT_KEYS:
        run.act(0, 0)
    elif key == "s":
        run.act_scan()
    elif key == "p":
        run.act_panic()
    elif key == "f":
        run.act_fork()
    elif key == "e":
        run.act_sigstop()
    elif key == "t":
        run.act_socat()
    elif key == "m":
        run.act_mkfifo()
    elif key == "x":
        run.act_extract()
    elif key == "c" and aux is not None:
        run.act_ssh(aux)
    elif key == "d" and aux is not None:
        run.act_rm(*aux)
    elif key in MOVES:
        run.act(*MOVES[key])
    return run


