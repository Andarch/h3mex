from src.defs import artifacts, conditions, objects

from . import io


def parse_conditions() -> dict:
    info = {
        "victory_condition": conditions.VictoryType.NONE,
        "allow_normal_win": False,
        "allow_ai_special_win": False,
        "objective_value_1": 0,
        "objective_value_2": 0,
        "objective_coords": [0, 0, 0],
        "loss_condition": conditions.LossType.NONE,
        "loss_coords": [0, 0, 0],
        "loss_timer": 0,
    }

    vc = conditions.VictoryType(io.read_int(1))
    info["victory_condition"] = vc

    if vc != conditions.VictoryType.NONE:
        info["allow_normal_win"] = bool(io.read_int(1))
        info["allow_ai_special_win"] = bool(io.read_int(1))

        match vc:
            case conditions.VictoryType.ACQUIRE_ARTIFACT:
                info["objective_value_1"] = artifacts.ID(io.read_int(2))
            case conditions.VictoryType.ACCUMULATE_CREATURES:
                info["objective_value_1"] = io.read_int(2)
                info["objective_value_2"] = io.read_int(4)
            case conditions.VictoryType.ACCUMULATE_RESOURCES:
                info["objective_value_1"] = objects.Resource(io.read_int(1))
                info["objective_value_2"] = io.read_int(4)
            case conditions.VictoryType.UPGRADE_TOWN:
                info["objective_coords"][0] = io.read_int(1)
                info["objective_coords"][1] = io.read_int(1)
                info["objective_coords"][2] = io.read_int(1)
                info["objective_value_1"] = io.read_int(1)
                info["objective_value_2"] = io.read_int(1)
            case (
                conditions.VictoryType.BUILD_THE_GRAIL
                | conditions.VictoryType.DEFEAT_HERO
                | conditions.VictoryType.CAPTURE_TOWN
                | conditions.VictoryType.DEFEAT_MONSTER
            ):
                info["objective_coords"][0] = io.read_int(1)
                info["objective_coords"][1] = io.read_int(1)
                info["objective_coords"][2] = io.read_int(1)
            case conditions.VictoryType.TRANSPORT_ARTIFACT:
                info["objective_value_1"] = artifacts.ID(io.read_int(1))
                info["objective_coords"][0] = io.read_int(1)
                info["objective_coords"][1] = io.read_int(1)
                info["objective_coords"][2] = io.read_int(1)
            case conditions.VictoryType.SURVIVE:
                info["objective_value_1"] = io.read_int(4)

    lc = conditions.LossType(io.read_int(1))
    info["loss_condition"] = lc

    if lc == conditions.LossType.TIME_EXPIRES:
        info["loss_timer"] = io.read_int(2)
    elif lc != conditions.LossType.NONE:
        info["loss_coords"][0] = io.read_int(1)
        info["loss_coords"][1] = io.read_int(1)
        info["loss_coords"][2] = io.read_int(1)

    return info


def write_conditions(info: dict) -> None:
    vc = info["victory_condition"]
    io.write_int(vc, 1)

    if vc != conditions.VictoryType.NONE:
        io.write_int(info["allow_normal_win"], 1)
        io.write_int(info["allow_ai_special_win"], 1)

        match vc:
            case conditions.VictoryType.ACQUIRE_ARTIFACT:
                io.write_int(info["objective_value_1"], 2)
            case conditions.VictoryType.ACCUMULATE_CREATURES:
                io.write_int(info["objective_value_1"], 2)
                io.write_int(info["objective_value_2"], 4)
            case conditions.VictoryType.ACCUMULATE_RESOURCES:
                io.write_int(info["objective_value_1"], 1)
                io.write_int(info["objective_value_2"], 4)
            case conditions.VictoryType.UPGRADE_TOWN:
                io.write_int(info["objective_coords"][0], 1)
                io.write_int(info["objective_coords"][1], 1)
                io.write_int(info["objective_coords"][2], 1)
                io.write_int(info["objective_value_1"], 1)
                io.write_int(info["objective_value_2"], 1)
            case (
                conditions.VictoryType.BUILD_THE_GRAIL
                | conditions.VictoryType.DEFEAT_HERO
                | conditions.VictoryType.CAPTURE_TOWN
                | conditions.VictoryType.DEFEAT_MONSTER
            ):
                io.write_int(info["objective_coords"][0], 1)
                io.write_int(info["objective_coords"][1], 1)
                io.write_int(info["objective_coords"][2], 1)
            case conditions.VictoryType.TRANSPORT_ARTIFACT:
                io.write_int(info["objective_value_1"], 1)
                io.write_int(info["objective_coords"][0], 1)
                io.write_int(info["objective_coords"][1], 1)
                io.write_int(info["objective_coords"][2], 1)
            case conditions.VictoryType.SURVIVE:
                io.write_int(info["objective_value_1"], 4)

    lc = info["loss_condition"]
    io.write_int(lc, 1)

    if lc == conditions.LossType.TIME_EXPIRES:
        io.write_int(info["loss_timer"], 2)
    elif lc != conditions.LossType.NONE:
        io.write_int(info["loss_coords"][0], 1)
        io.write_int(info["loss_coords"][1], 1)
        io.write_int(info["loss_coords"][2], 1)
