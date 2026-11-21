"""Transform: small pure functions, DataFrame in, DataFrame out (built out in Step 5)."""

import re

_STATE_WORD = re.compile(r"\bstate\b")
_SEPARATORS = re.compile(r"[-,.]")


def normalise_state_name(name: str) -> str:
    """Normalise a raw state label for lookup in ``core.state_alias``.

    Lower-case, hyphens/commas/full stops to spaces, drop the word "state", collapse whitespace:
    ``"  Akwa-Ibom State "`` -> ``"akwa ibom"``.
    """
    s = _SEPARATORS.sub(" ", name.lower())
    s = _STATE_WORD.sub(" ", s)
    return " ".join(s.split())
