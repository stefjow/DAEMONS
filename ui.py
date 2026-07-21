"""DAEMONS curses layer: rendering, input, animations, loadout screen.

Everything terminal-specific lives here; the rules are in game.py. The
main loop funnels every input through game.dispatch — the same code path
the replay tests drive headless.
"""

import curses

from meta import (Campaign, CORPS, CLOCK_MAX, EXPOSURE_GOAL, FENCE_RATE,
                  INTEL_PRICE)
from game import (
    dispatch, PROGRAMS, DEFAULT_LOADOUT, MOVES,
    BOARD_W, BOARD_H, TRACE_MAX, MU_MAX,
    GLYPH_RUNNER, GLYPH_HUNTER, GLYPH_KILLER, GLYPH_JUNK, GLYPH_WALL,
    GLYPH_GATE, GLYPH_STATIC, GLYPH_FILE, GLYPH_CRED, GLYPH_TRAP,
    GLYPH_DOOR, GLYPH_HIDDEN, GLYPH_PORT, GLYPH_TUNNEL, GLYPH_ARCHIVE,
    GLYPH_FIFO_IN, GLYPH_FIFO_OUT, GLYPH_INTEL,
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
                 "trap": GLYPH_TRAP, "door": GLYPH_DOOR,
                 "intel": GLYPH_INTEL}[kind]
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
        nxt = ("[space] to the safehouse" if run.won
               else "[space] back to the city — new runner")
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
                   "[letters] toggle   [enter] jack in   [q] city map",
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
CITY_NODE_CAP = 12          # most recent targets shown on the map screen


# -- city map & safehouse ------------------------------------------------------

def show_city(scr, campaign, notes=()):
    """The between-runs screen: corp clocks, known servers, last events,
    and the fixer. Returns the chosen node, or None to quit."""
    letters = "abcdefghijkl"
    buying = False
    fixer_line = ""
    while True:
        scr.erase()
        scr.addstr(1, 2, "DAEMONS — CITY MAP", curses.A_BOLD)
        scr.addstr(1, 24, f"BANK {campaign.bank}", curses.A_DIM)
        for i, corp in enumerate(CORPS):
            c, e = campaign.clock[corp], campaign.exposure[corp]
            if campaign.fallen(corp):
                line = f"{corp:<5} FALLEN — servers dark"
                attr = curses.A_DIM
            else:
                line = (f"{corp:<5} [{'#' * c}{'-' * (CLOCK_MAX - c)}] "
                        f"{c:2d}/{CLOCK_MAX}   exposure {e}/{EXPOSURE_GOAL}")
                attr = col("threat") if c >= CLOCK_MAX - 3 else 0
            scr.addstr(3 + i, 2, line, attr)

        targets = campaign.targets()[-CITY_NODE_CAP:]
        for i, node in enumerate(targets):
            ice = node.ice if node.known else "?"
            raided = f"  raided ×{node.raided}" if node.raided else ""
            line = (f"[{letters[i]}] {node.name:<18} depth {node.level}  "
                    f"ice: {ice}{raided}")
            scr.addstr(7 + i, 2, line,
                       0 if node.known else col("unknown"))
        note_row = 8 + len(targets)
        for i, note in enumerate(list(notes)[-4:]):
            scr.addstr(note_row + i, 2, note[:BOARD_W + 38], curses.A_DIM)
        prompt_row = note_row + min(len(notes), 4) + 1
        if fixer_line:
            scr.addstr(prompt_row, 2, fixer_line[:BOARD_W + 38],
                       curses.A_BOLD)
            prompt_row += 1
        prompt = ("fixer: intel on which server? [letter] / [esc] never mind"
                  if buying else
                  f"[letter] jack in   [i] buy intel ({INTEL_PRICE} creds)"
                  f"   [q] quit")
        scr.addstr(prompt_row, 2, prompt, curses.A_DIM)
        scr.refresh()

        key = scr.get_wch()
        if buying:
            buying = False
            if (isinstance(key, str) and key in letters[:len(targets)]):
                fixer_line = campaign.buy_intel(targets[letters.index(key)])
            continue
        if key == "q":
            return None
        if key == "i":
            if all(n.known for n in targets):
                fixer_line = "Fixer: nothing left to sell you here."
            elif campaign.bank < INTEL_PRICE:
                fixer_line = (f"Fixer wants {INTEL_PRICE} creds. "
                              f"You're short.")
            else:
                buying = True
                fixer_line = ""
            continue
        if isinstance(key, str) and key in letters[:len(targets)]:
            return targets[letters.index(key)]


def safehouse(scr, campaign, node, run):
    """Publish-or-fence (DESIGN §5): every stolen file is campaign
    progress or gear money, never both. Returns event lines."""
    if not run.carried:
        return campaign.end_run(node, run, publish=False)
    while True:
        scr.erase()
        scr.addstr(1, 2, "SAFEHOUSE", curses.A_BOLD)
        scr.addstr(3, 2, f"Haul from {node.name}: {run.carried} files, "
                         f"{run.creds_taken} creds.")
        scr.addstr(5, 2, f"[p] publish — {node.corp} clock -{run.carried}, "
                         f"exposure +{run.carried}")
        scr.addstr(6, 2, f"[f] fence   — +{run.carried * FENCE_RATE} creds")
        scr.addstr(8, 2, "Every cred you take is campaign progress you sold.",
                   curses.A_DIM)
        scr.refresh()
        key = scr.get_wch()
        if key in ("p", "f"):
            return campaign.end_run(node, run, publish=(key == "p"))


def show_finale(scr, campaign, notes):
    """Campaign over. Returns True to start a new campaign."""
    won = campaign.result == "won"
    while True:
        scr.erase()
        scr.addstr(1, 2, "THE CORPS FALL" if won else "PROJECT COMPLETE",
                   curses.A_BOLD | (0 if won else curses.A_REVERSE))
        for i, note in enumerate(list(notes)[-4:]):
            scr.addstr(3 + i, 2, note[:BOARD_W + 38])
        scr.addstr(8, 2, "[n] new campaign   [q] quit", curses.A_DIM)
        scr.refresh()
        key = scr.get_wch()
        if key == "n":
            return True
        if key == "q":
            return False


def play_run(scr, run, campaign):
    """Drive one run to its end screen. Returns the run, or None on quit."""
    while True:
        draw(scr, run, campaign.bank)
        key = scr.get_wch()
        key = ARROWS.get(key, key)
        if key == "q":
            return None
        if run.over:
            if key in (" ", "r", "\n", "\r"):
                return run
            continue
        turn_before = run.turn
        prev = run
        if key == "c":
            if run.has("ssh"):
                target = pick_target(scr, run, campaign.bank)
                if target:
                    run = dispatch(run, "c", target)
            else:
                run.message = "ssh: not rigged / no charge."
        elif key == "d":
            if run.has("rm -rf"):
                run.message = "rm -rf: which direction?"
                draw(scr, run, campaign.bank)
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
            intro_flash(scr, run, campaign.bank)   # descended: ring 0 boots
        elif run.turn != turn_before and not run.over:
            hunter_pulse(scr, run, campaign.bank)


def main(scr):
    curses.curs_set(0)
    init_colors()
    rows, cols = scr.getmaxyx()
    if rows < MIN_ROWS or cols < MIN_COLS:
        raise SystemExit(
            f"daemons: terminal too small — need at least "
            f"{MIN_COLS}x{MIN_ROWS}, got {cols}x{rows}.")

    campaign = Campaign()
    chosen = list(DEFAULT_LOADOUT)
    notes = ("The corps build. You leak. Pick a server.",)
    while True:
        node = show_city(scr, campaign, notes)
        if node is None:
            return
        loadout = show_loadout(scr, node.level, campaign.bank, chosen)
        if loadout is None:
            continue                    # back to the city map
        run = campaign.start_run(node, loadout)
        intro_flash(scr, run, campaign.bank)
        run = play_run(scr, run, campaign)
        if run is None:
            return
        if run.won:
            notes = safehouse(scr, campaign, node, run)
        else:
            notes = campaign.end_run(node, run)
        if campaign.result:
            if not show_finale(scr, campaign, notes):
                return
            campaign = Campaign()
            chosen = list(DEFAULT_LOADOUT)
            notes = ("A new campaign. The corps never sleep.",)
