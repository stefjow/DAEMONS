#!/usr/bin/env python3
"""DAEMONS — rings & ICE.

The v1 milestone from DESIGN.md §7 (barrier ICE, sentries + static fields,
code gates, `?` scanning with rare backdoors, traps, the starter program
suite, an MU loadout screen), the v0.5 stack experiment (§3.1), and the
first v2 additions: encrypted archives `≡` and `mkfifo`.

Every server is a stack of two rings. Ring 1 is userland; ring 0 is root —
richer, nastier, and running an ICE daemon whose rule is hidden until you
stand on the down-port and read its boot banner. Ports are the only places
you can jack out; once you step off a port into a ring, the only exits are
the far port or death. Trace, loot, and charges carry across the descent.
Runs are seeded and deterministic (§6).

Run:  python3 daemons.py

Code layout: game.py (rules engine, headless), ice.py (ring content &
balance), meta.py (campaign: city map, corp clocks, publish-or-fence),
rooms.py + rooms/ (authored ring-0 vaults: fully visible, hand-designed,
solver-verified; dying in one offers a free retry of the room), ui.py
(curses), tools/room_solver.py (exhaustive room solver for authoring),
tests/ (mechanics + exact-replay tests).

Movement (8-directional; z = y for QWERTZ; arrows for the cardinals):
      y k u     7 8 9
      h . l     4 . 6        . or 5 = wait
      b j n     1 2 3

Actions:
      s   scan adjacent `?` tiles and archives (costs a turn; free &
          automatic with stat equipped)
      x   extract an archive `≡` you stand on: channel 2 turns in place —
          any other action breaks the channel. Loot: creds, a charge
          refill — or a tarbomb. Scan first.
      >   on the down-port: descend to ring 0 (read the banner first)
      <   on an open port: jack out with everything you carry
Programs (must be equipped, consume charges):
      p   panic     kernel panic: random teleport — can land you next to,
                    or on, a hunter; desperation only
      c   ssh       connect anywhere: move the cursor, c/enter to jump,
                    escape to cancel
      f   fork      fork a decoy child on your tile; dumb hunters chase
                    it 3 turns and crash into it
      e   sigstop   freeze all adjacent hunter processes 1 turn (loud)
      d   rm -rf    then a direction: delete an adjacent # or ▒ (loud)
      t   socat     bind a tunnel end; two ends link into a two-way,
                    hunter-proof passage (travel is loud)
      m   mkfifo    budget socat: one-way pipe — first end bound is the
                    inlet ∩, second the outlet ∪
      sudo / stat are passive while equipped.

      space  continue after a run ends: to the safehouse if you jacked
             out, back to the city map if you flatlined
      q      quit

The campaign (DESIGN.md §5): the city map starts with one entry server
per corp. Jacking out of a server reveals its connected servers — deeper,
richer, nastier; backdoor escapes reveal secret edges two levels down.
A server's ICE shows as `?` on the map until earned: read its boot
banner yourself (you keep that even if you die), jack out with a looted
intel file `i` (decrypts at the safehouse, names another server's ICE),
or pay the fixer on the city screen.
At the safehouse every haul is published (sets back that corp's project
clock and exposes it — expose every corp to win) or fenced (creds for
gear). Every run, however shallow, ticks every standing corp's clock:
if any corp completes its project, the campaign is lost. Death wipes
your bank but the map stays mapped.
"""

import curses
import locale

from ui import main

if __name__ == "__main__":
    locale.setlocale(locale.LC_ALL, "")
    curses.wrapper(main)
