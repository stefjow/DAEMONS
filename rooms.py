"""Authored rooms: hand-crafted ring-0 vaults (the anti-randomness
experiment). A room file is a header plus an ASCII drawing — the glyph
table *is* the level format.

Header lines (`key: value`), then `map:` and the drawing:

    name: junction
    ice: crond
    par: 3 files, ~20 turns
    map:
    #########
    #@..+..*#
    #...#..P#
    #########

Map glyphs (ASCII aliases so rooms stay easy to type):
    #  wall          G  gate (sudo)      ~  static field
    @  runner start  P  port (also ⌂)    *  paydata file (also ¤)
    $  credits       +  hunter           K  hunter-killer
    S  sentry, horizontal   s  sentry, vertical
    X  sentry, horizontal, phase +2      x  vertical, phase +2
    v  vent — scripted reinforcements enter here (trace waves cycle
       through vents in order; no vents = no reinforcements)
    .  floor         anything else is a wall

Every room needs exactly one `@` and one port. Rooms are fully visible —
no `?`, no archives: paranoia lives at the campaign layer, clarity here.
"""

from pathlib import Path

ROOM_DIR = Path(__file__).resolve().parent / "rooms"


class Room:
    def __init__(self, name, ice, par, grid):
        self.name = name
        self.ice = ice
        self.par = par
        self.h = len(grid)
        self.w = max(len(line) for line in grid)
        self.walls, self.gates, self.static = set(), set(), set()
        self.files, self.creds = set(), set()
        self.hunters, self.killers = set(), set()
        self.sentries, self.vents = [], []
        self.player = None
        self.port = None

        for y, line in enumerate(grid):
            for x in range(self.w):
                ch = line[x] if x < len(line) else "#"
                pos = (x, y)
                if ch == ".":
                    continue
                elif ch == "@":
                    self.player = pos
                elif ch in ("P", "⌂"):
                    self.port = pos
                elif ch in ("*", "¤"):
                    self.files.add(pos)
                elif ch == "$":
                    self.creds.add(pos)
                elif ch == "+":
                    self.hunters.add(pos)
                elif ch == "K":
                    self.killers.add(pos)
                elif ch == "G":
                    self.gates.add(pos)
                elif ch == "~":
                    self.static.add(pos)
                elif ch == "v":
                    self.vents.append(pos)
                elif ch in "SsXx":
                    self.sentries.append(
                        {"pos": pos, "axis": "h" if ch in "SX" else "v",
                         "phase": 2 if ch in "Xx" else 0})
                else:
                    self.walls.add(pos)

        if self.player is None or self.port is None:
            raise ValueError(f"room {name!r}: needs one @ and one port")


def parse_room(text, name="?"):
    head, sep, body = text.partition("map:")
    if not sep:
        raise ValueError(f"room {name!r}: no map: section")
    meta = {}
    for line in head.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    grid = [line for line in body.splitlines() if line.strip()]
    return Room(meta.get("name", name), meta.get("ice", "crond"),
                meta.get("par", ""), grid)


_cache = None


def catalog():
    """ice name -> Room, from rooms/*.txt (first file per ice wins)."""
    global _cache
    if _cache is None:
        _cache = {}
        if ROOM_DIR.is_dir():
            for path in sorted(ROOM_DIR.glob("*.txt")):
                room = parse_room(path.read_text(encoding="utf-8"),
                                  name=path.stem)
                _cache.setdefault(room.ice, room)
    return _cache


def room_for(ice):
    return catalog().get(ice)
