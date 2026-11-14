#!/usr/bin/env python3
"""
Strat-O-Matic Football Game Tracker + Defense Caller + Box Score
Works on Windows, Mac, and Pythonista (iPad). Standard library only.

Type ? or help at the prompt for the command guide.
Press Enter (or space + Enter) on a blank line to get a defensive call.
"""

import copy
import random
import re

# ---------------------------------------------------------------------------
# Clock settings
# ---------------------------------------------------------------------------
QUARTER_LENGTH = 15 * 60   # 15:00

# Regular clock (seconds)
IN_PLAY_SECS = 30          # running / completed plays
STOPPED_SECS = 15          # incompletes and penalties
KICKOFF_SECS = 15
PUNT_SECS = 30

# Touchback spots (receiving team's own yard line)
KICKOFF_TOUCHBACK_SPOT = 20
PUNT_TOUCHBACK_SPOT = 20

# Defense chart time windows (2nd and 4th quarters only)
FIVE_MIN_MARK = 5 * 60
TWO_MIN_MARK = 2 * 60

# When the game is tied, which chart rows does the defense use?
# False = treat tie as "Behind", True = treat tie as "Ahead"
TIE_COUNTS_AS_AHEAD = False

TIMEOUTS_PER_HALF = 3

# Two-minute clock: 18 ticks from 2:00 down to 0:00
TWO_MIN_TICKS = [120, 112, 105, 97, 90, 82, 75, 67, 60,
                 52, 45, 37, 30, 22, 15, 8, 1, 0]

# How many ticks each kind of play uses on the two-minute clock
TWO_MIN_COSTS = {
    "live": 4,         # running / completed plays
    "incomplete": 2,
    "penalty": 1,
    "punt": 1,
    "kickoff": 1,
    "spike": 0,        # a spike is its own play and stops the clock
}

# Two-minute options (applied right AFTER a play)
HURRY_UP_TICKS = 1         # Hurry Up: the play takes 1 fewer tick
TIMEOUT_TICKS = 3          # Time Out (offense or defense): up to 3 fewer ticks


def play_clock_cost(game, kind):
    """Regular-clock seconds for a play type."""
    return {
        "live": IN_PLAY_SECS,
        "incomplete": STOPPED_SECS,
        "penalty": STOPPED_SECS,
        "punt": PUNT_SECS,
        "kickoff": KICKOFF_SECS,
        "spike": 0,
    }[kind]


# ---------------------------------------------------------------------------
# Roster / stats settings
# ---------------------------------------------------------------------------
ROLES = ["QB", "HB", "HB2", "FB", "TE1", "TE2", "WR1", "WR2", "WR3", "WR4"]

# Codes used in play commands
RUSH_CODES = {"q": "QB", "h": "HB", "h2": "HB2", "f": "FB"}
RECV_CODES = {"w1": "WR1", "w2": "WR2", "w3": "WR3", "w4": "WR4",
              "t1": "TE1", "t2": "TE2", "h": "HB", "h2": "HB2", "f": "FB"}

# Who can fumble (w and t alone will ask which WR / TE)
FUM_CODES = {"q": "QB", "h": "HB", "h2": "HB2", "f": "FB",
             "w1": "WR1", "w2": "WR2", "w3": "WR3", "w4": "WR4",
             "t1": "TE1", "t2": "TE2"}

STAT_KEYS = ("att", "cmp", "pyds", "ptd", "int",   # passing
             "car", "ryds", "rtd",                 # rushing
             "tgt", "rec", "recyds", "rectd",      # receiving
             "fum")                                # fumbles lost


def new_stat():
    return {k: 0 for k in STAT_KEYS}


# ---------------------------------------------------------------------------
# DEFENSE CHART
#
# Key: (down, yards_to_go_bucket) -> 4 blocks, in this order:
#   OPP_50_20  Opponent territory, 50 to 20 (offense's own 50 back to its own 20)
#   OWN_20_50  Defense's own territory, 20 to 50
#   OPP_0_20   Opponent territory, 0 to 20 (offense backed up near its own goal)
#   OWN_0_20   Defense's own territory, 0 to 20 (offense in scoring position)
#
# Each block has 6 rows, in this order:
#   Ahead/Standard, Ahead/5 min, Ahead/2 min,
#   Behind/Standard, Behind/5 min, Behind/2 min
#
# Each row: (Run, RunCall, Blitz, FallBack, DTeam)
# Pass % is just 100 - Run.
# ---------------------------------------------------------------------------
PLACES = ["OPP_50_20", "OWN_20_50", "OPP_0_20", "OWN_0_20"]
YTG_BUCKETS = ["10", "11+", "5-9", "1-4"]

CHART = {
    (1, "10"): [
        [(55,30,20,20,20), (35,15,30,20,20), (15,15,30,20,20), (60,30,20,20,20), (65,30,10,10,10), (80,45,10,10,10)],
        [(60,30,20,20,20), (35,15,30,20,20), (15,15,30,20,20), (60,30,20,20,20), (65,30,10,10,10), (80,45,10,10,10)],
        [(65,30,20,20,20), (35,15,30,20,20), (15,15,30,20,20), (60,30,20,20,20), (65,30,10,10,10), (80,45,10,10,10)],
        [(45,30,20,20,20), (40,15,35,20,20), (35,15,35,20,20), (65,30,20,20,20), (70,35,15,10,15), (85,45,10,10,10)],
    ],
    (1, "11+"): [
        [(55,15,25,30,25), (30,10,30,35,30), (10,5,30,35,30), (60,15,25,30,25), (60,25,15,20,25), (75,30,15,15,15)],
        [(50,15,25,30,25), (30,10,30,35,30), (10,5,30,35,30), (60,15,25,30,25), (60,25,15,20,25), (75,30,15,15,15)],
        [(70,15,25,30,25), (35,10,30,35,30), (15,5,30,35,30), (60,15,25,30,25), (60,25,15,20,25), (75,30,15,15,15)],
        [(60,20,20,20,20), (35,15,25,35,30), (20,15,25,35,30), (65,15,25,30,25), (70,30,15,25,20), (90,35,10,20,15)],
    ],
    (1, "5-9"): [
        [(55,30,20,20,20), (40,15,30,20,20), (25,15,30,20,20), (60,30,20,20,20), (65,30,10,10,10), (80,45,10,10,10)],
        [(55,30,20,20,20), (40,15,30,20,20), (25,15,30,20,20), (60,30,20,20,20), (65,30,10,10,10), (80,45,10,10,10)],
        [(55,30,20,20,20), (35,15,30,20,20), (15,15,30,20,20), (60,30,20,20,20), (60,30,10,10,10), (75,45,10,10,10)],
        [(50,30,20,20,20), (35,15,35,20,20), (30,15,35,20,20), (70,30,20,20,20), (75,35,15,10,15), (90,45,10,10,10)],
    ],
    (1, "1-4"): [
        [(50,30,20,20,20), (50,15,30,20,20), (35,15,30,20,20), (55,30,20,20,20), (80,30,10,10,10), (90,45,10,10,10)],
        [(45,30,20,20,20), (50,15,30,20,20), (35,15,30,20,20), (55,30,20,20,20), (80,30,10,10,10), (90,45,10,10,10)],
        [(55,30,20,20,20), (45,15,30,20,20), (35,15,30,20,20), (55,30,20,20,20), (65,30,10,10,10), (75,45,10,10,10)],
        [(55,30,20,20,20), (45,15,35,20,20), (35,15,35,20,20), (60,30,20,20,20), (75,35,15,10,15), (90,45,10,10,10)],
    ],
    (2, "10"): [
        [(50,30,20,20,20), (35,15,30,20,20), (25,15,30,20,20), (50,30,20,20,20), (65,30,10,10,10), (75,45,10,10,10)],
        [(50,30,20,20,20), (35,15,30,20,20), (25,15,30,20,20), (50,30,20,20,20), (65,30,10,10,10), (75,45,10,10,10)],
        [(45,30,20,20,20), (40,15,30,20,20), (20,15,30,20,20), (60,30,20,20,20), (70,30,10,10,10), (80,45,10,10,10)],
        [(50,30,20,20,20), (35,15,35,20,20), (15,15,35,20,20), (55,30,20,20,20), (65,35,15,10,15), (80,45,10,10,10)],
    ],
    (2, "11+"): [
        [(40,15,25,30,25), (30,10,30,35,30), (20,5,30,35,30), (55,15,25,30,25), (70,25,15,20,25), (80,30,15,15,15)],
        [(40,15,25,30,25), (30,10,30,35,30), (20,5,30,35,30), (55,15,25,30,25), (70,25,15,20,25), (80,30,15,15,15)],
        [(40,15,25,30,25), (35,10,30,35,30), (25,5,30,35,30), (45,15,25,30,25), (65,25,15,20,25), (70,30,15,15,15)],
        [(45,20,20,20,20), (35,15,25,35,30), (25,15,25,35,30), (50,15,25,30,25), (55,30,15,25,20), (60,35,10,20,15)],
    ],
    (2, "5-9"): [
        [(55,30,20,20,20), (35,15,30,20,20), (15,15,30,20,20), (60,30,20,20,20), (65,30,10,10,10), (80,45,10,10,10)],
        [(60,30,20,20,20), (35,15,30,20,20), (15,15,30,20,20), (60,30,20,20,20), (65,30,10,10,10), (80,45,10,10,10)],
        [(65,30,20,20,20), (35,15,30,20,20), (15,15,30,20,20), (60,30,20,20,20), (65,30,10,10,10), (80,45,10,10,10)],
        [(45,30,20,20,20), (40,15,35,20,20), (35,15,35,20,20), (65,30,20,20,20), (70,35,15,10,15), (85,45,10,10,10)],
    ],
    (2, "1-4"): [
        [(50,30,20,20,20), (40,15,30,20,20), (20,15,30,20,20), (50,30,20,20,20), (60,30,10,10,10), (80,45,10,10,10)],
        [(45,30,20,20,20), (40,15,30,20,20), (35,15,30,20,20), (65,30,20,20,20), (70,30,10,10,10), (85,45,10,10,10)],
        [(60,30,20,20,20), (40,15,30,20,20), (20,15,30,20,20), (60,30,20,20,20), (70,30,10,10,10), (80,45,10,10,10)],
        [(50,30,20,20,20), (40,15,35,20,20), (20,15,35,20,20), (50,30,20,20,20), (60,35,15,10,15), (80,45,10,10,10)],
    ],
    (3, "10"): [
        [(25,20,35,40,35), (15,15,35,40,35), (10,10,35,40,35), (45,30,20,20,15), (50,30,20,20,15), (55,35,15,20,15)],
        [(25,20,35,40,35), (15,15,35,40,35), (10,10,35,40,35), (50,30,20,20,15), (60,30,20,20,15), (65,35,15,20,15)],
        [(40,15,35,45,35), (35,10,35,45,35), (20,5,35,45,35), (65,30,15,15,10), (70,30,10,10,10), (80,30,10,10,10)],
        [(25,20,40,40,25), (15,15,35,40,30), (10,15,35,40,30), (50,40,15,10,10), (60,35,20,15,10), (65,35,15,15,10)],
    ],
    (3, "5-9"): [
        [(35,20,35,40,35), (25,15,35,40,35), (10,10,35,40,35), (40,30,20,20,15), (35,30,20,20,15), (30,35,15,20,15)],
        [(35,20,35,40,35), (20,15,35,40,35), (10,10,35,40,35), (40,30,20,20,15), (35,30,20,20,15), (30,35,15,20,15)],
        [(30,15,35,45,35), (20,10,35,45,35), (10,5,35,45,35), (40,30,15,15,10), (40,30,10,10,10), (35,30,10,10,10)],
        [(40,20,40,40,25), (25,15,35,40,30), (15,15,35,40,30), (45,40,15,10,10), (45,35,20,15,10), (50,35,15,15,10)],
    ],
    (3, "1-4"): [
        [(50,30,35,30,20), (40,20,35,35,30), (25,15,35,40,35), (50,40,30,20,25), (65,40,25,20,25), (75,40,25,20,25)],
        [(50,30,35,30,20), (40,20,35,35,30), (25,15,35,40,35), (50,40,30,20,25), (65,40,25,20,25), (75,40,25,20,25)],
        [(55,30,35,30,20), (40,20,35,35,30), (30,15,35,40,35), (55,40,30,20,25), (70,40,25,20,25), (85,40,25,20,25)],
        [(45,25,40,40,25), (40,15,40,40,30), (25,15,35,40,30), (55,35,20,15,10), (65,35,20,15,10), (75,35,20,15,10)],
    ],
}

# 3rd & 11+ is identical to 3rd & 10 on your chart
CHART[(3, "11+")] = CHART[(3, "10")]

# 4th down: same numbers for every ball placement within each yardage group
_FOURTH_LONG = [(10,5,15,50,35), (10,5,15,50,35), (5,5,20,50,35),
                (10,5,15,50,35), (15,5,15,50,35), (15,5,20,50,35)]
_FOURTH_MID = [(10,5,20,40,35), (10,5,20,40,35), (5,5,25,40,35),
               (10,5,15,35,35), (15,5,15,35,35), (15,5,25,35,35)]
_FOURTH_SHORT = [(50,50,35,10,15), (40,50,35,10,15), (35,50,35,15,20),
                 (50,50,35,10,15), (60,50,35,10,15), (75,50,35,15,20)]
CHART[(4, "10")] = [_FOURTH_LONG] * 4
CHART[(4, "11+")] = [_FOURTH_LONG] * 4
CHART[(4, "5-9")] = [_FOURTH_MID] * 4
CHART[(4, "1-4")] = [_FOURTH_SHORT] * 4

# Quick sanity check so a missing chart entry fails loudly at startup
for _d in (1, 2, 3, 4):
    for _y in YTG_BUCKETS:
        assert (_d, _y) in CHART and len(CHART[(_d, _y)]) == 4, (_d, _y)

SCORE_TIME_LABELS = [
    "Ahead / Standard", "Ahead / 5 Min left", "Ahead / 2 Min left",
    "Behind / Standard", "Behind / 5 Min left", "Behind / 2 Min left",
]
PLACE_LABELS = {
    "OPP_50_20": "Opponent 50-20",
    "OWN_20_50": "Own 20-50",
    "OPP_0_20": "Opponent 0-20",
    "OWN_0_20": "Own 0-20",
}

# ---------------------------------------------------------------------------
# D-TEAM TARGETS: who gets double-teamed when a D-Team call is made.
# One list, in priority order (most likely first). Weights add up to 100.
# ---------------------------------------------------------------------------
DTEAM_TARGETS = (["WR1", "WR2", "TE1", "WR3", "HB1"],
                 [35,    30,    15,    12,    8])

# ---------------------------------------------------------------------------
# FLAT PASS (percent of PASS calls). Same for every placement and time.
# ---------------------------------------------------------------------------
SHORT_YARDAGE = 3                  # "3 or less" yards to go
FLAT_PASS_BY_DOWN = {1: 20, 2: 15, 3: 20}
FLAT_PASS_4TH_SHORT = 20           # 4th and 3 or less
FLAT_PASS_4TH_LONG = 10            # 4th and 4 or more

# ---------------------------------------------------------------------------
# RUN KEYS (percent of RUN calls), plus who gets keyed.
# No key is ever called on 3rd or 4th down with more than 3 to go.
# ---------------------------------------------------------------------------
KEY_CHANCE_EARLY = 10                       # 1st and 2nd down
KEY_CHANCE_SHORT = {3: 20, 4: 35}           # 3rd / 4th and 3 or less
KEY_SPLIT_EARLY = (["QB", "HB", "FB"], [10, 70, 20])
KEY_SPLIT_SHORT = (["QB", "HB", "FB"], [35, 55, 10])


# ---------------------------------------------------------------------------
# Game state
# ---------------------------------------------------------------------------
STATE_FIELDS = ("quarter", "clock", "home_score", "away_score",
                "poss", "pos", "down", "to_go",
                "timeouts_home", "timeouts_away",
                "last_ticks", "stats")


class Game:
    """
    Ball position (pos) is yards from the HOME goal line:
        0 = home goal line, 50 = midfield, 100 = away goal line.
    Home drives toward 100, away drives toward 0.
    """

    def __init__(self, home="HOME", away="AWAY"):
        self.home = home
        self.away = away
        self.quarter = 1
        self.clock = QUARTER_LENGTH
        self.home_score = 0
        self.away_score = 0
        self.poss = "h"
        self.pos = 25
        self.down = 1
        self.to_go = 10
        self.timeouts_home = TIMEOUTS_PER_HALF
        self.timeouts_away = TIMEOUTS_PER_HALF
        self.last_ticks = 0      # ticks the most recent play used (2-min clock)
        self.roster = {"h": {r: "" for r in ROLES},
                       "a": {r: "" for r in ROLES}}
        self.stats = {"h": {r: new_stat() for r in ROLES},
                      "a": {r: new_stat() for r in ROLES}}
        self.history = []

    def snapshot(self):
        return copy.deepcopy({f: getattr(self, f) for f in STATE_FIELDS})

    def restore(self, snap):
        for f, v in copy.deepcopy(snap).items():
            setattr(self, f, v)

    def direction(self):
        return 1 if self.poss == "h" else -1

    def yards_to_goal(self):
        """Yards the OFFENSE needs to score."""
        return 100 - self.pos if self.poss == "h" else self.pos

    def offense(self):
        return self.home if self.poss == "h" else self.away

    def defense(self):
        return self.away if self.poss == "h" else self.home

    def defense_key(self):
        """'h' or 'a' for the team currently on defense."""
        return "a" if self.poss == "h" else "h"

    def flip_possession(self):
        self.poss = "a" if self.poss == "h" else "h"

    def team_name(self, team):
        return self.home if team == "h" else self.away

    def timeouts_for(self, team):
        return self.timeouts_home if team == "h" else self.timeouts_away

    def use_timeout_for(self, team):
        if team == "h":
            self.timeouts_home -= 1
        else:
            self.timeouts_away -= 1


def player_label(g, team, role):
    name = g.roster[team].get(role, "")
    return "{} ({})".format(name, role) if name else role


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------
def fmt_clock(secs):
    return "{:02d}:{:02d}".format(secs // 60, secs % 60)


def ordinal(n):
    return {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}.get(n, str(n))


def ball_text(g):
    if g.pos < 50:
        return "{} {}".format(g.home, g.pos)
    if g.pos > 50:
        return "{} {}".format(g.away, 100 - g.pos)
    return "Midfield (50)"


def down_text(g):
    if g.to_go >= g.yards_to_goal():
        return "{} & Goal".format(ordinal(g.down))
    return "{} & {}".format(ordinal(g.down), g.to_go)


def show_status(g):
    tag = "  [2-MIN CLOCK]" if in_two_minute(g) else ""
    print("")
    print("=" * 36)
    print(" Q{}   Clock: {}{}".format(g.quarter, fmt_clock(g.clock), tag))
    print(" {} {}  -  {} {}".format(g.home, g.home_score, g.away, g.away_score))
    print(" {}   ({} ball)".format(down_text(g), g.offense()))
    print(" Ball on: {}".format(ball_text(g)))
    print(" Timeouts: {} {}  |  {} {}".format(
        g.home, g.timeouts_home, g.away, g.timeouts_away))
    print("=" * 36)


def print_box(g):
    print("")
    print("=" * 60)
    print(" BOX SCORE   {} {} - {} {}   (Q{} {})".format(
        g.home, g.home_score, g.away, g.away_score,
        g.quarter, fmt_clock(g.clock)))
    print("=" * 60)

    for team, tname in (("h", g.home), ("a", g.away)):
        st = g.stats[team]
        lines = []

        q = st["QB"]
        if q["att"] or q["int"]:
            pct = 100.0 * q["cmp"] / q["att"] if q["att"] else 0.0
            lines.append("  PASSING    {:<22} {}/{}  {:.1f}%  {} yds  {} TD  {} INT".format(
                player_label(g, team, "QB"), q["cmp"], q["att"], pct,
                q["pyds"], q["ptd"], q["int"]))

        for role in ("QB", "HB", "HB2", "FB"):
            s = st[role]
            if s["car"]:
                avg = float(s["ryds"]) / s["car"]
                lines.append("  RUSHING    {:<22} {} car  {} yds  {:.1f} avg  {} TD".format(
                    player_label(g, team, role), s["car"], s["ryds"], avg,
                    s["rtd"]))

        for role in ("WR1", "WR2", "WR3", "WR4", "TE1", "TE2", "HB", "HB2", "FB"):
            s = st[role]
            if s["tgt"]:
                lines.append("  RECEIVING  {:<22} {} rec / {} tgt  {} yds  {} TD".format(
                    player_label(g, team, role), s["rec"], s["tgt"],
                    s["recyds"], s["rectd"]))

        for role in ROLES:
            if st[role]["fum"]:
                lines.append("  FUMBLES    {:<22} {} lost".format(
                    player_label(g, team, role), st[role]["fum"]))

        print("")
        print(" {}".format(tname))
        if lines:
            for line in lines:
                print(line)
        else:
            print("  (no stats yet)")
    print("")
    print("=" * 60)


HELP_TEXT = """
================ COMMAND GUIDE ================

DEFENSE CALL
  Enter   Press Enter (or space + Enter) on a blank line.
  o       Same thing, typed.
  Run calls can come with: Key HB / Key QB / Key FB, and LBs in the run zone.
  Pass calls can be: Blitz, Fall back, Flat Pass covered, or D-Team
  (WR1, WR2, TE1, WR3 or HB1 double-teamed). Only one per pass call.

PLAYS   (all of these also build the box score)
  yX      Ball moves X yards. No player credited.   y5   y-5
  yXh     Rush by the HB.                            y3h   y-2h
            q = QB   h = HB   h2 = HB2   f = FB      y4q   y2f
  yXw2    Completion, QB to WR2, X yards.            y12w2   y8t1
            w1-w4 = WRs   t1 t2 = TEs
  yXqh    QB to a back (q = QB threw it).            y9qh   y6qf   y4qh2
  i       Incomplete pass (QB attempt, no target).
  iw1     Incomplete intended for WR1.               iw1   it2   iqh
  xX      Penalty. Moves the ball X yards, down advances.   x5   x-10
  xXr     Same, but repeat the down.                 x-10r
  Touchdowns are credited automatically when the ball reaches the end zone.

TURNOVERS
  phi     Interception. HOME takes over, QB of the other team gets the INT.
  pai     Same, AWAY takes over.
  phfh    Fumble lost by the other team's HB, HOME takes over.
  pafw    Fumble by a WR (asks which one), AWAY takes over.
            q = QB   h = HB   h2 = HB2   f = FB   w1-w4 = WRs   t1 t2 = TEs
            (w or t alone will ask which one)
  New offense gets 1st & 10 at the current spot. Use b / d to adjust.
  Enter the play first (iw1, y3h...) so the clock and attempt are counted.

KICKING
  koX.Y   Kickoff. Lands on the receiving team's X yard line, returned Y.
            ko10.32 -> ball ends up on the receiver's 42
            ko0.20  -> kicked into the end zone, returned out to the 20
  ko.tb   Kickoff touchback (ball comes out to the 20).
  pX.Y    Punt X yards, returned Y yards.        p45.7
  p.tb    Punt touchback (ball comes out to the 20).
  Leave off the .Y for no return (fair catch / downed): ko10 or p45
  The team with possession is the KICKING team. After the kick,
  possession flips and it's 1st & 10.

STATS
  box     Show the box score (passing, rushing, receiving, fumbles).

TWO-MINUTE CLOCK (2nd and 4th quarter, at 2:00 or less)
  The clock moves in ticks instead of seconds (18 ticks, ~7 sec each):
    run / completed play = 4 ticks     incomplete = 2 ticks
    penalty, punt, kickoff = 1 tick    spike = 0 ticks
  After each run/completed play or incomplete you'll be asked:
    1  Hurry Up        that play takes 1 fewer tick
    2  Spike Ball      a separate play: loses a down, clock stops
    3  Time Out        offense timeout: play takes up to 3 fewer ticks
    4  Defense Timeout defense timeout: same clock effect
    Enter  = none
  You can also type these yourself, right after a play:
    sp      Spike (2-minute clock only)
    to      Timeout for the team with the ball (offense)
    dt      Timeout for the team on defense
  The clock never gets back more ticks than the play used, so if both
  teams call a timeout on the same play, the second one saves less.

MANUAL FIXES
  tMM:SS  Set the clock.            t12:45
  qX      Start quarter X (1-4), clock resets to 15:00.   q4
            (q1 and q3 also refill both teams' timeouts)
  bhX     Place ball on HOME team's X yard line.          bh35
  baX     Place ball on AWAY team's X yard line.          ba20
  dX.Y    Set down X and yards to go Y.                   d3.7
  shX     Set HOME score to X.                            sh14
  saX     Set AWAY score to X.                            sa7
  ph      Home team gets the ball.
  pa      Away team gets the ball.
  tmhX    Set HOME timeouts remaining.                    tmh2
  tmaX    Set AWAY timeouts remaining.                    tma3

OTHER
  u       Undo the last change (stats and timeouts too).
  ? / help  Show this guide.
  quit    Exit.

NOTES
  - Gaining enough yards for a first down resets to 1st & 10.
  - Fail to convert on 4th down = turnover on downs (auto possession flip).
  - Reaching the end zone prints a TOUCHDOWN reminder. Update the score
    with sh/sa, then set up the next possession with ph/pa, bh/ba, d.
  - Plays typed without a player (like y5) move the ball but don't add
    to anyone's stats.
  - When the clock hits 0:00 you'll get a reminder. Use qX to move on.
  - Tied game: defense uses the "Behind" rows (change TIE_COUNTS_AS_AHEAD
    at the top of the script to flip that).
===============================================
"""


# ---------------------------------------------------------------------------
# Clock
# ---------------------------------------------------------------------------
def in_two_minute(g):
    return g.quarter in (2, 4) and g.clock <= TWO_MIN_MARK


def set_clock(g, new_clock):
    before = g.clock
    g.clock = max(0, new_clock)
    if g.quarter in (2, 4) and before > TWO_MIN_MARK >= g.clock > 0:
        print(">> 2-MINUTE CLOCK now in effect.")
    if before > 0 and g.clock == 0:
        if g.quarter < 4:
            print(">> END OF Q{}. Type q{} to start the next quarter."
                  .format(g.quarter, g.quarter + 1))
        else:
            print(">> END OF Q4. Regulation is over.")


def tick_index(clock):
    """Position on the two-minute clock (snaps to the nearest tick)."""
    return min(range(len(TWO_MIN_TICKS)),
               key=lambda i: abs(TWO_MIN_TICKS[i] - clock))


def spend_clock(g, kind):
    """
    Take time off the clock for a play.
    kind: 'live', 'incomplete', 'penalty', 'punt', 'kickoff', or 'spike'
    """
    if in_two_minute(g):
        ticks = TWO_MIN_COSTS[kind]
        g.last_ticks = ticks
        if ticks == 0:
            return
        idx = min(tick_index(g.clock) + ticks, len(TWO_MIN_TICKS) - 1)
        set_clock(g, TWO_MIN_TICKS[idx])
    else:
        g.last_ticks = 0
        set_clock(g, g.clock - play_clock_cost(g, kind))


def give_back_ticks(g, n):
    """Put n ticks back on the two-minute clock (never more than the last play used)."""
    n = min(n, g.last_ticks)
    if n <= 0:
        return 0
    idx = max(0, tick_index(g.clock) - n)
    g.clock = TWO_MIN_TICKS[idx]
    g.last_ticks -= n
    return n


# ---------------------------------------------------------------------------
# Play logic
# ---------------------------------------------------------------------------
def new_first_down(g):
    g.down = 1
    g.to_go = min(10, g.yards_to_goal())


def advance_down(g):
    """
    Next down. Returns True if the same team still has the ball,
    False if it was a turnover on downs.
    """
    g.down += 1
    if g.down > 4:
        print(">> TURNOVER ON DOWNS. {} takes over.".format(g.defense()))
        g.flip_possession()
        new_first_down(g)
        return False
    return True


def apply_yards(g, yards, kind, repeat_down=False):
    """
    Move the ball and update the down.
    Returns "cont", "td", "safety", or "turnover".
    """
    g.pos += g.direction() * yards
    spend_clock(g, kind)

    ytg = g.yards_to_goal()
    if ytg <= 0:
        g.pos = 100 if g.poss == "h" else 0
        print(">> TOUCHDOWN {}! Update score (sh/sa), then set up the next "
              "possession (ph/pa, bh/ba, d).".format(g.offense()))
        return "td"
    if ytg >= 100:
        g.pos = 0 if g.poss == "h" else 100
        print(">> SAFETY? Ball is in {}'s own end zone. Update score "
              "(sh/sa) and set up the next possession.".format(g.offense()))
        return "safety"

    g.to_go -= yards
    if g.to_go <= 0:
        new_first_down(g)
        print(">> FIRST DOWN {}".format(g.offense()))
        return "cont"

    if repeat_down:
        return "cont"

    return "cont" if advance_down(g) else "turnover"


def record_stats(g, team, kind, yards, rusher, receiver, td):
    """kind: 'run', 'complete', or 'incomplete'. team is 'h' or 'a'."""
    st = g.stats[team]
    if kind == "run" and rusher:
        s = st[rusher]
        s["car"] += 1
        s["ryds"] += yards
        if td:
            s["rtd"] += 1
            print(">> TD: {}".format(player_label(g, team, rusher)))
    elif kind == "complete" and receiver:
        qb = st["QB"]
        r = st[receiver]
        qb["att"] += 1
        qb["cmp"] += 1
        qb["pyds"] += yards
        r["tgt"] += 1
        r["rec"] += 1
        r["recyds"] += yards
        if td:
            qb["ptd"] += 1
            r["rectd"] += 1
            print(">> TD: {} to {}".format(
                player_label(g, team, "QB"), player_label(g, team, receiver)))
    elif kind == "incomplete":
        st["QB"]["att"] += 1
        if receiver:
            st[receiver]["tgt"] += 1


def spike(g):
    """A spike is its own play: loses a down, stops the clock."""
    print(">> SPIKE by {}. Down lost.".format(g.offense()))
    spend_clock(g, "spike")
    advance_down(g)


def hurry_up(g):
    saved = give_back_ticks(g, HURRY_UP_TICKS)
    print(">> HURRY UP. {} tick(s) saved.".format(saved))


def do_timeout(g, defense=False):
    """
    Timeout right after a play, for the team with the ball (default) or
    the team on defense (defense=True). Returns True if it was used.
    """
    team = g.defense_key() if defense else g.poss
    name = g.team_name(team)
    if g.timeouts_for(team) <= 0:
        print(">> No timeouts left for {}.".format(name))
        return False
    g.use_timeout_for(team)
    saved = give_back_ticks(g, TIMEOUT_TICKS) if in_two_minute(g) else 0
    print(">> TIMEOUT {} ({}). {} tick(s) saved. ({} left)".format(
        name, "defense" if defense else "offense", saved,
        g.timeouts_for(team)))
    return True


def two_minute_options(g):
    """Asked right after a play on the two-minute clock."""
    print(">> 2-MINUTE options ({} ball):".format(g.offense()))
    print("   1 = Hurry Up   2 = Spike Ball   "
          "3 = Time Out {} ({} left)".format(
              g.offense(), g.timeouts_for(g.poss)))
    print("   4 = Defense Timeout {} ({} left)   Enter = none".format(
        g.defense(), g.timeouts_for(g.defense_key())))
    while True:
        ans = input("   option> ").strip()
        if ans == "":
            return
        if ans == "1":
            hurry_up(g)
            return
        if ans == "2":
            spike(g)
            return
        if ans == "3":
            if do_timeout(g):
                return
            continue
        if ans == "4":
            if do_timeout(g, defense=True):
                return
            continue
        print("   Enter 1, 2, 3, 4, or just press Enter.")


def run_live_play(g, kind, yards=0, rusher=None, receiver=None):
    """
    Run/completed plays (kind='live') and incompletions (kind='incomplete').
    Credits stats, then offers the two-minute options if they apply.
    """
    team = g.poss
    was_two = in_two_minute(g)

    if kind == "incomplete":
        spend_clock(g, "incomplete")
        record_stats(g, team, "incomplete", 0, None, receiver, False)
        status = "cont" if advance_down(g) else "turnover"
    else:
        ytg_before = g.yards_to_goal()
        status = apply_yards(g, yards, "live")
        td = (status == "td")
        credited = min(yards, ytg_before) if td else yards
        if rusher:
            record_stats(g, team, "run", credited, rusher, None, td)
        elif receiver:
            record_stats(g, team, "complete", credited, None, receiver, td)

    if was_two and status == "cont":
        two_minute_options(g)


def ask_which(g, code):
    """For fumble codes 'w' or 't' with no number: ask which WR / TE."""
    kind = "WR" if code == "w" else "TE"
    top = 4 if code == "w" else 2
    while True:
        ans = input("   Which {} (1-{})? Enter = skip stat: ".format(kind, top)).strip()
        if ans == "":
            return None
        if ans.isdigit() and 1 <= int(ans) <= top:
            return "{}{}".format(kind, ans)
        print("   Enter a number 1-{}.".format(top))


def turnover(g, to_team, cause, role=None):
    """
    to_team ('h' or 'a') takes the ball. cause is 'int' or 'fum'.
    The team that HAD the ball gets charged. Returns True if it happened.
    """
    if g.poss == to_team:
        print(">> {} already has the ball.".format(g.offense()))
        return False
    lost = g.poss
    if cause == "int":
        g.stats[lost]["QB"]["int"] += 1
        print(">> INTERCEPTION thrown by {}.".format(player_label(g, lost, "QB")))
    else:
        if role:
            g.stats[lost][role]["fum"] += 1
            print(">> FUMBLE lost by {}.".format(player_label(g, lost, role)))
        else:
            print(">> FUMBLE lost.")
    g.poss = to_team
    new_first_down(g)
    print(">> {} takes over. {}. (Use b / d to adjust the spot.)".format(
        g.offense(), down_text(g)))
    return True


# ---------------------------------------------------------------------------
# Kicking
# ---------------------------------------------------------------------------
def give_ball(g, spot, label, kind):
    """
    Flip possession to the receiving team and put the ball at `spot`
    (yards from the RECEIVING team's own goal line). 1st down.
    """
    g.flip_possession()
    spend_clock(g, kind)
    if spot >= 100:
        g.pos = 100 if g.poss == "h" else 0
        print(">> {} RETURN TOUCHDOWN {}! Update score (sh/sa). {} kicks "
              "off next.".format(label, g.offense(), g.offense()))
        return
    g.pos = spot if g.poss == "h" else 100 - spot
    new_first_down(g)


def kickoff(g, landing, ret):
    """landing=None means touchback."""
    if landing is None or landing + ret <= 0:
        print(">> KICKOFF touchback.")
        give_ball(g, KICKOFF_TOUCHBACK_SPOT, "KICKOFF", "kickoff")
    else:
        print(">> KICKOFF to the {}, returned {}.".format(landing, ret))
        give_ball(g, landing + ret, "KICKOFF", "kickoff")


def punt(g, dist, ret):
    """dist=None means touchback."""
    landing = None if dist is None else g.yards_to_goal() - dist
    if landing is None or landing <= 0:
        print(">> PUNT touchback.")
        give_ball(g, PUNT_TOUCHBACK_SPOT, "PUNT", "punt")
    else:
        print(">> PUNT {} yards, returned {}.".format(dist, ret))
        give_ball(g, landing + ret, "PUNT", "punt")


# ---------------------------------------------------------------------------
# Defense call
# ---------------------------------------------------------------------------
def ytg_bucket(to_go):
    if to_go >= 11:
        return "11+"
    if to_go == 10:
        return "10"
    if to_go >= 5:
        return "5-9"
    return "1-4"


def place_bucket(g):
    """Ball placement from the DEFENSE's point of view."""
    ytg = g.yards_to_goal()          # yards from the defense's goal line
    if ytg <= 20:
        return 3                     # Own 0-20 (scoring position)
    if ytg <= 50:
        return 1                     # Own 20-50
    if ytg <= 80:
        return 0                     # Opponent 50-20
    return 2                         # Opponent 0-20


def score_time_index(g):
    """0-2 = defense Ahead (Std, 5 min, 2 min); 3-5 = Behind."""
    if g.poss == "h":
        def_lead = g.away_score - g.home_score
    else:
        def_lead = g.home_score - g.away_score

    if def_lead > 0:
        ahead = True
    elif def_lead < 0:
        ahead = False
    else:
        ahead = TIE_COUNTS_AS_AHEAD

    t = 0
    if g.quarter in (2, 4):
        if g.clock <= TWO_MIN_MARK:
            t = 2
        elif g.clock <= FIVE_MIN_MARK:
            t = 1
    return t if ahead else 3 + t


def flat_pass_chance(g):
    """Percent of pass calls that are Flat Pass covered."""
    down = min(max(g.down, 1), 4)
    if down == 4:
        if g.to_go <= SHORT_YARDAGE:
            return FLAT_PASS_4TH_SHORT
        return FLAT_PASS_4TH_LONG
    return FLAT_PASS_BY_DOWN[down]


def run_key_odds(g):
    """
    Returns (key_chance, split) for run calls.
    split is None when keys aren't used (3rd/4th and more than 3 to go).
    """
    down = min(max(g.down, 1), 4)
    if down in (1, 2):
        return KEY_CHANCE_EARLY, KEY_SPLIT_EARLY
    if g.to_go <= SHORT_YARDAGE:
        return KEY_CHANCE_SHORT[down], KEY_SPLIT_SHORT
    return 0, None


def roll(pct):
    """True pct% of the time."""
    return random.randint(1, 100) <= pct


def weighted(options):
    names, weights = options
    return random.choices(names, weights=weights)[0]


def call_defense(g):
    down = min(max(g.down, 1), 4)
    yb = ytg_bucket(g.to_go)
    pi = place_bucket(g)
    si = score_time_index(g)
    run, run_call, blitz, fall_back, d_team = CHART[(down, yb)][pi][si]

    print("")
    print(">> Chart row: {} & {} | {} | {}".format(
        ordinal(down), yb, PLACE_LABELS[PLACES[pi]], SCORE_TIME_LABELS[si]))
    print("   (Run {}% / Pass {}%)".format(run, 100 - run))

    if roll(run):
        parts = ["Run"]

        # Run key: independent of the linebacker run-zone call
        key_chance, key_split = run_key_odds(g)
        if key_chance and roll(key_chance):
            parts.append("Key " + weighted(key_split))

        if roll(run_call):
            parts.append("Linebackers in run zone. "
                         "No LB in passing zone or flat pass")
        text = ", ".join(parts)
    else:
        text = "Pass"
        chances = {"blitz": blitz, "fall": fall_back, "dteam": d_team,
                   "flat": flat_pass_chance(g)}
        order = list(chances.keys())
        random.shuffle(order)          # random order, first hit wins
        for choice in order:
            if not roll(chances[choice]):
                continue
            if choice == "blitz":
                text += ", Blitz. No LB in short pass or flat pass zones"
            elif choice == "fall":
                text += (", Fall back. Defenders in short and long pass zones. "
                         "No defender in flat pass or running zones")
            elif choice == "flat":
                text += ", Flat Pass covered. No LB in running zones"
            else:
                target = weighted(DTEAM_TARGETS)
                text += (", {} double teamed. No defender in flat pass or "
                         "running zones".format(target))
            break

    print(">> Defense called -> " + text)


# ---------------------------------------------------------------------------
# Command handling
# returns "mut" (state changed), "info" (no change, show status),
#         "quiet" (no change, no status), or None (error)
# ---------------------------------------------------------------------------
def handle(g, raw):
    cmd = raw.strip().lower().replace(" ", "")

    if cmd == "" or cmd == "o":
        call_defense(g)
        return "quiet"

    if cmd in ("?", "h", "help"):
        print(HELP_TEXT)
        return "quiet"

    if cmd == "box":
        print_box(g)
        return "quiet"

    if cmd in ("u", "undo"):
        if g.history:
            g.restore(g.history.pop())
            print(">> Undid last change.")
        else:
            print(">> Nothing to undo.")
        return "info"

    # yX = no player | yXh = rush | yXw2 = pass to WR2 | yXqh = QB to HB
    m = re.match(r"^y(-?\d+)(?:-?(q|h2|h|f)|q?(w[1-4]|t[12])|q(h2|h|f))?$", cmd)
    if m:
        run_live_play(g, "live", int(m.group(1)),
                      rusher=RUSH_CODES.get(m.group(2)),
                      receiver=RECV_CODES.get(m.group(3) or m.group(4)))
        return "mut"

    # i = incomplete | iw1 = intended for WR1 | iqh = intended for HB
    m = re.match(r"^i(?:q?(w[1-4]|t[12])|q?(h2|h|f))?$", cmd)
    if m:
        run_live_play(g, "incomplete",
                      receiver=RECV_CODES.get(m.group(1) or m.group(2)))
        return "mut"

    # phi / pai = interception; phfh / pafw = fumble by that position
    m = re.match(r"^p([ha])i$", cmd)
    if m:
        return "mut" if turnover(g, m.group(1), "int") else None

    m = re.match(r"^p([ha])f(q|h2|h|f|w[1-4]?|t[12]?)$", cmd)
    if m:
        if g.poss == m.group(1):
            print(">> {} already has the ball.".format(g.offense()))
            return None
        code = m.group(2)
        role = FUM_CODES.get(code)
        if role is None:                 # just 'w' or 't'
            role = ask_which(g, code)
        return "mut" if turnover(g, m.group(1), "fum", role) else None

    if cmd == "sp":
        if not in_two_minute(g):
            print(">> Spike is only available on the 2-minute clock.")
            return None
        spike(g)
        return "mut"

    if cmd == "to":
        return "mut" if do_timeout(g) else None

    if cmd == "dt":
        return "mut" if do_timeout(g, defense=True) else None

    m = re.match(r"^x(-?\d+)(r?)$", cmd)
    if m:
        apply_yards(g, int(m.group(1)), "penalty",
                    repeat_down=bool(m.group(2)))
        return "mut"

    if cmd == "ko.tb":
        kickoff(g, None, 0)
        return "mut"

    m = re.match(r"^ko(\d{1,2})(?:\.(\d{1,2}))?$", cmd)
    if m:
        kickoff(g, int(m.group(1)), int(m.group(2) or 0))
        return "mut"

    if cmd == "p.tb":
        punt(g, None, 0)
        return "mut"

    m = re.match(r"^p(\d{1,2})(?:\.(\d{1,2}))?$", cmd)
    if m:
        punt(g, int(m.group(1)), int(m.group(2) or 0))
        return "mut"

    m = re.match(r"^t(\d{1,2}):(\d{2})$", cmd)
    if m:
        mins, secs = int(m.group(1)), int(m.group(2))
        total = mins * 60 + secs
        if secs > 59 or total > QUARTER_LENGTH:
            print(">> Clock must be between 00:00 and 15:00.")
            return None
        g.clock = total
        g.last_ticks = 0
        return "mut"

    m = re.match(r"^q([1-4])$", cmd)
    if m:
        g.quarter = int(m.group(1))
        g.clock = QUARTER_LENGTH
        g.last_ticks = 0
        if g.quarter in (1, 3):          # new half = fresh timeouts
            g.timeouts_home = TIMEOUTS_PER_HALF
            g.timeouts_away = TIMEOUTS_PER_HALF
        return "mut"

    m = re.match(r"^tm([ha])(\d)$", cmd)
    if m:
        n = int(m.group(2))
        if n > TIMEOUTS_PER_HALF:
            print(">> Max timeouts per half is {}.".format(TIMEOUTS_PER_HALF))
            return None
        if m.group(1) == "h":
            g.timeouts_home = n
        else:
            g.timeouts_away = n
        return "mut"

    m = re.match(r"^b([ha])(\d{1,2})$", cmd)
    if m:
        yard = int(m.group(2))
        if not 1 <= yard <= 50:
            print(">> Yard line must be 1-50 (e.g. bh35, ba20).")
            return None
        g.pos = yard if m.group(1) == "h" else 100 - yard
        return "mut"

    m = re.match(r"^d([1-4])\.(\d+)$", cmd)
    if m:
        g.down = int(m.group(1))
        g.to_go = int(m.group(2))
        return "mut"

    m = re.match(r"^s([ha])(\d+)$", cmd)
    if m:
        if m.group(1) == "h":
            g.home_score = int(m.group(2))
        else:
            g.away_score = int(m.group(2))
        return "mut"

    m = re.match(r"^p([ha])$", cmd)
    if m:
        g.poss = m.group(1)
        return "mut"

    print(">> Didn't catch that. Type ? for the command guide.")
    return None


def process(g, raw):
    snap = g.snapshot()
    result = handle(g, raw)
    if result == "mut":
        g.history.append(snap)
    return result


# ---------------------------------------------------------------------------
# Setup + main loop
# ---------------------------------------------------------------------------
def setup_step(g, prompt, default, build):
    while True:
        s = input("{} [{}]: ".format(prompt, default)).strip() or default
        if process(g, build(s)) is not None:
            return


def setup_roster(g):
    ans = input("Enter player names for the box score? (y/n) [n]: ")
    if ans.strip().lower() not in ("y", "yes"):
        print("No problem. Stats still work, using positions (QB, HB, WR1...).\n")
        return
    print("Press Enter to skip any position.")
    for team, tname in (("h", g.home), ("a", g.away)):
        print("\n-- {} roster --".format(tname))
        for role in ROLES:
            g.roster[team][role] = input("  {} {}: ".format(tname, role)).strip()
    print("")


def setup_game():
    print("")
    print("== STRAT-O-MATIC FOOTBALL TRACKER ==")
    print("Press Enter to accept the [default] on any setup question.\n")
    home = input("Home team name [HOME]: ").strip().upper() or "HOME"
    away = input("Away team name [AWAY]: ").strip().upper() or "AWAY"
    g = Game(home, away)

    setup_roster(g)

    setup_step(g, "Quarter (1-4)", "1", lambda s: "q" + s)
    setup_step(g, "Clock (MM:SS)", "15:00", lambda s: "t" + s)
    setup_step(g, "{} score".format(home), "0", lambda s: "sh" + s)
    setup_step(g, "{} score".format(away), "0", lambda s: "sa" + s)
    setup_step(g, "{} timeouts left this half".format(home),
               str(TIMEOUTS_PER_HALF), lambda s: "tmh" + s)
    setup_step(g, "{} timeouts left this half".format(away),
               str(TIMEOUTS_PER_HALF), lambda s: "tma" + s)
    setup_step(g, "Who has the ball? (h/a)", "h", lambda s: "p" + s)
    default_ball = "h25" if g.poss == "h" else "a25"
    setup_step(g, "Ball spot (h35 = {} 35, a20 = {} 20)".format(home, away),
               default_ball, lambda s: "b" + s)
    setup_step(g, "Down.Distance (e.g. 1.10)", "1.10", lambda s: "d" + s)

    g.history = []   # setup shouldn't be undoable
    return g


def main():
    g = setup_game()
    show_status(g)
    print("Enter = defense call.  box = box score.  ? = command guide.")
    while True:
        try:
            raw = input("\n> ")
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break
        if raw.strip().lower() in ("quit", "exit"):
            print("Final: {} {} - {} {}. Bye!".format(
                g.home, g.home_score, g.away, g.away_score))
            break
        result = process(g, raw)
        if result in ("mut", "info"):
            show_status(g)


if __name__ == "__main__":
    main()
