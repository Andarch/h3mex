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
    m5_settings,
    m6_extended_events,
    m7_rumors_and_events,
    m8_terrain,
    m9_objects,
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

        report_progress("Parsing 1/15: General")
        data["general"] = m1_general.read_general()

        report_progress("Parsing 2/15: Player Specs")
        data["player_specs"] = m2_players.read_players()

        report_progress("Parsing 3/15: Victory/Loss Conditions")
        data["conditions"] = m3_conditions.parse_conditions()

        report_progress("Parsing 4/15: Teams")
        data["teams"] = m2_players.parse_teams()

        report_progress("Parsing 5/15: Hero Availability")
        data["starting_heroes"] = m4_heroes.parse_starting_heroes()

        report_progress("Parsing 6/15: Settings 1")
        data["settings"] = m5_settings.parse_settings_1()

        report_progress("Parsing 7/15: Extended Events")
        data["extended_events"] = m6_extended_events.parse_extended_events()

        report_progress("Parsing 8/15: Settings 2")
        data["settings"].update(m5_settings.parse_settings_2())

        report_progress("Parsing 9/15: Rumors")
        data["rumors"] = m7_rumors_and_events.parse_rumors()

        report_progress("Parsing 10/15: Hero Templates")
        data["hero_data"] = m4_heroes.parse_hero_data()

        report_progress("Parsing 11/15: Terrain Data")
        data["terrain"] = m8_terrain.parse_terrain(data["general"])

        report_progress("Parsing 12/15: Object Defs")
        data["object_defs"] = m9_objects.parse_object_defs()

        report_progress("Parsing 13/15: Object Data")
        data["object_data"] = m9_objects.parse_object_data(
            data["filename"], data["starting_heroes"]["custom_heroes"], data["object_defs"]
        )
        data["town_events"] = m7_rumors_and_events.town_events.copy()
        m7_rumors_and_events.town_events.clear()

        report_progress("Parsing 14/15: Events")
        data["global_events"] = m7_rumors_and_events.parse_events()

        report_progress("Parsing 15/15: Null Bytes")
        data["null_bytes"] = io.read_raw(124)

        report_progress("Done")

        return data


@io.with_position_tracking
def save_map(data: dict[str, Any], filename: str, source_filename: str | None = None) -> str:
    target_filename = ensure_h3m_extension(filename)

    _rotate_backup(target_filename, source_filename)

    settings_data = data.get("settings", data.get("ban_flags"))
    if settings_data is None:
        raise KeyError("Map data is missing 'settings' (or legacy 'ban_flags').")

    with gzopen(target_filename, "wb") as io.out_file:
        m1_general.write(data["general"])
        m2_players.write(data["player_specs"])
        m3_conditions.write_conditions(data["conditions"])
        m2_players.write_teams(data["teams"])
        m4_heroes.write_starting_heroes(data["starting_heroes"])
        m5_settings.write_settings_1(settings_data)
        m6_extended_events.write_extended_events(data.get("extended_events", {"has_extended_events": False}))
        m5_settings.write_settings_2(settings_data)
        m7_rumors_and_events.write_rumors(data["rumors"])
        m4_heroes.write_hero_data(data["hero_data"])
        m8_terrain.write_terrain(data["terrain"])
        m9_objects.write_object_defs(data["object_defs"])
        m9_objects.write_object_data(data["object_data"])
        m7_rumors_and_events.write_events(data["global_events"])
        io.write_raw(data["null_bytes"])

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
