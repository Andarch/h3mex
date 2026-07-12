import math

from . import io


def parse_settings_1() -> dict:
    info = {
        "allow_plague": False,
        "combo_artifact_count": 0,
        "combo_artifacts": [],
        "combat_round_limit": 0,
        "forbid_hiring": [],
    }
    info["allow_plague"] = bool(io.read_int(4))
    info["combo_artifact_count"] = io.read_int(4)
    combo_artifact_bytes = math.ceil(info["combo_artifact_count"] / 8)
    info["combo_artifacts"] = io.read_bits(combo_artifact_bytes)
    info["combat_round_limit"] = io.read_int(4)
    for _ in range(8):
        info["forbid_hiring"].append(bool(io.read_int(1)))
    return info


def parse_settings_2() -> dict:
    info = {
        "artifact_count": 0,
        "artifacts": [],
        "spells": [],
        "skills": [],
    }
    info["artifact_count"] = io.read_int(4)
    artifact_bytes = math.ceil(info["artifact_count"] / 8)
    info["artifacts"] = io.read_bits(artifact_bytes)
    info["spells"] = io.read_bits(9)
    info["skills"] = io.read_bits(4)
    return info


def write_settings_1(info: dict) -> None:
    io.write_int(info["allow_plague"], 4)
    io.write_int(info["combo_artifact_count"], 4)
    io.write_bits(info["combo_artifacts"])
    io.write_int(info["combat_round_limit"], 4)
    for player in range(8):
        io.write_int(info["forbid_hiring"][player], 1)


def write_settings_2(info: dict) -> None:
    io.write_int(info["artifact_count"], 4)
    io.write_bits(info["artifacts"])
    io.write_bits(info["spells"])
    io.write_bits(info["skills"])
