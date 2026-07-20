#!/usr/bin/env python3
"""DAEMONS v0 — Robots-with-a-goal.

The core run loop from DESIGN.md §7 step 1: grid, runner, dumb hunters,
collision junk, paydata files, exit port, trace clock with spawn-wave
escalation. No programs, no ICE, no meta-layer yet.

Run:  python3 daemons.py
Keys: y k u     7 8 9
      h . l     4 . 6   move (8-directional, vi-style or numpad; arrows work
      b j n     1 2 3   for the cardinals; z = y for QWERTZ keyboards)
      . or 5  wait
      t       panic: random teleport (3 charges — you can land next to,
              or on, a hunter; desperation only)
      r       continue (after a run ends): next server if you jacked out,
              back to server 1 if you flatlined
      q       quit

Each server you jack out of leads to a deeper one: more hunters, higher
stakes. Death sends you back to server 1 with an empty bank.
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
FILE_COUNT = 4
PANIC_CHARGES = 3
TRACE_MAX = 100
WAVE_THRESHOLDS = (25, 50, 75)   # each spawns a wave of hunters at the edges
MAX_WAVE = 6                     # wave size grows with server level
BURN_SPAWN_EVERY = 3        # at 100% trace, continuous edge spawns

GLYPH_RUNNER = "@"
GLYPH_HUNTER = "+"
GLYPH_JUNK = "▒"       # ▒
GLYPH_FILE = "¤"       # ¤
GLYPH_EXIT = "⌂"       # ⌂

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


def sign(n):
    return (n > 0) - (n < 0)


def cheb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


class Run:
    """One server run: board state and the turn loop rules."""

    def __init__(self, level=1):
        self.level = level
        self.turn = 0
        self.trace = 0
        self.carried = 0
        self.panic = PANIC_CHARGES
        self.over = None            # None = live, else end-of-run message
        self.won = False
        self.message = "Jack in. Grab the paydata, reach the exit port."
        self.waves_fired = set()

        cells = [(x, y) for x in range(BOARD_W) for y in range(BOARD_H)]
        self.player = random.choice(
            [(x, y) for x, y in cells
             if BOARD_W // 4 <= x < 3 * BOARD_W // 4
             and BOARD_H // 4 <= y < 3 * BOARD_H // 4]
        )
        taken = {self.player}

        def claim(pool):
            pos = random.choice([c for c in pool if c not in taken])
            taken.add(pos)
            return pos

        self.exit = claim([c for c in cells if cheb(c, self.player) >= 12])
        self.files = {claim(cells) for _ in range(FILE_COUNT)}
        count = min(MAX_HUNTERS,
                    BASE_HUNTERS + HUNTERS_PER_LEVEL * (level - 1))
        self.wave_size = min(MAX_WAVE, 2 + (level - 1) // 2)
        self.hunters = {
            claim([c for c in cells if cheb(c, self.player) >= MIN_SPAWN_DIST])
            for _ in range(count)
        }
        self.junk = set()

    # -- player action ------------------------------------------------------

    def act(self, dx, dy):
        """One full turn: player step (or wait), then the world responds."""
        if self.over:
            return
        nx, ny = self.player[0] + dx, self.player[1] + dy
        if not (0 <= nx < BOARD_W and 0 <= ny < BOARD_H):
            self.message = "Edge of the server."
            return
        if (nx, ny) in self.junk:
            self.message = "A junk heap blocks the way."
            return
        self.player = (nx, ny)
        self.message = ""
        self.resolve("You walked into a hunter process.")

    def act_panic(self):
        """Classic Robots teleport: anywhere non-junk — even onto a hunter."""
        if self.over:
            return
        if self.panic <= 0:
            self.message = "panic.exe: no charges left."
            return
        self.panic -= 1
        self.player = random.choice(
            [(x, y) for x in range(BOARD_W) for y in range(BOARD_H)
             if (x, y) not in self.junk]
        )
        self.message = f"panic.exe fired — {self.panic} left."
        self.resolve("you teleported into a hunter process.")

    def resolve(self, contact_death):
        """Everything that happens after the runner lands on a tile."""
        if self.player in self.hunters:
            return self.die(contact_death)
        if self.player in self.files:
            self.files.discard(self.player)
            self.carried += 1
            self.message = f"Paydata secured ({self.carried})."
        if self.player == self.exit:
            self.won = True
            self.over = (f"JACKED OUT — {self.carried} file"
                         f"{'s' if self.carried != 1 else ''} extracted, "
                         f"trace {self.trace}%.")
            return

        self.step_hunters()
        if self.over:
            return
        self.tick_trace()

    def die(self, why):
        self.won = False
        self.over = f"FLATLINED — {why}"

    # -- world response -----------------------------------------------------

    def step_hunters(self):
        """Classic Robots rule: every hunter takes one sign-step toward @.
        Same-tile arrivals crash into junk; stepping into junk is fatal."""
        px, py = self.player
        arrivals = {}
        for hx, hy in self.hunters:
            dest = (hx + sign(px - hx), hy + sign(py - hy))
            arrivals.setdefault(dest, 0)
            arrivals[dest] += 1

        survivors = set()
        for dest, count in arrivals.items():
            if dest == self.player:
                return self.die("a hunter caught you.")
            if dest in self.junk or count > 1:
                self.junk.add(dest)
            else:
                survivors.add(dest)
        self.hunters = survivors

    def tick_trace(self):
        self.turn += 1
        self.trace = min(TRACE_MAX, self.trace + 1)
        for t in WAVE_THRESHOLDS:
            if self.trace >= t and t not in self.waves_fired:
                self.waves_fired.add(t)
                self.spawn_wave(self.wave_size)
                self.message = f"TRACE {t}% — new hunters flood the edges!"
        if self.trace >= TRACE_MAX and self.turn % BURN_SPAWN_EVERY == 0:
            self.spawn_wave(1)
            self.message = "TRACE 100% — they keep coming. Get out NOW."

    def spawn_wave(self, n):
        edges = [(x, y) for x in range(BOARD_W) for y in range(BOARD_H)
                 if (x in (0, BOARD_W - 1) or y in (0, BOARD_H - 1))
                 and (x, y) not in self.junk
                 and (x, y) != self.player
                 and cheb((x, y), self.player) >= 4]
        for pos in random.sample(edges, min(n, len(edges))):
            self.hunters.add(pos)


# -- rendering ---------------------------------------------------------------

def draw(scr, run, bank):
    scr.erase()
    oy, ox = 1, 2   # board origin on screen

    for x in range(BOARD_W):
        for y in range(BOARD_H):
            scr.addstr(oy + y, ox + x, "·", curses.A_DIM)
    for x, y in run.junk:
        scr.addstr(oy + y, ox + x, GLYPH_JUNK)
    for x, y in run.files:
        scr.addstr(oy + y, ox + x, GLYPH_FILE, curses.A_BOLD)
    ex, ey = run.exit
    scr.addstr(oy + ey, ox + ex, GLYPH_EXIT, curses.A_BOLD)
    for x, y in run.hunters:
        scr.addstr(oy + y, ox + x, GLYPH_HUNTER)
    px, py = run.player
    scr.addstr(oy + py, ox + px, GLYPH_RUNNER, curses.A_BOLD)

    bar_w = 20
    filled = run.trace * bar_w // TRACE_MAX
    hud = (f"SRV {run.level}   "
           f"TRACE [{'#' * filled}{'-' * (bar_w - filled)}] {run.trace:3d}%   "
           f"FILES {run.carried}/{FILE_COUNT}   PANIC {run.panic}   "
           f"BANK {bank}")
    scr.addstr(oy + BOARD_H + 1, ox, hud)
    scr.addstr(oy + BOARD_H + 2, ox, run.message[:BOARD_W + 30])
    if run.over:
        attr = curses.A_BOLD | (0 if run.won else curses.A_REVERSE)
        scr.addstr(oy + BOARD_H + 3, ox, run.over, attr)
        nxt = (f"[r] jack into server {run.level + 1}" if run.won
               else "[r] new runner, back to server 1")
        scr.addstr(oy + BOARD_H + 4, ox, f"{nxt}   [q] quit")
    else:
        scr.addstr(oy + BOARD_H + 3, ox,
                   "move: hjkl + zubn / numpad   wait: .   panic: t   quit: q",
                   curses.A_DIM)
    scr.refresh()


MIN_ROWS = BOARD_H + 6
MIN_COLS = BOARD_W + 4


def main(scr):
    curses.curs_set(0)
    rows, cols = scr.getmaxyx()
    if rows < MIN_ROWS or cols < MIN_COLS:
        raise SystemExit(
            f"daemons: terminal too small — need at least "
            f"{MIN_COLS}x{MIN_ROWS}, got {cols}x{rows}.")
    bank = 0
    run = Run(level=1)
    while True:
        draw(scr, run, bank + (run.carried if run.won else 0))
        key = scr.get_wch()
        name = key if isinstance(key, str) else key
        if name == "q":
            return
        if run.over:
            if name == "r":
                if run.won:
                    bank += run.carried
                    run = Run(level=run.level + 1)
                else:
                    bank = 0
                    run = Run(level=1)
            continue
        if name in WAIT_KEYS:
            run.act(0, 0)
        elif name == "t":
            run.act_panic()
        elif name in MOVES:
            run.act(*MOVES[name])


if __name__ == "__main__":
    locale.setlocale(locale.LC_ALL, "")
    curses.wrapper(main)
