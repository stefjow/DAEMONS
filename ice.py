"""Ring content (DESIGN.md §3.1): ICE identities and loot balance.

This is the file that grows: new ICE, corp signature variants, and
per-ring loot tuning all live here, away from the rules engine.
"""

VISIBLE_FILES = 2           # ring 1; ring 0 shows one more

# ring 0 ICE identities: name -> the rule, as the boot banner states it
ICE_POOL = {
    "crond":     "baseline hunters, just more of them",
    "watchdogd": "a hunter-killer wakes at boot",
    "snortd":    "sentry grid threaded with static",
    "auditd":    "every trace gain doubled",
    "honeyd":    "? everywhere — paydata and snares",
}


def ring0_spec(ice):
    """What an ICE identity does to ring 0's generation and rules."""
    spec = {"hunters": 4, "trace_mult": 1,
            "kinds": ["file", "file", "file", "cred", "cred",
                      "trap", "trap"]}
    if ice == "crond":
        spec["hunters"] = 6
    elif ice == "auditd":
        spec["trace_mult"] = 2
    elif ice == "honeyd":
        spec["kinds"] += ["file", "file", "trap", "trap"]
    return spec


def ring0_files(ice):
    """Paydata the boot banner promises: visible + hidden + vault."""
    return (VISIBLE_FILES + 1) + ring0_spec(ice)["kinds"].count("file") + 1
