"""Sample component: entry point of the bundled example app."""

import notify
import store


def handle() -> str:
    return store.save(notify.message())
