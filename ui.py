"""DAEMONS curses layer: rendering, input, animations, loadout screen.

Everything terminal-specific lives here; the rules are in game.py. The
main loop funnels every input through game.dispatch — the same code path
the replay tests drive headless.
"""

import curses

from game import (
    Run, dispatch, PROGRAMS, DEFAULT_LOADOUT, MOVES,
    BOARD_W, BOARD_H, TRACE_MAX, MU_MAX,
    GLYPH_RUNNER, GLYPH_HUNTER, GLYPH_KILLER, GLYPH_JUNK, GLYPH_WALL,
    GLYPH_GATE, GLYPH_STATIC, GLYPH_FILE, GLYPH_CRED, GLYPH_TRAP,
    GLYPH_DOOR, GLYPH_HIDDEN, GLYPH_PORT, GLYPH_TUNNEL, GLYPH_ARCHIVE,
    GLYPH_FIFO_IN, GLYPH_FIFO_OUT,
)

# curses key codes -> the plain keys the engine understands
ARROWS = {curses.KEY_LEFT: "h", curses.KEY_RIGHT: "l",
          curses.KEY_UP: "k", curses.KEY_DOWN: "j"}

COLORS = {}


def init_colors():
    if not curses.has_colors():
        return
    curses.start_color()
    curses.use_default_colors()
    for i, (name, fg) in enumerate(
            [("threat", curses.COLOR_RED), ("loot", curses.COLOR_YELLOW),
             ("port", curses.COLOR_GREEN), ("static", curses.COLOR_CYAN),
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
    for i, p in enumerate(run.fifos):
        put(p, GLYPH_FIFO_IN if i == 0 else GLYPH_FIFO_OUT, curses.A_BOLD)
    for p in run.files:
        put(p, GLYPH_FILE, col("loot", curses.A_BOLD))
    for p, kind in run.revealed.items():
        glyph = {"file": GLYPH_FILE, "cred": GLYPH_CRED,
                 "trap": GLYPH_TRAP, "door": GLYPH_DOOR}[kind]
        name = "threat" if kind == "trap" else "loot"
        put(p, glyph, col(name, curses.A_BOLD))
    for p, kind in run.archives.items():
        if p in run.known_archives:
            name = "threat" if kind == "tarbomb" else "loot"
        else:
            name = "unknown"
        put(p, GLYPH_ARCHIVE, col(name, curses.A_BOLD))
    for p in run.hidden:
        put(p, GLYPH_HIDDEN, col("unknown", curses.A_BOLD))
    if run.port_open:
        blink = curses.A_BLINK if run.port_timer is not None else 0
        put(run.port, GLYPH_PORT, col("port", curses.A_BOLD | blink))
    for s in run.sentries:
        cd = run.sentry_countdown(s)
        ch = "!" if cd == 0 else str(cd)
        put(s["pos"], ch, col("threat", curses.A_BOLD))
    if run.decoy:
        put(run.decoy[0], GLYPH_RUNNER, curses.A_DIM)
    for p in run.hunters:
        put(p, GLYPH_HUNTER, curses.A_BOLD)
    for p in run.killers:
        put(p, GLYPH_KILLER, col("threat", curses.A_BOLD))
    put(run.player, GLYPH_RUNNER, curses.A_BOLD)

    bar_w = 20
    filled = run.trace * bar_w // TRACE_MAX
    hud = (f"SRV {run.level} RING {run.ring}   "
           f"TRACE [{'#' * filled}{'-' * (bar_w - filled)}] {run.trace:3d}%   "
           f"FILES {run.carried}/{run.total_files}   "
           f"CRED {run.creds_taken}   BANK {bank}")
    scr.addstr(oy + BOARD_H + 1, ox, hud)

    rig = []
    for name, charges in run.loadout.items():
        key = PROGRAMS[name][0]
        prefix = "" if key == "-" else f"{key}:"
        rig.append(f"{prefix}{name}" +
                   ("" if charges is None else f"×{charges}"))
    scr.addstr(oy + BOARD_H + 2, ox, "RIG  " + "  ".join(rig), curses.A_DIM)
    scr.addstr(oy + BOARD_H + 3, ox, run.message[:BOARD_W + 38])
    if run.over:
        attr = curses.A_BOLD | (0 if run.won else curses.A_REVERSE)
        scr.addstr(oy + BOARD_H + 4, ox, run.over, attr)
        nxt = (f"[r] jack into server {run.level + 1}" if run.won
               else "[r] new runner, back to server 1")
        scr.addstr(oy + BOARD_H + 5, ox, f"{nxt}   [q] quit")
    elif run.player == run.port:
        # the boot banner: the descend-or-jack-out decision lives here
        scr.addstr(oy + BOARD_H + 4, ox,
                   run.port_message()[:BOARD_W + 38], curses.A_BOLD)
    else:
        scr.addstr(oy + BOARD_H + 4, ox,
                   "move hjkl+zubn/numpad  wait .  scan s  extract x"
                   "  ports <>  quit q", curses.A_DIM)
    scr.refresh()


def hunter_pulse(scr, run, bank, ms=90):
    """One brief highlight frame on the hunters, so they read at a glance."""
    if not run.hunters and not run.killers:
        return
    draw(scr, run, bank)
    for p in run.hunters:
        scr.addstr(1 + p[1], 2 + p[0], GLYPH_HUNTER,
                   col("threat", curses.A_BOLD | curses.A_REVERSE))
    for p in run.killers:
        scr.addstr(1 + p[1], 2 + p[0], GLYPH_KILLER,
                   col("threat", curses.A_BOLD | curses.A_REVERSE))
    scr.refresh()
    curses.napms(ms)


def intro_flash(scr, run, bank):
    """Jacking in: the runner's signal locks in — @ blinks 3 times —
    then the hunters blink twice. Here's you; here's them."""
    for phase in range(6):
        draw(scr, run, bank)
        if phase % 2 == 0:
            scr.addstr(1 + run.player[1], 2 + run.player[0], " ")
        else:
            scr.addstr(1 + run.player[1], 2 + run.player[0], GLYPH_RUNNER,
                       col("loot", curses.A_BOLD | curses.A_REVERSE))
        scr.refresh()
        curses.napms(150)
    for _ in range(2):
        hunter_pulse(scr, run, bank, ms=220)
        draw(scr, run, bank)
        scr.refresh()
        curses.napms(120)
    curses.flushinp()   # drop keys mashed during the animation


# -- loadout screen ---------------------------------------------------------------

def show_loadout(scr, level, bank, chosen):
    names = list(PROGRAMS)
    letters = "abcdefghijkl"
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
        if "panic" not in chosen:
            scr.addstr(row, 2, "No panic: no escape valve. Your funeral.",
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


# -- targeting mode for ssh --------------------------------------------------

def pick_target(scr, run, bank):
    cursor = run.player
    while True:
        draw(scr, run, bank)
        scr.addstr(1 + BOARD_H + 3, 2,
                   "ssh: move cursor, [c/enter] connect, [esc] cancel",
                   col("loot", curses.A_BOLD))
        scr.addstr(1 + cursor[1], 2 + cursor[0], "X",
                   col("loot") | curses.A_REVERSE)
        scr.refresh()
        key = scr.get_wch()
        key = ARROWS.get(key, key)
        if key in ("c", "\n", "\r", curses.KEY_ENTER):
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
    intro_flash(scr, run, bank)

    while True:
        draw(scr, run, bank + (run.carried + run.creds_taken
                               if run.won else 0))
        key = scr.get_wch()
        key = ARROWS.get(key, key)
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
                intro_flash(scr, run, bank)
            continue
        turn_before = run.turn
        prev = run
        if key == "c":
            if run.has("ssh"):
                target = pick_target(scr, run, bank)
                if target:
                    run = dispatch(run, "c", target)
            else:
                run.message = "ssh: not rigged / no charge."
        elif key == "d":
            if run.has("rm -rf"):
                run.message = "rm -rf: which direction?"
                draw(scr, run, bank)
                dkey = scr.get_wch()
                dkey = ARROWS.get(dkey, dkey)
                if dkey in MOVES:
                    run = dispatch(run, "d", MOVES[dkey])
                else:
                    run.message = "rm -rf: cancelled."
            else:
                run.message = "rm -rf: not rigged / no charge."
        else:
            run = dispatch(run, key)
        if run is not prev:
            intro_flash(scr, run, bank)      # descended: ring 0 boots
        elif run.turn != turn_before and not run.over:
            hunter_pulse(scr, run, bank)
