# DAEMONS

*An ASCII cyberspace heist game built on the bones of `robots(6)`.*

> Daemons: background processes, corrupted and hunting.

---

## 1. High Concept

You are a runner — an `@` on a terminal grid. Corporate servers are stacks
of ICE rings: small boards populated by mindless hunter programs that take
one step directly toward you every time you move. You have no weapons. Your
tools are geometry, greed management, and a small suite of single-use
programs. A run is a descent, ring by ring, toward `/root`.

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

### 3.1 Servers, rings, ICE

A server is not one board — it is a **stack of rings**, protection rings in
the Unix sense: outer rings are userland, ring 0 is root. Each ring is one
small board. A run is a descent: jack into the outermost ring, fight down
toward ring 0, jack out with what you dared to carry.

- **Ports (`⌂`) connect the rings.** Every ring has an entry port (where
  you arrive) and a down-port (leading deeper). Ports are the only places
  you can jack out.
- **The boot banner.** A ring's identity is hidden until you stand at its
  door. On a down-port you see the next ring's banner — one `dmesg` line
  (`[ 2.0331 ] watchdogd started`) naming its ICE — but its layout stays
  dark. Descend or jack out: that choice, made at every port, is the
  structural push-your-luck of the game.
- **The encounter rule.** Once you step off a port into a ring, you are
  committed: the only exits are the far port or death. No retreat upward,
  no mid-ring jack-out. (The rare backdoor `◊` is the exception — a
  jailbreak, never a plan.)
- **Reveal, not ambush.** A ring boots when you enter: you materialize on
  its entry port with the whole board visible, and nothing moves until
  your first input. Hidden information decides whether you *enter*; it
  never sucker-punches you after you have.
- **Depth is public, identity is secret.** The city map shows how deep a
  stack goes; what runs on each ring is learned by descending to its door,
  looted as intel files from other servers, or bought at the repo (§5).
  Information is earned by depth — the natural first visit to a scary
  server is a *scouting run*: crack the outer ring, read the next banner,
  jack out and rig accordingly.
- **Loot on every ring.** Paydata gets steeply richer toward ring 0 — the
  vault is `/root` — but a ring-1 skim always pays *something*. A shallow
  jack-out is a result, not a failure.

**ICE — ring identities.** Each ring runs one signature daemon that defines
its board-wide rule. Two fairness rules: an unbooted ring may be *worse
than you hoped*, never *unwinnable with your rig* — identities modulate
pressure, they never hard-gate progress on a specific program. Starter pool
(tune freely):

| ICE | Ring rule |
|-----|-----------|
| `crond` | Baseline: dumb hunters, standard spawns. The outer ring of most stacks. |
| `firewalld` | Barrier-dense: funnels of `#`, permission gates `G`. Slow geometry. |
| `watchdogd` | A hunter-killer `K` is awake from boot. |
| `snortd` | Sentry grid `S` threaded with static fields `~`. A rhythm level. |
| `auditd` | Every trace gain doubled. Quiet feet, or pay in time. |
| `honeyd` | Rich in `?` and `☠`; paydata plentiful, scanning near-mandatory. |
| `tmpwatch` | Self-wiping floor: tiles you leave collapse N moves later. Backtracking rots. |

**Authored rooms (the anti-randomness experiment).** Procedural boards
make difficulty out of noise; authored rooms make it out of design. A
room is an ASCII drawing (`rooms/*.txt`, format in `rooms.py`) wired in
as a ring-0 vault for its ICE. The rules inside an authored room:

- **Fully visible.** No `?`, no archives — paranoia lives at the campaign
  layer, clarity inside the room. Hidden info decides whether you enter;
  design decides whether you survive.
- **Scripted vents, not random waves.** Trace thresholds spawn
  reinforcements at marked vent tiles, in order — plannable pressure.
  No vents, no reinforcements; the clock still seals the port.
- **Free retries.** Dying in an authored room offers a reset to the
  descent state, like a puzzle. Permadeath consequences stay at the
  campaign layer. (Open question: should each retry tick the corp clock?)
- **Machine-verified.** Every shipped room carries solver-proven solution
  strings in `tests/test_rooms.py`: a scout line (port, no loot) and a
  full-loot line — both found by exhaustive search over the deterministic
  state space (`tools/room_solver.py`), so they hold for any loadout.
- **Greed is depth of solution.** The scout line should be findable in a
  minute; the full-loot line is the real puzzle (the kennel: 15 keys to
  flee, 49 to leave with everything and the watchdog fried on its own
  corp's sentry beam).

### 3.2 Board

- Each ring is a procedurally generated grid — small and dense; a ring is
  a course, not a meal (tune size against stack depth).
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
| `G`   | Permission gate | Door tile. Passable only with `sudo`. |
| `∩`   | Tunnel end | Bound by `socat`. Two ends link; stepping on one moves you to the other (both ways). Hunters can't follow. |
| `◊`   | Backdoor port | Rare, found only under a `?`. The only mid-ring jack-out: escape instantly and reveal a secret edge on the city map. |
| `¤`   | Paydata file | The reason you're here. Pick up by stepping on it. |
| `$`   | Credits cache | Money for the meta-layer. |
| `☠`   | Trap / snare | Looks like paydata until scanned or triggered. Brain damage. |
| `⌂`   | Port | Ring entry/exit. On a down-port: read the next ring's boot banner, then descend — or jack out with everything you carry (§3.1). |
| `≡`   | Encrypted archive (v2) | Extract by channeling 2 turns in place — visible countdown, hunters keep coming. Loot: credits, warez, patches, charge refills — or a **tarbomb** (junk burst / hunter spawn). Scanning warns. |
| `?`   | Unscanned entity | Something is here. You don't know what. Scanning costs a turn. Resolves to paydata, credits, a trap — or, rarely, a backdoor `◊`. Scanning is a gamble, not just trap-avoidance. |

### 3.3 Turn structure

1. Player acts: move 1 step, wait, scan an adjacent `?`, or fire a program.
2. Every dumb hunter (`+`) steps 1 tile toward the player (dx/dy sign step,
   classic Robots rule). Hunters that land on the same tile, or on junk,
   crash into `▒`.
3. Hunter-killers (`K`) take a pathfinding step (A* around obstacles).
4. Sentries tick their fire rhythm.
5. Trace clock +1 (more for loud actions — see §3.4).
6. Check escalation thresholds, port-close timer, win/loss.

### 3.4 The trace clock

A visible bar. Every turn it rises. Loud actions (breaking a barrier,
triggering a trap, EMP) spike it. The clock is per *run*, not per ring:
trace carries across the whole descent — it is the corp noticing *you*,
not the floor — so you arrive at deep rings with thresholds already
burned. Thresholds escalate the run:

- **25%** — a new wave of `+` spawns at the board edges.
- **50%** — spawn 1 `K` (pathfinding hunter).
- **75%** — the current ring's ports start flickering: they seal in ~10
  turns. Reach one and choose — deeper or out — or you're locked in until
  the chaos-wipe.
- **100%** — runner is **tagged** (meta-layer consequence, §5), continuous
  hunter spawns. Get out *now*.

The trace clock is the anti-camping mechanism and the tempo engine. Tuning
it is the single most important balance job in the game.

### 3.5 Win / loss (per run)

- **Jack out** at any port `⌂`: keep all carried files/credits, however
  shallow the run. Trace level at exit determines whether you leave tagged.
- **Death** (hunter contact, sentry hit, trap): permadeath for the character
  (§5). Some traps deal *brain damage* instead of death. Inside a ring
  there is no third option — far port or flatline (§3.1).

---

## 4. Programs — the loadout layer

Between runs the player rigs up. The rig has limited **MU slots** (start: 4).
Each program occupies MU and has limited charges per run. This is the
"deckbuilding": identical boards play completely differently depending on the
suite you brought, and bringing the wrong suite hurts.

Programs are also the *soft counters* to ICE (§3.1): `rm -rf` makes a
`firewalld` ring fast, `nice` makes `watchdogd` survivable, `stat` defangs
`honeyd` — faster, never free. The matchup between rig and stack is what
scouting runs and bought intel inform, and it is why they're worth doing.

Programs are Unix commands, not branded wares — the runner's rig is a
shell. Starter suite (tune freely):

| Program | MU | Charges | Effect |
|---------|----|---------|--------|
| `panic` | 1 | 3 | Kernel panic: random teleport (classic Robots). Cheap, desperate. |
| `ssh` | 2 | 1 | Open a session on any visible tile: targeted teleport. |
| `fork` | 1 | 2 | Forks a decoy child `@`; dumb hunters chase it 3 turns. |
| `sigstop` | 2 | 1 | Freezes all adjacent processes 1 turn. Loud (+trace). |
| `rm -rf` | 1 | 2 | Deletes one adjacent `#` or `▒`. Loud. |
| `sudo` | 1 | ∞ | Passes `G` permission gates (specific gate families later). |
| `stat` | 1 | ∞ | Adjacent `?` identified for free (no turn cost). |
| `socat` | 2 | 2 | Binds a tunnel end `∩` on your tile (1 charge each). Two ends link into a two-way, hunter-proof passage. Travel is loud (+trace). |

The teleport progression is deliberate: `panic` (random, base kit) →
`socat` (fixed, player-authored) → `ssh` (targeted, premium).
Determinism gets cheaper the more foresight it demands.

Design rule: **no program removes the need to read the board.** Programs buy
you one mistake or one shortcut; geometry is still the game.

### v2 — warez, versions, rig heat

- **Corp signature warez:** each corp develops one program that can only be
  looted from its own servers (or bought stolen at the repo, §5). Target
  selection on the city map gains a second axis beyond file count: "this
  corp is where `sigkill` lives."
- **Versions, not sprawl:** §9 bans inventory bloat, so most progression is
  *patches*, not new programs — `fork 1.0` (child lives 3 turns) →
  `fork 2.0` (4 turns, 3 charges). Patches are found in archives or bought
  at the repo and applied at the safehouse. Keep the total roster ≤ ~14.
- **Rig heat:** every MU above 4 adds ~+25% to *all* trace gains. MU is
  bought, but power is priced in time — a bigger rig runs hotter, and
  minimal-rig runs stay a legitimate expert style.

Candidate v2 warez (each mechanic-first, tune freely):

| Program | MU | Charges | Effect |
|---------|----|---------|--------|
| `mkfifo` | 1 | 1 | Budget socat: two ends, but the pipe is **one-way** (first planted → second). |
| `nice` | 1 | 2 | Reschedule adjacent hunters: they move only every other turn, for 4 turns. |
| `sigkill` | 2 | 1 | Delete one adjacent hunter outright. Rare, loud, expensive — ration hard (§8). |
| `at` | 1 | 2 | Schedule another equipped program's effect N turns in the future (set the sentry-freeze for when you'll be at the vault). |
| `grep` | 1 | 2 | Mark every `?` on the board that matches a pattern (paydata / not-paydata). |
| `mount` | 1 | 2 | Drop a junk heap `▒` on an adjacent tile. Instant cover. |

---

## 5. The Meta-Layer (between runs)

Keep this thin in v1 — the run loop must be fun naked first.

- **City map:** a rhizome, not a list. Start with ~3 known corp servers;
  jacking out of one reveals its connected servers (deeper, richer,
  nastier). Backdoor `◊` escapes reveal *secret edges* — shortcuts to
  servers you couldn't otherwise reach. The map draws itself as you play.
  Each node shows its **stack depth**; ring identities show as `?` until
  *earned* — scout the boot banner yourself, decrypt an intel file looted
  from another server, or pay the fixer. No free rumors: information is
  loot.
- **Corp clock:** each corp advances its flagship project by 1 tick per
  player run — *every* run, however shallow. The clock is the run fee:
  a safe ring-1 skim still spends campaign time, the one currency you
  can't buy back. If any corp completes its project → campaign loss.
  *Publishing* that corp's stolen files sets it back (see
  publish-or-fence). This makes ignoring a corp a real cost and gives the
  campaign a win condition: expose enough stolen files to take the corps
  down publicly.
- **Restock:** a looted ring stays looted until the corp restocks it some
  ticks later. Shallow farming has a withdrawal limit.
- **The repo:** a gray-market node on the city map that isn't a corp — a
  fixer's package mirror. Buy warez, patches, RAM, and **ring intel** (a
  stack's boot banners — money buys what scouting runs earn) with
  credits; stock rotates per visit, so you can't always buy your way out.
- **Publish or fence:** every stolen file is spent one of two ways —
  *published* (sets back that corp's clock: campaign progress) or *fenced*
  at the repo (credits for gear). Every credit spent is campaign progress
  you sold. The meta-layer's greed decision mirrors the board's.
- **RAM & rig heat:** MU upgrades 4 → 5 → 6 (hard cap), steeply priced —
  and each MU above 4 makes the runner louder (§4 rig heat). Brain damage
  (−1 MU) and hardware fight over the same stat: an injured runner with an
  upgraded deck is back at baseline.
- **No XP, ever:** progression is capability and information — programs,
  versions, MU, intel, perception upgrades. The runner never moves faster
  and hunters never get dumber; the player's real leveling is skill.
- **Adaptation:** hit the same corp repeatedly and its stacks fortify —
  more sentries, seeded `☠` traps near paydata, and rings reshuffled or
  swapped so last run's banners go stale. Hidden information regrows.
- **Corp archetypes:** each corp owns one *signature ICE* from the pool in
  §3.1, not just stat inflation — one corp's stacks run `tmpwatch` heavy,
  another layers `snortd` grids, another seeds vortex ICE (v3). Its
  signature also appears in nastier versions in its deep rings, and its
  signature *warez* (§4) is the counter — looted only from its own vaults.
  Identical rules everywhere, different geometry of fear.
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
- **Boot banners carry rules, not just flavor.** The one `dmesg` line shown
  at a down-port must tell the player exactly what rule the next ring runs
  — it's the basis of the descend-or-jack-out decision.
- Monospace, single screen per ring, no scrolling in v1.
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
2. **v0.5 — The stack experiment:** split one server into two small rings
   joined by a port with a boot banner; jack-out only at ports; loot
   gradient steep enough that ring 0 tempts. If standing at the port
   reading the banner doesn't produce a genuine pause, stop and tune
   before building the ICE pool.
3. **v1 — ICE & programs:** the ring identity pool from §3.1 (barriers,
   sentries + static fields, permission gates, self-wipe floors),
   `?` scanning (incl. rare backdoors `◊`), traps, the starter program
   suite with `socat`, MU loadout screen.
4. **v2 — Meta-layer:** encrypted archives `≡` and `mkfifo` first (pure
   run-loop additions, cheapest experiments), then the rhizome city map
   (self-revealing nodes with stack depths, secret edges from backdoors),
   corp clock as run fee, ring restock, the repo with ring intel,
   publish-or-fence, RAM & rig heat, versioned warez, corp signature
   archetypes, tagged consequences, brain damage, legacy.
5. **v3 — Texture:** display-corruption brain damage + perception upgrades,
   corp adaptation, hunter-killer variety, vortex ICE (pulls runner *and*
   hunters 1 tile per turn within radius 3 — kite the pack into it),
   chaos-wipe trace-out (at 100% trace the board edge collapses inward one
   ring every 3 turns), campaign finale (arcology server).

---

## 8. Balance Watchlist

- **Camping/degenerate corners** (classic Robots exploit: hide behind junk
  and wait). Killers: trace escalation, port-sealing at 75%, spawn waves.
  Verify
  in playtests that waiting is never the best move.
- **Trace tuning:** too fast → panic slog; too slow → camping returns.
- **`panic` spam:** random teleport must stay a desperation tool, not a
  strategy. Charge limits and landing-on-a-hunter risk keep it honest.
- **Junk-wall fortresses:** herding is the point, but sealing yourself in
  safely forever isn't. `K` hunters pathfind around junk for exactly this
  reason.
- **Tunnel camping:** a `∩`↔`∩` link plus junk walls could make a safe
  ping-pong loop. Tunnel use costs trace, and the trace clock never stops —
  verify in playtests that tunnel loops lose to the clock.
- **Third-file math:** the expected value of greed should hover near
  break-even. If taking every file is always right, there's no decision; if
  it's always wrong, there's no temptation. The same curve governs the
  port decision one scale up: pushing one ring deeper should also hover
  near break-even.
- **The ring-1 ATM:** if a safe skim of easy outer rings is the best
  strategy, the descent is decoration. Killers: corp clock as run fee,
  ring restock, adaptation. Verify shallow farming *loses the campaign*.
- **Intel pricing:** if repo intel is too cheap, scouting runs die and
  hidden information never bites; too dear and deep runs feel like coin
  flips. Banners must stay worth earning *and* worth buying.
- **Run length creep:** permadeath on ring 3 of 4 stings in proportion to
  time invested. Rings stay small; a full descent should not exceed the
  playtime of one current v0 board by much.
- **Credit inflation:** the economy needs sinks (bribing off *tagged*,
  safehouse repairs, patch prices) or fencing dominates publishing and the
  campaign clock becomes decoration.
- **`sigkill` scarcity:** if deleting hunters is ever routine, geometry
  stops being the game. Price it, ration it, and keep it loud.
- **Rig heat tuning:** the +MU trace multiplier needs the same care as the
  base clock — too weak and MU is a pure power buy, too strong and nobody
  ever upgrades.

---

## 9. What This Game Is Not

- Not a card game. No decks, no hands, no card terminology.
- Not a Netrunner adaptation. Original fiction and terms only — the
  *mechanics of paranoia* are unownable; the trademark isn't ours.
- Not a full roguelike dungeon crawler. No inventory sprawl, no XP levels,
  no melee. The board and the clock are the game.
