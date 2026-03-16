from __future__ import annotations

import os
from gzip import open as gzopen
from pathlib import Path
from typing import Any, Callable

from src.file import (
    io,
    m1_general,
    m2_players,
    m3_conditions,
    m4_heroes,
    m5_additional_flags,
    m6_rumors_and_events,
    m7_terrain,
    m8_objects,
    m9_null,
    state,
)


def ensure_h3m_extension(filename: str) -> str:
    return filename if filename.lower().endswith(".h3m") else f"{filename}.h3m"


@io.with_position_tracking
def load_map(filename: str, progress_callback: Callable[[str], None] | None = None) -> dict[str, Any]:
    filename = ensure_h3m_extension(filename)

    def report_progress(message: str) -> None:
        if progress_callback is not None:
            progress_callback(message)

    with gzopen(filename, "rb") as io.in_file:
        io.reset_position()

        data: dict[str, Any] = {}
        data["filename"] = filename

        report_progress("Parsing 1/13: General")
        data["general"] = m1_general.read_general()

        report_progress("Parsing 2/13: Player Specs")
        data["player_specs"] = m2_players.read_players()

        report_progress("Parsing 3/13: Victory/Loss Conditions")
        data["conditions"] = m3_conditions.parse_conditions()

        report_progress("Parsing 4/13: Teams")
        data["teams"] = m2_players.parse_teams()

        report_progress("Parsing 5/13: Hero Availability")
        data["starting_heroes"] = m4_heroes.parse_starting_heroes()

        report_progress("Parsing 6/13: Additional Specs")
        data["ban_flags"] = m5_additional_flags.parse_flags()

        report_progress("Parsing 7/13: Rumors")
        data["rumors"] = m6_rumors_and_events.parse_rumors()

        report_progress("Parsing 8/13: Hero Templates")
        data["hero_data"] = m4_heroes.parse_hero_data()

        report_progress("Parsing 9/13: Terrain Data")
        data["terrain"] = m7_terrain.parse_terrain(data["general"])

        report_progress("Parsing 10/13: Object Defs")
        data["object_defs"] = m8_objects.parse_object_defs()

        report_progress("Parsing 11/13: Object Data")
        data["object_data"] = m8_objects.parse_object_data(
            data["filename"], data["starting_heroes"]["custom_heroes"], data["object_defs"]
        )
        data["town_events"] = state.town_events.copy()
        state.town_events.clear()

        report_progress("Parsing 12/13: Events")
        data["global_events"] = m6_rumors_and_events.parse_events()

        report_progress("Parsing 13/13: Null Bytes")
        data["null_bytes"] = m9_null.read_null()

        report_progress("Done")

        return data


@io.with_position_tracking
def save_map(data: dict[str, Any], filename: str, source_filename: str | None = None) -> str:
    target_filename = ensure_h3m_extension(filename)

    _rotate_backup(target_filename, source_filename)

    with gzopen(target_filename, "wb") as io.out_file:
        m1_general.write(data["general"])
        m2_players.write(data["player_specs"])
        m3_conditions.write_conditions(data["conditions"])
        m2_players.write_teams(data["teams"])
        m4_heroes.write_starting_heroes(data["starting_heroes"])
        m5_additional_flags.write_flags(data["ban_flags"])
        m6_rumors_and_events.write_rumors(data["rumors"])
        m4_heroes.write_hero_data(data["hero_data"])
        m7_terrain.write_terrain(data["terrain"])
        m8_objects.write_object_defs(data["object_defs"])
        m8_objects.write_object_data(data["object_data"])
        m6_rumors_and_events.write_events(data["global_events"])
        m9_null.write_null(data["null_bytes"])

    return target_filename


def _rotate_backup(target_filename: str, source_filename: str | None) -> None:
    should_backup = source_filename and os.path.abspath(source_filename) == os.path.abspath(target_filename)
    if not should_backup:
        return

    target = Path(target_filename)
    if not target.exists():
        return

    backup_index = 1
    for i in range(1, 10):
        backup_path = Path(f"{target_filename}.bak{i}")
        if not backup_path.exists():
            backup_index = i
            break

    backup_path = Path(f"{target_filename}.bak{backup_index}")
    if backup_path.exists():
        backup_path.unlink()
    target.rename(backup_path)
