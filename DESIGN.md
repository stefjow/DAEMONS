# DAEMONS

*An ASCII cyberspace heist game built on the bones of `robots(6)`.*

> Daemons: background processes, corrupted and hunting.

---

## 1. High Concept

You are a runner — an `@` on a terminal grid. Corporate servers are boards
populated by mindless hunter programs that take one step directly toward you
every time you move. You have no weapons. Your tools are geometry, greed
management, and a small suite of single-use programs.

**You do not win by surviving. You win by stealing files and jacking out.**

DAEMONS takes the deterministic pursuit-and-collision core of the classic Unix
game *Robots* and rebuilds it as a push-your-luck extraction game inspired by
the *spirit* of Android: Netrunner (asymmetric paranoia, hidden information,
an economy of attention) — with none of its cards, terminology, or IP.

---

## 2. Design Pillars

These four pillars are the identity of the game. Any feature that weakens one
of them should be cut, no matter how cool it is.

1. **Extraction over survival.** The goal of every run is grabbing paydata
   and reaching the exit. Clearing the board is never the objective and never
   optimal. The game lives in the moment the player takes one more file than
   was safe.

2. **Deterministic threat, legible risk.** Hunters move by a simple, fully
   predictable rule. Every death is the player's fault and the player can see
   why. Push-your-luck only feels fair when the risk is readable on the board.

3. **The enemy is your terrain.** Hunters that collide crash into junk heaps
   that block other hunters. Herding enemies into each other is not just
   defense — it is how you *build cover* on the way to the paydata. The corp's
   strength becomes the runner's tool.

4. **Time forces imperfection.** A trace clock ticks every turn. Camping,
   stalling, and perfect play are punished by escalation. The player must
   choose between the safe move and the fast move, constantly.

---

## 3. The Core Run Loop

### 3.1 Board

- Procedurally generated grid (start ~40×20, tune later).
- Rendered in ASCII. Unknown things are *visibly unknown* (see §6).

| Glyph | Entity | Behavior |
|-------|--------|----------|
| `@`   | Runner (player) | Moves 1 step / turn (8-directional), or acts |
| `+`   | Hunter | Steps 1 tile directly toward `@` each player turn. No pathfinding. Kills on contact. |
| `K`   | Hunter-Killer | Late-run escalation. Pathfinds around junk/walls. Rare, scary. |
| `▒`   | Junk heap (crashed process) | Created when two hunters collide. Destroys dumb hunters that step into it. Blocks movement. |
| `#`   | Barrier ICE | Static wall. Shapes the board's funnels and chokepoints. |
| `S`   | Sentry ICE | Stationary. Fires down its row/column every N turns on a visible rhythm. The shot travels until blocked by `#`, `▒`, or `~`. |
| `~`   | Static field | Noise sector. Walkable. Blocks sentry lines that pass through it; a runner standing in static can't be hit by sentries at all. |
| `G`   | Code gate | Door tile. Passable only with the matching breaker program. |
| `∩`   | Tunnel end | Planted by `tunnel.exe`. Two ends link; stepping on one moves you to the other (both ways). Hunters can't follow. |
| `◊`   | Backdoor port | Rare, found only under a `?`. Jack out instantly from mid-board and reveal a secret edge on the city map. |
| `¤`   | Paydata file | The reason you're here. Pick up by stepping on it. |
| `$`   | Credits cache | Money for the meta-layer. |
| `☠`   | Trap / snare | Looks like paydata until scanned or triggered. Brain damage. |
| `⌂`   | Exit port | Step on it to jack out with everything you carry. |
| `?`   | Unscanned entity | Something is here. You don't know what. Scanning costs a turn. Resolves to paydata, credits, a trap — or, rarely, a backdoor `◊`. Scanning is a gamble, not just trap-avoidance. |

### 3.2 Turn structure

1. Player acts: move 1 step, wait, scan an adjacent `?`, or fire a program.
2. Every dumb hunter (`+`) steps 1 tile toward the player (dx/dy sign step,
   classic Robots rule). Hunters that land on the same tile, or on junk,
   crash into `▒`.
3. Hunter-killers (`K`) take a pathfinding step (A* around obstacles).
4. Sentries tick their fire rhythm.
5. Trace clock +1 (more for loud actions — see §3.3).
6. Check escalation thresholds, exit-flicker timer, win/loss.

### 3.3 The trace clock

A visible bar. Every turn it rises. Loud actions (breaking a barrier,
triggering a trap, EMP) spike it. Thresholds escalate the run:

- **25%** — a new wave of `+` spawns at the board edges.
- **50%** — spawn 1 `K` (pathfinding hunter).
- **75%** — the exit port `⌂` starts flickering: closes in ~10 turns.
- **100%** — runner is **tagged** (meta-layer consequence, §5), continuous
  hunter spawns. Get out *now*.

The trace clock is the anti-camping mechanism and the tempo engine. Tuning
it is the single most important balance job in the game.

### 3.4 Win / loss (per run)

- **Jack out** at `⌂`: keep all carried files/credits. Trace level at exit
  determines whether you leave tagged.
- **Death** (hunter contact, sentry hit, trap): permadeath for the character
  (§5). Some traps deal *brain damage* instead of death.

---

## 4. Programs — the loadout layer

Between runs the player rigs up. The rig has limited **MU slots** (start: 4).
Each program occupies MU and has limited charges per run. This is the
"deckbuilding": identical boards play completely differently depending on the
suite you brought, and bringing the wrong suite hurts.

Starter suite (tune freely):

| Program | MU | Charges | Effect |
|---------|----|---------|--------|
| `panic.exe` | 1 | 3 | Random teleport (classic Robots). Cheap, desperate. |
| `blink.exe` | 2 | 1 | Targeted teleport to a visible tile. |
| `decoy.exe` | 1 | 2 | Spawns a fake `@` signal; dumb hunters chase it 3 turns. |
| `emp.exe` | 2 | 1 | Stuns all adjacent entities 1 turn. Loud (+trace). |
| `crowbar.exe` | 1 | 2 | Smash one adjacent `#` or `▒`. Loud. |
| `gatekey.exe` | 1 | ∞ | Passes `G` code gates (specific gate families later). |
| `probe.exe` | 1 | ∞ | Scan an adjacent `?` for free (no turn cost). |
| `tunnel.exe` | 2 | 2 | Plant a tunnel end `∩` on your tile (1 charge each). Two ends link into a two-way, hunter-proof passage. Using a tunnel is loud (+trace). |

The teleport progression is deliberate: `panic.exe` (random, base kit) →
`tunnel.exe` (fixed, player-authored) → `blink.exe` (targeted, premium).
Determinism gets cheaper the more foresight it demands.

Design rule: **no program removes the need to read the board.** Programs buy
you one mistake or one shortcut; geometry is still the game.

---

## 5. The Meta-Layer (between runs)

Keep this thin in v1 — the run loop must be fun naked first.

- **City map:** a rhizome, not a list. Start with ~3 known corp servers;
  jacking out of one reveals its connected servers (deeper, richer,
  nastier). Backdoor `◊` escapes reveal *secret edges* — shortcuts to
  servers you couldn't otherwise reach. The map draws itself as you play.
  Rumor-level intel per node ("high security, 2 files, sentry-heavy").
- **Corp clock:** each corp advances its flagship project by 1 tick per
  player run. If any corp completes it → campaign loss. Stealing that corp's
  files sets it back. This makes ignoring a corp a real cost and gives the
  campaign a win condition: expose enough stolen files to take the corps down
  publicly.
- **Adaptation:** hit the same corp repeatedly and its boards get fortified —
  more sentries, seeded `☠` traps near paydata.
- **Corp archetypes:** each corp owns one *signature board mechanic*, not
  just stat inflation. E.g. one corp's servers self-wipe behind intruders
  (tiles you step off collapse exactly N moves later — backtracking rots),
  another runs dense sentry grids threaded with static fields, another
  seeds vortex ICE. Identical rules everywhere, different geometry of fear.
- **Tagged:** if you jacked out at 100% trace, next run starts with hunters
  pre-spawned closer, and/or a safehouse event fires (fried console: lose a
  program; bounty: credits drained).
- **Brain damage:** permanent per character. Effects: −1 max MU, or —
  signature idea — **display corruption**: a percentage of tiles render as
  glitch glyphs (`▓ ? ~`) for the rest of that character's life. In a game
  about reading the board, damaging the player's *information* is the
  cruelest, most thematic wound available.
- **Perception upgrades:** the positive mirror of brain damage. Campaign
  milestones grant persistent information — e.g. `?` entities within 2
  tiles show a partial hint, or sentry fire-lines render one turn early.
  Damage and upgrades fight over the same channel: what you can see.
- **Permadeath + light legacy:** a dead runner leaves the next one a small
  head start (reputation, one contact, a stashed program). Losses sting but
  don't feel wasted.

---

## 6. Rendering & UX rules

- **Unknown must look unknown.** Hidden information is the Netrunner soul.
  Unscanned entities are `?`. Never leak type through subtle tells.
- Trace bar, MU/charges, carried files: always on screen. No hidden player
  state.
- Sentry fire rhythms must be readable (e.g., a countdown glyph or blink).
- Monospace, single screen per run, no scrolling in v1.
- **Deterministic runs:** seed the RNG per run and log keystrokes. Buys
  replayable deaths, shareable daily-seed servers, and exact-replay balance
  tests (a scripted solution string per test board, driven through the real
  input dispatch).
- Suggested stack: **Python + `tcod`** (or Rust + `bracket-lib`). The v1 run
  loop is a few hundred lines.

---

## 7. Build Order

1. **v0 — Robots-with-a-goal (weekend):** grid, `@`, dumb hunters, collision
   junk, files, exit, trace clock with one escalation. If this isn't fun,
   stop and tune before adding anything.
2. **v1 — ICE & programs:** barriers, sentries + static fields, code gates,
   `?` scanning (incl. rare backdoors `◊`), traps, the starter program
   suite with `tunnel.exe`, MU loadout screen.
3. **v2 — Meta-layer:** rhizome city map (self-revealing nodes, secret
   edges from backdoors), corp clock, corp signature archetypes, credits
   economy, tagged consequences, brain damage, legacy.
4. **v3 — Texture:** display-corruption brain damage + perception upgrades,
   corp adaptation, hunter-killer variety, vortex ICE (pulls runner *and*
   hunters 1 tile per turn within radius 3 — kite the pack into it),
   chaos-wipe trace-out (at 100% trace the board edge collapses inward one
   ring every 3 turns), campaign finale (arcology server).

---

## 8. Balance Watchlist

- **Camping/degenerate corners** (classic Robots exploit: hide behind junk
  and wait). Killers: trace escalation, flickering exit, spawn waves. Verify
  in playtests that waiting is never the best move.
- **Trace tuning:** too fast → panic slog; too slow → camping returns.
- **`panic.exe` spam:** random teleport must stay a desperation tool, not a
  strategy. Charge limits and landing-on-a-hunter risk keep it honest.
- **Junk-wall fortresses:** herding is the point, but sealing yourself in
  safely forever isn't. `K` hunters pathfind around junk for exactly this
  reason.
- **Tunnel camping:** a `∩`↔`∩` link plus junk walls could make a safe
  ping-pong loop. Tunnel use costs trace, and the trace clock never stops —
  verify in playtests that tunnel loops lose to the clock.
- **Third-file math:** the expected value of greed should hover near
  break-even. If taking every file is always right, there's no decision; if
  it's always wrong, there's no temptation.

---

## 9. What This Game Is Not

- Not a card game. No decks, no hands, no card terminology.
- Not a Netrunner adaptation. Original fiction and terms only — the
  *mechanics of paranoia* are unownable; the trademark isn't ours.
- Not a full roguelike dungeon crawler. No inventory sprawl, no XP levels,
  no melee. The board and the clock are the game.
