#!/usr/bin/env python3
"""DAEMONS v1 — ICE & programs.

The v1 milestone from DESIGN.md §7: barrier ICE, sentries + static fields,
code gates, `?` scanning (with rare backdoors), traps, the starter program
suite with tunnel.exe, and an MU loadout screen. Runs are seeded and
deterministic (§6).

Run:  python3 daemons.py

Movement (8-directional; z = y for QWERTZ; arrows for the cardinals):
      y k u     7 8 9
      h . l     4 . 6        . or 5 = wait
      b j n     1 2 3

Actions:
      s   scan adjacent `?` tiles (costs a turn; free & automatic with
          probe.exe equipped)
Programs (must be equipped, consume charges):
      p   panic.exe    random teleport — can land you next to, or on,
                       a hunter; desperation only
      f   blink.exe    targeted teleport: move the cursor, f/enter to jump,
                       escape to cancel
      d   decoy.exe    drop a fake signal on your tile; dumb hunters chase
                       it 3 turns and crash into it
      e   emp.exe      stun all adjacent hunters 1 turn (loud)
      c   crowbar.exe  then a direction: smash an adjacent # or ▒ (loud)
      t   tunnel.exe   plant a tunnel end; two ends link into a two-way,
                       hunter-proof passage (travel is loud)
      gatekey.exe / probe.exe are passive while equipped.

      r   continue (after a run ends): next server if you jacked out,
          back to server 1 if you flatlined
      q   quit

Each server you jack out of leads to a deeper one. Death sends you back to
server 1 with an empty bank.
"""

import curses
import locale
import random

BOARD_W = 40
BOARD_H = 20

BASE_HUNTERS = 6            # server 1; each deeper server adds more
HUNTERS_PER_LEVEL = 2
MAX_HUNTERS = 18
MIN_SPAWN_DIST = 8          # Chebyshev distance hunters keep from @ at spawn
VISIBLE_FILES = 2
TRACE_MAX = 100
WAVE_THRESHOLDS = (25, 50)  # spawn waves; 50% also wakes a hunter-killer
FLICKER_AT = 75             # exit starts flickering...
FLICKER_TURNS = 12          # ...and closes this many turns later
MAX_WAVE = 6                # wave size grows with server level
BURN_SPAWN_EVERY = 3        # at 100% trace, continuous edge spawns
SENTRY_PERIOD = 4
DECOY_TTL = 3
MU_MAX = 4

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
GLYPH_EXIT = "⌂"
GLYPH_TUNNEL = "∩"

# program name -> (hotkey, MU, charges per run; None = unlimited/passive)
PROGRAMS = {
    "panic.exe":   ("p", 1, 3, "random teleport; desperate"),
    "blink.exe":   ("f", 2, 1, "targeted teleport to any open tile"),
    "decoy.exe":   ("d", 1, 2, "fake @; dumb hunters chase it 3 turns"),
    "emp.exe":     ("e", 2, 1, "stun adjacent hunters 1 turn; loud"),
    "crowbar.exe": ("c", 1, 2, "smash one adjacent # or ▒; loud"),
    "gatekey.exe": ("g", 1, None, "passive: walk through G code gates"),
    "probe.exe":   ("o", 1, None, "passive: adjacent ? auto-scanned free"),
    "tunnel.exe":  ("t", 2, 2, "plant a tunnel end; 2 ends = 2-way passage"),
}
DEFAULT_LOADOUT = ("panic.exe", "probe.exe", "tunnel.exe")


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
    curses.KEY_LEFT: (-1, 0), curses.KEY_RIGHT: (1, 0),
    curses.KEY_UP: (0, -1), curses.KEY_DOWN: (0, 1),
}
WAIT_KEYS = {".", "5"}


class Run:
    """One server run: board state and the turn rules of DESIGN.md §3."""

    def __init__(self, level=1, loadout=DEFAULT_LOADOUT, seed=None):
        if seed is None:
            seed = random.randrange(10 ** 6)
        self.seed = seed
        self.rng = random.Random(seed)
        self.level = level
        self.turn = 0
        self.trace = 0
        self.carried = 0
        self.creds_taken = 0
        self.over = None            # None = live, else end-of-run message
        self.won = False
        self.message = "Jack in. Grab the paydata, reach the exit port."
        self.waves_fired = set()
        self.killer_woken = False
        self.exit_open = True
        self.exit_timer = None      # counts down once trace >= FLICKER_AT

        self.loadout = {name: PROGRAMS[name][2] for name in loadout}
        self.tunnels = []
        self.decoy = None           # (pos, turns left)
        self.stunned = set()
        self.beams = set()          # tiles hit by sentry fire last world step
        self.junk = set()
        self.killers = set()

        self.wave_size = min(MAX_WAVE, 2 + (level - 1) // 2)
        self.gen_board()
        self.auto_probe()

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
        for _ in range(2):
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
            self.exit = claim([c for c in floor if cheb(c, self.player) >= 12])
            self.files = {claim([c for c in floor if c not in static])
                          for _ in range(VISIBLE_FILES)}

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

            n_sentries = min(3, (self.level >= 2) + (self.level >= 4)
                             + (self.level >= 7))
            self.sentries = []
            for _ in range(n_sentries):
                pos = claim([c for c in floor
                             if c not in static and cheb(c, self.player) >= 5])
                self.sentries.append({"pos": pos,
                                      "axis": rng.choice("hv"),
                                      "phase": rng.randrange(SENTRY_PERIOD)})

            count = min(MAX_HUNTERS,
                        BASE_HUNTERS + HUNTERS_PER_LEVEL * (self.level - 1))
            self.hunters = {
                claim([c for c in floor
                       if cheb(c, self.player) >= MIN_SPAWN_DIST])
                for _ in range(count)
            }
        except IndexError:
            return False

        self.walls, self.gates, self.vault, self.static = (
            walls, gates, vault, static)
        self.total_files = VISIBLE_FILES + sum(
            1 for k in self.hidden.values() if k == "file")

        # everything outside the vault must be reachable on foot
        reach = self.flood(self.player)
        need = ({self.exit} | self.files
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

    def can_enter(self, pos):
        if not (0 <= pos[0] < BOARD_W and 0 <= pos[1] < BOARD_H):
            return False
        if pos in self.walls or pos in self.junk:
            return False
        if pos in {s["pos"] for s in self.sentries}:
            return False
        if pos in self.gates and not self.has("gatekey.exe"):
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

    def auto_probe(self):
        if not self.has("probe.exe"):
            return
        for pos in [p for p in self.hidden if cheb(p, self.player) <= 1]:
            self.revealed[pos] = self.hidden.pop(pos)

    def die(self, why):
        self.won = False
        self.over = f"FLATLINED — {why} (seed {self.seed})"

    def jack_out(self, how="the exit port"):
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
                self.message = "A code gate. You need gatekey.exe."
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
        if not found:
            self.message = "Nothing unscanned in reach."
            return
        for pos in found:
            self.revealed[pos] = self.hidden.pop(pos)
        self.message = "Scan: " + ", ".join(
            self.revealed[p] for p in found) + "."
        self.world_step()

    def act_panic(self):
        if self.over:
            return
        if not self.has("panic.exe"):
            self.message = "panic.exe: no charges left."
            return
        self.spend("panic.exe")
        self.player = self.rng.choice(
            [(x, y) for x in range(BOARD_W) for y in range(BOARD_H)
             if self.can_enter((x, y))])
        self.message = f"panic.exe fired — {self.loadout['panic.exe']} left."
        self.resolve("you teleported into a hunter process.", moved=False)

    def act_blink(self, target):
        if self.over:
            return
        if not self.has("blink.exe"):
            self.message = "blink.exe: no charges left."
            return
        if (not self.can_enter(target) or target in self.hunters
                or target in self.killers):
            self.message = "blink.exe: can't land there."
            return
        self.spend("blink.exe")
        self.player = target
        self.message = "blink.exe: relocated."
        self.resolve("blink misfire.", moved=False)

    def act_decoy(self):
        if self.over:
            return
        if not self.has("decoy.exe"):
            self.message = "decoy.exe: no charges left."
            return
        self.spend("decoy.exe")
        self.decoy = (self.player, DECOY_TTL)
        self.message = "decoy.exe: a fake signal blooms on your tile. Move!"
        self.world_step()

    def act_emp(self):
        if self.over:
            return
        if not self.has("emp.exe"):
            self.message = "emp.exe: no charges left."
            return
        self.spend("emp.exe")
        self.stunned = {h for h in self.hunters | self.killers
                        if cheb(h, self.player) <= 1}
        self.trace = min(TRACE_MAX, self.trace + NOISE_EMP)
        self.message = f"emp.exe: {len(self.stunned)} stunned. Loud."
        self.world_step()

    def act_crowbar(self, dx, dy):
        if self.over:
            return
        if not self.has("crowbar.exe"):
            self.message = "crowbar.exe: no charges left."
            return
        target = (self.player[0] + dx, self.player[1] + dy)
        if target in self.walls and target not in self.vault_shell():
            self.walls.discard(target)
        elif target in self.walls:
            self.message = "crowbar.exe: vault plating is too hard."
            return
        elif target in self.junk:
            self.junk.discard(target)
        else:
            self.message = "crowbar.exe: nothing to smash there."
            return
        self.spend("crowbar.exe")
        self.trace = min(TRACE_MAX, self.trace + NOISE_CROWBAR)
        self.message = "crowbar.exe: smashed. Loud."
        self.world_step()

    def vault_shell(self):
        return {p for p in self.walls
                if any(cheb(p, v) <= 1 for v in self.vault)}

    def act_tunnel(self):
        if self.over:
            return
        if not self.has("tunnel.exe"):
            self.message = "tunnel.exe: no charges left."
            return
        pos = self.player
        occupied = (pos in self.hidden or pos in self.revealed
                    or pos in self.files or pos == self.exit
                    or pos in self.tunnels or pos in self.gates)
        if occupied:
            self.message = "tunnel.exe: can't plant here."
            return
        self.spend("tunnel.exe")
        self.tunnels.append(pos)
        linked = " Link established." if len(self.tunnels) == 2 else ""
        self.message = f"tunnel.exe: end planted.{linked}"
        self.world_step()

    # -- landing on a tile -----------------------------------------------------

    def resolve(self, contact_death, moved):
        """Everything that happens after the runner lands on a tile."""
        if self.player in self.hunters or self.player in self.killers:
            return self.die(contact_death)

        if moved and len(self.tunnels) == 2 and self.player in self.tunnels:
            other = self.tunnels[1 - self.tunnels.index(self.player)]
            self.player = other
            self.trace = min(TRACE_MAX, self.trace + NOISE_TUNNEL)
            self.message = "Through the tunnel. Loud."
            if self.player in self.hunters or self.player in self.killers:
                return self.die("a hunter was waiting at the tunnel mouth.")

        pos = self.player
        kind = self.hidden.pop(pos, None) or self.revealed.pop(pos, None)
        if kind == "file":
            self.carried += 1
            self.message = f"Paydata secured ({self.carried})."
        elif kind == "cred":
            self.creds_taken += 1
            self.message = "Credits siphoned."
        elif kind == "trap":
            self.trace = min(TRACE_MAX, self.trace + NOISE_TRAP)
            self.message = f"SNARE! Trace spikes +{NOISE_TRAP} and you reel."
            self.step_hunters()      # the stumble: hunters get a free step
            if self.over:
                return
        elif kind == "door":
            return self.jack_out("a backdoor")

        if pos in self.files:
            self.files.discard(pos)
            self.carried += 1
            self.message = f"Paydata secured ({self.carried})."
        if pos == self.exit:
            if self.exit_open:
                return self.jack_out()
            self.message = "The exit port is dead. Find a backdoor or fry."

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
        self.auto_probe()

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
        self.trace = min(TRACE_MAX, self.trace + 1)
        for t in WAVE_THRESHOLDS:
            if self.trace >= t and t not in self.waves_fired:
                self.waves_fired.add(t)
                self.spawn_wave(self.wave_size)
                self.message = f"TRACE {t}% — new hunters flood the edges!"
        if self.trace >= 50 and not self.killer_woken:
            self.killer_woken = True
            self.spawn_killer()
            self.message = "TRACE 50% — a hunter-killer wakes. It pathfinds."
        if self.trace >= FLICKER_AT and self.exit_timer is None \
                and self.exit_open:
            self.exit_timer = FLICKER_TURNS
            self.message = (f"TRACE {FLICKER_AT}% — the exit port flickers: "
                            f"{FLICKER_TURNS} turns before it dies!")
        elif self.exit_timer is not None and self.exit_open:
            self.exit_timer -= 1
            if self.exit_timer <= 0:
                self.exit_open = False
                self.message = "The exit port goes dark."
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


# -- rendering -----------------------------------------------------------------

COLORS = {}


def init_colors():
    if not curses.has_colors():
        return
    curses.start_color()
    curses.use_default_colors()
    for i, (name, fg) in enumerate(
            [("threat", curses.COLOR_RED), ("loot", curses.COLOR_YELLOW),
             ("exit", curses.COLOR_GREEN), ("static", curses.COLOR_CYAN),
             ("unknown", curses.COLOR_MAGENTA)], start=1):
        curses.init_pair(i, fg, -1)
        COLORS[name] = curses.color_pair(i)


def col(name, extra=0):
    return COLORS.get(name, 0) | extra


def draw(scr, run, bank):
    scr.erase()
    oy, ox = 1, 2

    def put(pos, ch, attr=0):
        scr.addstr(oy + pos[1], ox + pos[0], ch, attr)

    for x in range(BOARD_W):
        for y in range(BOARD_H):
            put((x, y), "·", curses.A_DIM)
    for p in run.static:
        put(p, GLYPH_STATIC, col("static", curses.A_DIM))
    for p in run.walls:
        put(p, GLYPH_WALL)
    for p in run.gates:
        put(p, GLYPH_GATE, curses.A_BOLD)
    for s in run.sentries:
        if run.beams:
            ch = "═" if s["axis"] == "h" else "║"
            for p in run.beam_tiles(s) & run.beams:
                put(p, ch, col("threat", curses.A_BOLD))
    for p in run.junk:
        put(p, GLYPH_JUNK)
    for p in run.tunnels:
        put(p, GLYPH_TUNNEL, curses.A_BOLD)
    for p in run.files:
        put(p, GLYPH_FILE, col("loot", curses.A_BOLD))
    for p, kind in run.revealed.items():
        glyph = {"file": GLYPH_FILE, "cred": GLYPH_CRED,
                 "trap": GLYPH_TRAP, "door": GLYPH_DOOR}[kind]
        name = "threat" if kind == "trap" else "loot"
        put(p, glyph, col(name, curses.A_BOLD))
    for p in run.hidden:
        put(p, GLYPH_HIDDEN, col("unknown", curses.A_BOLD))
    if run.exit_open:
        blink = curses.A_BLINK if run.exit_timer is not None else 0
        put(run.exit, GLYPH_EXIT, col("exit", curses.A_BOLD | blink))
    for s in run.sentries:
        cd = run.sentry_countdown(s)
        ch = "!" if cd == 0 else str(cd)
        put(s["pos"], ch, col("threat", curses.A_BOLD))
    if run.decoy:
        put(run.decoy[0], GLYPH_RUNNER, curses.A_DIM)
    for p in run.hunters:
        put(p, GLYPH_HUNTER)
    for p in run.killers:
        put(p, GLYPH_KILLER, col("threat", curses.A_BOLD))
    put(run.player, GLYPH_RUNNER, curses.A_BOLD)

    bar_w = 20
    filled = run.trace * bar_w // TRACE_MAX
    hud = (f"SRV {run.level}   "
           f"TRACE [{'#' * filled}{'-' * (bar_w - filled)}] {run.trace:3d}%   "
           f"FILES {run.carried}/{run.total_files}   "
           f"CRED {run.creds_taken}   BANK {bank}")
    scr.addstr(oy + BOARD_H + 1, ox, hud)

    rig = []
    for name, charges in run.loadout.items():
        key = PROGRAMS[name][0]
        label = name.removesuffix(".exe")
        rig.append(f"{key}:{label}" +
                   ("" if charges is None else f"×{charges}"))
    scr.addstr(oy + BOARD_H + 2, ox, "RIG  " + "  ".join(rig), curses.A_DIM)
    scr.addstr(oy + BOARD_H + 3, ox, run.message[:BOARD_W + 38])
    if run.over:
        attr = curses.A_BOLD | (0 if run.won else curses.A_REVERSE)
        scr.addstr(oy + BOARD_H + 4, ox, run.over, attr)
        nxt = (f"[r] jack into server {run.level + 1}" if run.won
               else "[r] new runner, back to server 1")
        scr.addstr(oy + BOARD_H + 5, ox, f"{nxt}   [q] quit")
    else:
        scr.addstr(oy + BOARD_H + 4, ox,
                   "move hjkl+zubn/numpad  wait .  scan s  programs p f d e c t"
                   "  quit q", curses.A_DIM)
    scr.refresh()


# -- loadout screen ---------------------------------------------------------------

def show_loadout(scr, level, bank, chosen):
    names = list(PROGRAMS)
    letters = "abcdefgh"
    while True:
        scr.erase()
        mu = sum(PROGRAMS[n][1] for n in chosen)
        scr.addstr(1, 2, f"DAEMONS — RIG UP FOR SERVER {level}", curses.A_BOLD)
        scr.addstr(2, 2, f"MU {mu}/{MU_MAX}   BANK {bank}", curses.A_DIM)
        for i, name in enumerate(names):
            _, cost, charges, desc = PROGRAMS[name]
            mark = "▪" if name in chosen else " "
            ch = "∞" if charges is None else f"×{charges}"
            line = (f"[{letters[i]}] {mark} {name:<12} {cost} MU  {ch:>3}  "
                    f"{desc}")
            attr = curses.A_BOLD if name in chosen else curses.A_DIM
            scr.addstr(4 + i, 2, line, attr)
        row = 5 + len(names)
        if "panic.exe" not in chosen:
            scr.addstr(row, 2, "No panic.exe: no escape valve. Your funeral.",
                       col("threat"))
            row += 1
        if mu > MU_MAX:
            scr.addstr(row, 2, f"Rig overloaded ({mu}/{MU_MAX} MU).",
                       col("threat"))
            row += 1
        scr.addstr(row + 1, 2,
                   "[letters] toggle   [enter] jack in   [q] quit",
                   curses.A_DIM)
        scr.refresh()

        key = scr.get_wch()
        if key == "q":
            return None
        if key in ("\n", "\r", curses.KEY_ENTER) and mu <= MU_MAX:
            return list(chosen)
        if isinstance(key, str) and key in letters[:len(names)]:
            name = names[letters.index(key)]
            if name in chosen:
                chosen.remove(name)
            else:
                chosen.append(name)


# -- targeting mode for blink.exe --------------------------------------------------

def pick_target(scr, run, bank):
    cursor = run.player
    while True:
        draw(scr, run, bank)
        scr.addstr(1 + BOARD_H + 3, 2,
                   "blink.exe: move cursor, [f/enter] jump, [esc] cancel",
                   col("loot", curses.A_BOLD))
        scr.addstr(1 + cursor[1], 2 + cursor[0], "X",
                   col("loot") | curses.A_REVERSE)
        scr.refresh()
        key = scr.get_wch()
        if key in ("f", "\n", "\r", curses.KEY_ENTER):
            return cursor
        if key == "\x1b" or key == "q":
            return None
        if key in MOVES:
            dx, dy = MOVES[key]
            cursor = (min(BOARD_W - 1, max(0, cursor[0] + dx)),
                      min(BOARD_H - 1, max(0, cursor[1] + dy)))


MIN_ROWS = BOARD_H + 8
MIN_COLS = BOARD_W + 4


def main(scr):
    curses.curs_set(0)
    init_colors()
    rows, cols = scr.getmaxyx()
    if rows < MIN_ROWS or cols < MIN_COLS:
        raise SystemExit(
            f"daemons: terminal too small — need at least "
            f"{MIN_COLS}x{MIN_ROWS}, got {cols}x{rows}.")

    bank = 0
    level = 1
    chosen = list(DEFAULT_LOADOUT)
    loadout = show_loadout(scr, level, bank, chosen)
    if loadout is None:
        return
    run = Run(level=level, loadout=loadout)

    while True:
        draw(scr, run, bank + (run.carried + run.creds_taken
                               if run.won else 0))
        key = scr.get_wch()
        if key == "q":
            return
        if run.over:
            if key == "r":
                if run.won:
                    bank += run.carried + run.creds_taken
                    level += 1
                else:
                    bank = 0
                    level = 1
                loadout = show_loadout(scr, level, bank, chosen)
                if loadout is None:
                    return
                run = Run(level=level, loadout=loadout)
            continue
        if key in WAIT_KEYS:
            run.act(0, 0)
        elif key == "s":
            run.act_scan()
        elif key == "p":
            run.act_panic()
        elif key == "d":
            run.act_decoy()
        elif key == "e":
            run.act_emp()
        elif key == "t":
            run.act_tunnel()
        elif key == "f":
            if run.has("blink.exe"):
                target = pick_target(scr, run, bank)
                if target:
                    run.act_blink(target)
            else:
                run.message = "blink.exe: not rigged / no charge."
        elif key == "c":
            if run.has("crowbar.exe"):
                run.message = "crowbar.exe: which direction?"
                draw(scr, run, bank)
                d = scr.get_wch()
                if d in MOVES:
                    run.act_crowbar(*MOVES[d])
                else:
                    run.message = "crowbar.exe: cancelled."
            else:
                run.message = "crowbar.exe: not rigged / no charge."
        elif key in MOVES:
            run.act(*MOVES[key])


if __name__ == "__main__":
    locale.setlocale(locale.LC_ALL, "")
    curses.wrapper(main)
