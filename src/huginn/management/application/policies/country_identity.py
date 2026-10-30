"""Canonical country identity shared by ICP validation and recommendation filtering."""

import pycountry


def normalize_country(value):
    if not isinstance(value, str) or not value.strip():
        return None
    value = {"uk": "GB", "united states of america": "US"}.get(
        value.strip().casefold(), value.strip()
    )
    try:
        return pycountry.countries.lookup(value).alpha_2
    except LookupError:
        return None
