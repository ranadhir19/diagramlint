"""Sample component: persistence for the bundled example app."""

import util


def save(text: str) -> str:
    return util.normalise(text)
