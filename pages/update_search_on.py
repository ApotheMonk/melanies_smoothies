# Admin page: sync FRUIT_OPTIONS.SEARCH_ON with SmoothieFroot API names.
# Appears in the app sidebar (Streamlit multipage). Safe to delete once run.

import re

import requests
import streamlit as st

st.title("Sync SEARCH_ON with SmoothieFroot API")

API_URL = "https://www.smoothiefroot.com/api/fruit/all"
TABLE = "smoothies.public.fruit_options"


def norm(s):
    return re.sub(r"[^a-z]", "", s.lower())


def variants(name):
    """Normalized spellings to try: as-is, then singular forms."""
    n = norm(name)
    out = [n]
    if n.endswith("ies"):
        out.append(n[:-3] + "y")
    if n.endswith("es"):
        out.append(n[:-2])
    if n.endswith("s"):
        out.append(n[:-1])
    return out


# --- 1. Fetch the API fruit list ---
api_fruits = requests.get(API_URL, timeout=10).json()
api_by_norm = {norm(f["name"]): f["name"] for f in api_fruits}
st.write(f"API returned **{len(api_fruits)}** fruits.")

# --- 2. Read the current table ---
cnx = st.connection("snowflake")
session = cnx.session()
rows = session.sql(
    f"select fruit_name, search_on from {TABLE} order by fruit_name"
).collect()

# --- 3. Match each row to an API name ---
proposals = []
for row in rows:
    fruit_name = row["FRUIT_NAME"]
    current = row["SEARCH_ON"]
    matched = None
    for v in variants(fruit_name):
        if v in api_by_norm:
            matched = api_by_norm[v]
            break
    if matched is None:  # last resort: unique substring match
        candidates = [
            full for key, full in api_by_norm.items()
            if len(key) >= 4 and (key in norm(fruit_name) or norm(fruit_name) in key)
        ]
        if len(candidates) == 1:
            matched = candidates[0]

    if matched is None:
        status = "❌ no API match — set manually"
    elif current == matched:
        status = "✅ already correct"
    else:
        status = "🔄 will update"
    proposals.append(
        {"FRUIT_NAME": fruit_name, "SEARCH_ON (current)": current,
         "API name (proposed)": matched, "status": status}
    )

st.dataframe(proposals, use_container_width=True)

to_update = [p for p in proposals if p["status"] == "🔄 will update"]
unmatched = [p for p in proposals if p["API name (proposed)"] is None]

if unmatched:
    st.warning(
        f"{len(unmatched)} fruit(s) have no API match and will be left untouched: "
        + ", ".join(p["FRUIT_NAME"] for p in unmatched)
    )

# --- 4. Apply, behind an explicit button ---
if not to_update:
    st.success("Nothing to update — SEARCH_ON already matches the API.")
elif st.button(f"Apply {len(to_update)} update(s)"):
    for p in to_update:
        session.sql(
            f"update {TABLE} set search_on = ? where fruit_name = ?",
            params=[p["API name (proposed)"], p["FRUIT_NAME"]],
        ).collect()
    st.success(f"Updated {len(to_update)} row(s). Re-run the page to verify.")
