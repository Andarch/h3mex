from enum import IntEnum

from src.defs import (
    artifacts,
    creatures,
    heroes,
    objects,
    players,
    skills,
    spells,
)
from src.defs.events import ExtendedEvents

from . import io


def _read_uint(length: int) -> int:
    return io.read_int(length)


def _read_int(length: int) -> int:
    return int.from_bytes(io.read_raw(length), "little", signed=True)


def _write_uint(value, length: int) -> None:
    if isinstance(value, IntEnum):
        value = value.value
    io.write_int(int(value), length)


def _write_int(value, length: int) -> None:
    if isinstance(value, IntEnum):
        value = value.value
    io.write_raw(int(value).to_bytes(length, "little", signed=True))


def _read_enum(enum_cls, length: int = 4, signed: bool = False):
    value = _read_int(length) if signed else _read_uint(length)
    try:
        return enum_cls(value)
    except ValueError:
        return value


def _write_enum(value, length: int = 4, signed: bool = False) -> None:
    if isinstance(value, IntEnum):
        value = value.value
    if signed:
        _write_int(value, length)
    else:
        _write_uint(value, length)


def _read_bool() -> bool:
    return bool(_read_uint(1))


def _write_bool(value: bool) -> None:
    _write_uint(1 if value else 0, 1)


def _as_int(value) -> int:
    return value.value if isinstance(value, IntEnum) else int(value)


def _read_player_value(length: int = 4):
    value = _read_uint(length)
    try:
        return players.ID(value)
    except ValueError:
        return value


def _write_player_value(value, length: int = 4) -> None:
    _write_enum(value, length)


def _read_player_index(length: int = 4):
    value = _read_uint(length)
    try:
        return ExtendedEvents.ConditionPlayer(value)
    except ValueError:
        return value


def _write_player_index(value, length: int = 4) -> None:
    _write_enum(value, length)


def _read_expression_player(length: int = 1):
    value = _read_uint(length)
    try:
        return ExtendedEvents.ExpressionPlayer(value)
    except ValueError:
        return value


def _write_expression_player(value, length: int = 1) -> None:
    _write_enum(value, length)


def _is_extended_event_action_id(value: int) -> bool:
    try:
        ExtendedEvents.Action(value)
        return True
    except ValueError:
        return False


def _read_value_mode_payload(container: dict, mode_enum, integer_key: str, variable_key: str = "variable_id") -> None:
    container["value_mode"] = _read_enum(mode_enum, 1)
    if container["value_mode"] == mode_enum.Integer:
        container[integer_key] = _read_int(4)
    else:
        container[variable_key] = _read_uint(4)


def _write_value_mode_payload(container: dict, mode_enum, integer_key: str, variable_key: str = "variable_id") -> None:
    _write_enum(container["value_mode"], 1)
    if container["value_mode"] == mode_enum.Integer:
        _write_int(container[integer_key], 4)
    else:
        _write_uint(container[variable_key], 4)


def read_u32_string() -> str:
    return io.read_str(_read_uint(4))


def write_u32_string(value: str) -> None:
    _write_uint(len(value), 4)
    io.write_str(value)


def parse_extended_events() -> dict:
    info = {
        "has_extended_events": False,
        "extended_events": {} if not ExtendedEvents.READ_RAW else b"",
    }

    info["has_extended_events"] = _read_bool()
    if not info["has_extended_events"]:
        return info

    if ExtendedEvents.READ_RAW:
        info["extended_events"] = _parse_extended_events_alt()
        return info

    event_types = [
        ExtendedEvents.Type.Hero,
        ExtendedEvents.Type.Player,
        ExtendedEvents.Type.Town,
        ExtendedEvents.Type.Quest,
    ]

    info["extended_events"] = {event_type: {"events": [], "id_counter": 0, "ids": []} for event_type in event_types}
    info["extended_events"]["variables"] = []
    info["extended_events"]["variable_id_counter"] = 0
    info["extended_events"]["variable_ids"] = []

    for event_type in event_types:
        for _ in range(_read_uint(4)):
            info["extended_events"][event_type]["events"].append(parse_extended_event_info())

    for event_type in event_types:
        info["extended_events"][event_type]["id_counter"] = _read_uint(4)
    info["extended_events"]["variable_id_counter"] = _read_uint(4)

    for _ in range(_read_uint(4)):
        variable = {
            "id": _read_uint(4),
            "name": read_u32_string(),
            "save_in_campaign": _read_bool(),
            "value_mode": _read_enum(ExtendedEvents.VariableMode, 1),
        }
        if variable["value_mode"] == ExtendedEvents.VariableMode.InitialValue:
            variable["value"] = _read_int(4)
        info["extended_events"]["variables"].append(variable)

    for event_type in event_types:
        for _ in range(_read_uint(4)):
            info["extended_events"][event_type]["ids"].append(_read_uint(4))
    for _ in range(_read_uint(4)):
        info["extended_events"]["variable_ids"].append(_read_uint(4))

    return info


def parse_extended_event_info(max_depth: int = 64) -> dict:
    event_id = _read_uint(4)
    unknown_bytes = io.read_raw(5)
    action_count = _read_uint(4)

    return {
        "id": event_id,
        "unknown_bytes": unknown_bytes,
        "action_count": action_count,
        "actions": [parse_action(max_depth=max_depth) for _ in range(action_count)],
        "name": read_u32_string(),
    }


def parse_action(max_depth: int = 64) -> dict:
    if max_depth <= 0:
        raise ValueError(f"Extended event nesting depth exceeded at byte position {io.get_position()}")

    action_id = _read_enum(ExtendedEvents.Action, 4)
    if not isinstance(action_id, ExtendedEvents.Action):
        raise ValueError(f"Unsupported extended event action id {action_id} at byte position {io.get_position()}")

    action = {"action_id": action_id}
    _parse_action_payload(action, action_id, max_depth=max_depth)
    return action


def _parse_action_payload(action: dict, action_id: ExtendedEvents.Action, max_depth: int = 64) -> None:

    if action_id == ExtendedEvents.Action.SetVariableBasedOnCondition:
        action["variable_id"] = _read_uint(4)
        action["condition"] = parse_condition(max_depth=max_depth - 1)
        action["true_value"] = parse_condition_value(max_depth=max_depth - 1)
        action["false_value"] = parse_condition_value(max_depth=max_depth - 1)
    elif action_id == ExtendedEvents.Action.ModifyVariable:
        action["variable_id"] = _read_uint(4)
        action["operation"] = _read_enum(ExtendedEvents.VariableOperation, 1)
        action["expression"] = parse_expression(max_depth=max_depth - 1)
    elif action_id == ExtendedEvents.Action.ResourcesReward:
        action.update(parse_resources_reward(max_depth=max_depth - 1))
    elif action_id == ExtendedEvents.Action.RemoveCurrentObject_FinishQuest:
        pass
    elif action_id == ExtendedEvents.Action.MessageWithReward:
        action["message"] = read_u32_string()
        action["reward_list"] = parse_reward_list(max_depth=max_depth - 1)
    elif action_id == ExtendedEvents.Action.QuestAction:
        action["condition"] = parse_condition(max_depth=max_depth - 1)
        action["proposal_message"] = read_u32_string()
        action["progress_message"] = read_u32_string()
        action["completion_message"] = read_u32_string()
        action["hint_message"] = read_u32_string()
        action["completion_actions"] = parse_question_action_list(max_depth=max_depth - 1)
        action["set_quest_log_entry"] = _read_bool()
    elif action_id == ExtendedEvents.Action.CreaturesReward:
        action["operation"] = _read_enum(ExtendedEvents.RewardOperation, 1)
        action["creature_id"] = _read_enum(creatures.ID, 4)
        action["quantity"] = parse_operand(max_depth=max_depth - 1)
        action["show_with_message"] = _read_bool()
    elif action_id == ExtendedEvents.Action.ArtifactReward:
        action["operation"] = _read_enum(ExtendedEvents.RewardOperation, 1)
        action["artifact_id"] = _read_enum(artifacts.ID, 4)
        if _as_int(action["artifact_id"]) == _as_int(artifacts.ID.Spell_Scroll):
            action["spell_id"] = _read_enum(spells.ID, 4)
        else:
            action["artifact_spell_id_none"] = _read_uint(4)
        action["show_with_message"] = _read_bool()
    elif action_id == ExtendedEvents.Action.BuildTownStructure:
        action["building"] = _read_enum(objects.TownBuildings.Normal, 4)
        action["town_type"] = _read_enum(ExtendedEvents.BuildStructureTownType, 4)
        action["show_with_message"] = _read_bool()
    elif action_id == ExtendedEvents.Action.SetQuestHintAndLogEntry:
        action["quest_hint"] = read_u32_string()
        image_count = _read_uint(4)
        action["quest_log_images"] = [parse_quest_log_image() for _ in range(image_count)]
        action["show_quest_in_log"] = _read_bool()
    elif action_id == ExtendedEvents.Action.Question:
        action["image_mode"] = _read_enum(ExtendedEvents.QuestionImageMode, 1)
        action["question"] = read_u32_string()
        action["yes_actions"] = parse_question_action_list(max_depth=max_depth - 1)
        action["no_actions"] = parse_question_action_list(max_depth=max_depth - 1)
        if action["image_mode"] == ExtendedEvents.QuestionImageMode.SelectionCanExit:
            action["cancel_actions"] = parse_question_action_list(max_depth=max_depth - 1)

        if action["image_mode"] in (
            ExtendedEvents.QuestionImageMode.NoImages,
            ExtendedEvents.QuestionImageMode.SpecifyImages,
        ):
            image_count = _read_uint(4)
            action["specified_images"] = [parse_message_image() for _ in range(image_count)]
        else:
            action["first_choice_image"] = parse_message_image()
            action["second_choice_image"] = parse_message_image()
            action["show_or_text_between_images"] = _read_bool()
            stale_count = _read_uint(4)
            action["stale_specified_images"] = [parse_message_image() for _ in range(stale_count)]
    elif action_id == ExtendedEvents.Action.AddCreaturesToHire:
        action["creature_level"] = _read_enum(ExtendedEvents.TownCreatureLevel, 4)
        action["quantity"] = parse_operand(max_depth=max_depth - 1)
        action["unused_creature_id"] = _read_uint(4)
        action["show_with_message"] = _read_bool()
    elif action_id == ExtendedEvents.Action.SpellReward:
        action["spell_id"] = _read_enum(spells.ID, 4)
        action["show_with_message"] = _read_bool()
    elif action_id == ExtendedEvents.Action.ExperienceReward:
        action["amount"] = parse_operand(max_depth=max_depth - 1)
        action["show_with_message"] = _read_bool()
    elif action_id == ExtendedEvents.Action.SpellPointsReward:
        action["amount"] = parse_operand(max_depth=max_depth - 1)
        action["operation"] = _read_enum(ExtendedEvents.SpellPointsOperation, 4)
        action["show_with_message"] = _read_bool()
    elif action_id == ExtendedEvents.Action.MovementPointsReward:
        action["amount"] = parse_operand(max_depth=max_depth - 1)
        action["operation"] = _read_enum(ExtendedEvents.MovementPointsOperation, 4)
        action["show_with_message"] = _read_bool()
    elif action_id == ExtendedEvents.Action.PrimarySkillsReward:
        action["amount"] = parse_operand(max_depth=max_depth - 1)
        action["primary_skill"] = _read_enum(skills.Primary, 4)
        action["show_with_message"] = _read_bool()
    elif action_id == ExtendedEvents.Action.SecondarySkillsReward:
        action["secondary_skill_level"] = _read_enum(skills.SecondaryLevels, 4)
        action["secondary_skill"] = _read_enum(skills.Secondary, 4)
        action["show_with_message"] = _read_bool()
    elif action_id == ExtendedEvents.Action.LuckReward:
        action["amount"] = _read_int(4)
        action["show_with_message"] = _read_bool()
    elif action_id == ExtendedEvents.Action.MoraleReward:
        action["amount"] = _read_int(4)
        action["show_with_message"] = _read_bool()
    elif action_id == ExtendedEvents.Action.Combat:
        action["slots"] = [parse_combat_stack(max_depth=max_depth - 1) for _ in range(7)]
    elif action_id == ExtendedEvents.Action.ExecuteEvent:
        action["event_type"] = _read_enum(ExtendedEvents.Type, 4)
        action["event_id"] = _read_uint(4)
    elif action_id == ExtendedEvents.Action.WarMachineReward:
        action["operation"] = _read_enum(ExtendedEvents.RewardOperation, 1)
        action["war_machine_artifact_id"] = _read_enum(artifacts.ID, 4)
        action["hidden_extra"] = _read_uint(4)
        action["show_with_message"] = _read_bool()
    elif action_id == ExtendedEvents.Action.SpellbookReward:
        action["operation"] = _read_enum(ExtendedEvents.RewardOperation, 1)
        action["hidden_extra_1"] = _read_uint(4)
        action["hidden_extra_2"] = _read_uint(4)
        action["show_with_message"] = _read_bool()
    elif action_id == ExtendedEvents.Action.DisableEvent:
        pass
    elif action_id == ExtendedEvents.Action.Cycle:
        action["sequence_actions"] = parse_action_list(max_depth=max_depth - 1)
        action["first_value"] = parse_condition_value(max_depth=max_depth - 1)
        action["second_value"] = parse_condition_value(max_depth=max_depth - 1)
        action["variable_id"] = _read_uint(4)
    elif action_id == ExtendedEvents.Action.ShowMessage:
        action["message"] = read_u32_string()
        image_count = _read_uint(4)
        action["images"] = [parse_message_image() for _ in range(image_count)]
    elif action_id == ExtendedEvents.Action.IfThenElse:
        action["condition"] = parse_condition(max_depth=max_depth - 1)
        action["then_actions"] = parse_action_list(max_depth=max_depth - 1)
        action["else_actions"] = parse_action_list(max_depth=max_depth - 1)
    elif action_id == ExtendedEvents.Action.IfThenElseIf:
        action["first_pair"] = {
            "condition": parse_condition(max_depth=max_depth - 1),
            "then_actions": parse_action_list(max_depth=max_depth - 1),
        }
        action["tail"] = parse_if_then_else_if_tail(max_depth=max_depth - 1)
    else:
        raise ValueError(f"Unsupported extended event action id {action_id} at byte position {io.get_position()}")


def parse_if_then_else_if_tail(max_depth: int = 64) -> dict:
    if max_depth <= 0:
        raise ValueError(f"Extended event nesting depth exceeded at byte position {io.get_position()}")

    tail = {"chain_marker": _read_uint(1), "has_next_pair": _read_uint(4)}
    if tail["has_next_pair"] != 0:
        tail["next_pair"] = {
            "condition": parse_condition(max_depth=max_depth - 1),
            "then_actions": parse_action_list(max_depth=max_depth - 1),
        }
        tail["tail"] = parse_if_then_else_if_tail(max_depth=max_depth - 1)
    else:
        tail["else_actions"] = parse_plain_action_list(max_depth=max_depth - 1)
    return tail


def parse_action_list(max_depth: int = 64) -> dict:
    return {
        "action_list_marker": _read_uint(4),
        "action_list_unknown": _read_uint(1),
        "actions": parse_plain_action_list(max_depth=max_depth),
    }


def parse_plain_action_list(max_depth: int = 64) -> list:
    action_count = _read_uint(4)
    return [parse_action(max_depth=max_depth) for _ in range(action_count)]


def parse_question_action_list(max_depth: int = 64) -> dict:
    return parse_action_list(max_depth=max_depth)


def parse_operand(max_depth: int = 64) -> dict:
    mode = _read_enum(ExtendedEvents.ExpressionOperandMode, 1)
    operand = {"mode": mode}
    if mode == ExtendedEvents.ExpressionOperandMode.Integer:
        operand["integer_value"] = _read_int(4)
    elif mode == ExtendedEvents.ExpressionOperandMode.Expression:
        operand["expression"] = parse_expression(max_depth=max_depth - 1)
    else:
        raise ValueError(f"Unsupported extended event operand mode {mode} at byte position {io.get_position()}")
    return operand


def parse_condition_value(max_depth: int = 64) -> dict:
    return parse_operand(max_depth=max_depth)


def parse_expression(max_depth: int = 64) -> dict:
    if max_depth <= 0:
        raise ValueError(f"Extended event nesting depth exceeded at byte position {io.get_position()}")

    expression = {
        "item_count_or_flag": _read_uint(1),
        "expression_type": _read_enum(ExtendedEvents.ExpressionType, 4),
    }
    expression_type = expression["expression_type"]

    if expression_type == ExtendedEvents.ExpressionType.IntegerValue:
        expression["integer_value"] = _read_int(4)
    elif expression_type == ExtendedEvents.ExpressionType.VariableValue:
        expression["variable_id"] = _read_uint(4)
    elif expression_type == ExtendedEvents.ExpressionType.Resource:
        expression["player"] = _read_expression_player(1)
        expression["resource"] = _read_enum(objects.SubID.Resource, 4)
    elif expression_type == ExtendedEvents.ExpressionType.CreatureCount:
        expression["creature_id"] = _read_uint(4)
    elif expression_type == ExtendedEvents.ExpressionType.DifficultyLevel:
        expression["difficulty_level"] = _read_enum(ExtendedEvents.ExpressionDifficultyLevel, 4)
    elif expression_type == ExtendedEvents.ExpressionType.PrimarySkill:
        expression["primary_skill"] = _read_enum(skills.Primary, 4)
    elif expression_type == ExtendedEvents.ExpressionType.ArtifactCount:
        expression["artifact_id"] = _read_enum(artifacts.ID, 4)
        if _as_int(expression["artifact_id"]) == _as_int(artifacts.ID.Spell_Scroll):
            expression["spell_id"] = _read_enum(spells.ID, 4)
        else:
            expression["artifact_spell_id_none"] = _read_uint(4)
    elif expression_type == ExtendedEvents.ExpressionType.InvertSign:
        expression["value_expression"] = parse_expression(max_depth=max_depth - 1)
    elif expression_type in (
        ExtendedEvents.ExpressionType.Add,
        ExtendedEvents.ExpressionType.Subtract,
        ExtendedEvents.ExpressionType.Multiply,
        ExtendedEvents.ExpressionType.Divide,
        ExtendedEvents.ExpressionType.Remainder,
    ):
        expression["left_expression"] = parse_expression(max_depth=max_depth - 1)
        expression["right_expression"] = parse_expression(max_depth=max_depth - 1)
    elif expression_type in (
        ExtendedEvents.ExpressionType.CurrentDifficultyLevel,
        ExtendedEvents.ExpressionType.CurrentDate,
        ExtendedEvents.ExpressionType.CurrentHeroExperience,
        ExtendedEvents.ExpressionType.CurrentHeroLevel,
    ):
        pass
    elif expression_type == ExtendedEvents.ExpressionType.RandomNumber:
        expression["min_operand"] = parse_operand(max_depth=max_depth - 1)
        expression["max_operand"] = parse_operand(max_depth=max_depth - 1)
    else:
        raise ValueError(
            f"Unsupported extended event expression type {expression_type} at byte position {io.get_position()}"
        )

    return expression


def parse_condition(max_depth: int = 64) -> dict:
    if max_depth <= 0:
        raise ValueError(f"Extended event nesting depth exceeded at byte position {io.get_position()}")

    item_count_or_flag = _read_uint(1)
    condition = parse_condition_node(max_depth=max_depth - 1)
    condition["item_count_or_flag"] = item_count_or_flag
    return condition


def parse_condition_node(max_depth: int = 64) -> dict:
    if max_depth <= 0:
        raise ValueError(f"Extended event nesting depth exceeded at byte position {io.get_position()}")

    condition = {"condition_type": _read_enum(ExtendedEvents.ConditionType, 4)}
    condition_type = condition["condition_type"]

    if condition_type == ExtendedEvents.ConditionType.BooleanValue:
        condition["boolean_value"] = _read_bool()
    elif condition_type == ExtendedEvents.ConditionType.HeroHasArtifact:
        condition["artifact_id"] = _read_enum(artifacts.ID, 4)
        if _as_int(condition["artifact_id"]) == _as_int(artifacts.ID.Spell_Scroll):
            condition["spell_id"] = _read_enum(spells.ID, 4)
        else:
            condition["artifact_spell_id_none"] = _read_uint(4)
    elif condition_type == ExtendedEvents.ConditionType.MonsterDefeatedByPlayer:
        condition["player"] = _read_enum(ExtendedEvents.ConditionDefeatingPlayer, 4, signed=True)
        condition["monster_uid"] = _read_uint(4)
    elif condition_type == ExtendedEvents.ConditionType.HeroDefeatedByPlayer:
        condition["player"] = _read_enum(ExtendedEvents.ConditionDefeatingPlayer, 4, signed=True)
        condition["hero_uid"] = _read_uint(4)
    elif condition_type == ExtendedEvents.ConditionType.TownControlledByPlayer:
        condition["player"] = _read_enum(ExtendedEvents.ConditionDefeatingPlayer, 4, signed=True)
        condition["town_uid"] = _read_uint(4)
    elif condition_type in (ExtendedEvents.ConditionType.CurrentHero, ExtendedEvents.ConditionType.PlayerDefeated):
        condition["player"] = _read_player_index(4)
    elif condition_type == ExtendedEvents.ConditionType.PlayerIsHuman:
        condition["player"] = _read_enum(ExtendedEvents.ConditionPlayerOrCurrent, 4, signed=True)
    elif condition_type == ExtendedEvents.ConditionType.PlayerStartingTown:
        condition["player"] = _read_enum(ExtendedEvents.ConditionPlayerOrCurrent, 4, signed=True)
        condition["town_type"] = _read_enum(ExtendedEvents.BuildStructureTownType, 4)
    elif condition_type == ExtendedEvents.ConditionType.HeroAffiliation:
        condition["hero_name"] = _read_enum(heroes.ID, 4)
        condition["location"] = _read_enum(ExtendedEvents.HeroAffiliationLocation, 4, signed=True)
    elif condition_type == ExtendedEvents.ConditionType.HeroClass:
        condition["hero_class"] = _read_enum(heroes.Classes, 4)
    elif condition_type == ExtendedEvents.ConditionType.HeroSecondarySkill:
        condition["secondary_skill"] = _read_enum(skills.Secondary, 4)
        condition["secondary_skill_level"] = _read_enum(skills.SecondaryLevels, 4)
    elif condition_type in (
        ExtendedEvents.ConditionType.LessThan,
        ExtendedEvents.ConditionType.GreaterThan,
        ExtendedEvents.ConditionType.Equal,
        ExtendedEvents.ConditionType.GreaterThanOrEqual,
        ExtendedEvents.ConditionType.LessThanOrEqual,
        ExtendedEvents.ConditionType.NotEqual,
    ):
        condition["left_value"] = parse_condition_value(max_depth=max_depth - 1)
        condition["right_value"] = parse_condition_value(max_depth=max_depth - 1)
    elif condition_type == ExtendedEvents.ConditionType.Not:
        condition["nested_condition"] = parse_condition(max_depth=max_depth - 1)
    elif condition_type in (ExtendedEvents.ConditionType.And, ExtendedEvents.ConditionType.Or):
        condition_count = _read_uint(4)
        condition["condition_count"] = condition_count
        condition["child_conditions"] = [parse_condition_node(max_depth=max_depth - 1) for _ in range(condition_count)]
    else:
        raise ValueError(
            f"Unsupported extended event condition type {condition_type} at byte position {io.get_position()}"
        )

    return condition


def parse_resources_reward(max_depth: int = 64) -> dict:
    reward = {"operation": _read_enum(ExtendedEvents.VariableOperation, 1)}
    for resource_name in ("wood", "mercury", "ore", "sulfur", "crystal", "gems", "gold"):
        reward[resource_name] = parse_operand(max_depth=max_depth - 1)
    reward["show_with_message"] = _read_bool()
    return reward


def parse_reward_list(max_depth: int = 64) -> dict:
    reward_list = {
        "rewards_marker": _read_uint(1),
        "rewards_unknown": _read_uint(4),
        "reward_count": _read_uint(4),
        "rewards": [],
    }
    for _ in range(reward_list["reward_count"]):
        reward_list["rewards"].append(parse_reward_entry(max_depth=max_depth - 1))
    return reward_list


def parse_reward_entry(max_depth: int = 64) -> dict:
    reward_type = _read_uint(4)
    if not _is_extended_event_action_id(reward_type):
        raise ValueError(f"Unsupported extended event reward type {reward_type} at byte position {io.get_position()}")

    action_id = ExtendedEvents.Action(reward_type)
    reward = {"action_id": action_id, "reward_type": action_id}
    _parse_action_payload(reward, action_id, max_depth=max_depth - 1)
    return reward


def parse_message_image() -> dict:
    image = {"image_type": _read_enum(ExtendedEvents.MessageImageType, 4)}
    image_type = image["image_type"]

    if image_type in (
        ExtendedEvents.MessageImageType.ResourcesPlus,
        ExtendedEvents.MessageImageType.ResourcesMinus,
        ExtendedEvents.MessageImageType.ResourcesPerDay,
        ExtendedEvents.MessageImageType.ResourcesSimple,
    ):
        image["resource"] = _read_enum(objects.SubID.Resource, 4)
        _read_value_mode_payload(image, ExtendedEvents.MessageImageValueMode, "amount")
    elif image_type == ExtendedEvents.MessageImageType.Artifact:
        image["artifact_id"] = _read_enum(artifacts.ID, 4)
        _read_value_mode_payload(image, ExtendedEvents.MessageImageValueMode, "hidden_value")
    elif image_type in (ExtendedEvents.MessageImageType.Spell, ExtendedEvents.MessageImageType.SpellScroll):
        image["spell_id"] = _read_enum(spells.ID, 4)
        _read_value_mode_payload(image, ExtendedEvents.MessageImageValueMode, "hidden_value")
    elif image_type == ExtendedEvents.MessageImageType.PlayerFlag:
        image["player"] = _read_player_index(4)
        _read_value_mode_payload(image, ExtendedEvents.MessageImageValueMode, "hidden_value")
    elif image_type in (ExtendedEvents.MessageImageType.Luck, ExtendedEvents.MessageImageType.Morale):
        image["value"] = _read_int(4)
        _read_value_mode_payload(image, ExtendedEvents.MessageImageValueMode, "hidden_value")
    elif image_type in (
        ExtendedEvents.MessageImageType.Experience,
        ExtendedEvents.MessageImageType.GoldSmallPlus,
        ExtendedEvents.MessageImageType.GoldSmallMinus,
        ExtendedEvents.MessageImageType.GoldSmall,
        ExtendedEvents.MessageImageType.GoldSmallPerDay,
    ):
        image["subtype_placeholder"] = _read_int(4)
        _read_value_mode_payload(image, ExtendedEvents.MessageImageValueMode, "amount")
    elif image_type == ExtendedEvents.MessageImageType.LevelPlusOne:
        image["subtype_placeholder"] = _read_int(4)
        _read_value_mode_payload(image, ExtendedEvents.MessageImageValueMode, "hidden_value")
    elif image_type == ExtendedEvents.MessageImageType.SecondarySkill:
        image["secondary_skill"] = _read_enum(skills.Secondary, 4)
        _read_value_mode_payload(image, ExtendedEvents.MessageImageValueMode, "secondary_skill_level")
    elif image_type in (ExtendedEvents.MessageImageType.Creatures, ExtendedEvents.MessageImageType.CreaturesSimple):
        image["creature_id"] = _read_enum(creatures.ID, 4)
        _read_value_mode_payload(image, ExtendedEvents.MessageImageValueMode, "amount")
    elif image_type in (ExtendedEvents.MessageImageType.PrimarySkill, ExtendedEvents.MessageImageType.PrimarySkillPlus):
        image["primary_skill"] = _read_enum(skills.Primary, 4)
        _read_value_mode_payload(image, ExtendedEvents.MessageImageValueMode, "amount")
    elif image_type in (ExtendedEvents.MessageImageType.SpellPoints, ExtendedEvents.MessageImageType.MovementPoints):
        image["direction"] = _read_int(4)
        _read_value_mode_payload(image, ExtendedEvents.MessageImageValueMode, "amount")
    elif (
        ExtendedEvents.MessageImageType.BuildingCastle <= image_type <= ExtendedEvents.MessageImageType.BuildingBulwark
    ):
        image["building"] = _read_enum(objects.TownBuildings.Normal, 4)
        _read_value_mode_payload(image, ExtendedEvents.MessageImageValueMode, "hidden_value")
    else:
        raise ValueError(
            f"Unsupported extended event message image type {image_type} at byte position {io.get_position()}"
        )

    return image


def parse_quest_log_image() -> dict:
    image = {"image_type": _read_enum(ExtendedEvents.QuestLogImageType, 4)}
    image_type = image["image_type"]

    if image_type == ExtendedEvents.QuestLogImageType.Artifact:
        image["artifact_id"] = _read_enum(artifacts.ID, 4)
    elif image_type == ExtendedEvents.QuestLogImageType.SpellScroll:
        image["spell_id"] = _read_enum(spells.ID, 4)
    elif image_type == ExtendedEvents.QuestLogImageType.Creatures:
        image["creature_id"] = _read_enum(creatures.ID, 4)
    elif image_type == ExtendedEvents.QuestLogImageType.Resources:
        image["resource"] = _read_enum(objects.SubID.Resource, 4)
    elif image_type == ExtendedEvents.QuestLogImageType.PrimarySkill:
        image["primary_skill"] = _read_enum(skills.Primary, 4)
    elif image_type == ExtendedEvents.QuestLogImageType.SecondarySkill:
        image["secondary_skill"] = _read_enum(skills.Secondary, 4)
    elif image_type == ExtendedEvents.QuestLogImageType.Level:
        image["level_placeholder"] = _read_int(4)
    elif image_type == ExtendedEvents.QuestLogImageType.PlayerFlag:
        image["player"] = _read_player_index(4)
    elif image_type == ExtendedEvents.QuestLogImageType.Hero:
        image["hero_name"] = _read_enum(heroes.ID, 4)
    elif image_type == ExtendedEvents.QuestLogImageType.HeroOnMap:
        image["hero_uid"] = _read_uint(4)
    elif image_type == ExtendedEvents.QuestLogImageType.MonsterOnMap:
        image["monster_uid"] = _read_uint(4)
    else:
        raise ValueError(
            f"Unsupported extended event quest log image type {image_type} at byte position {io.get_position()}"
        )

    image["value_mode"] = _read_enum(ExtendedEvents.QuestLogImageValueMode, 1)
    if image["value_mode"] == ExtendedEvents.QuestLogImageValueMode.Integer:
        image["value"] = _read_int(4)
    else:
        image["variable_id"] = _read_uint(4)
    return image


def parse_combat_stack(max_depth: int = 64) -> dict:
    stack = parse_operand(max_depth=max_depth - 1)
    stack["creature_id"] = _read_int(4)
    return stack


def write_extended_events(info: dict) -> None:
    _write_bool(info["has_extended_events"])
    if not info["has_extended_events"]:
        return

    if ExtendedEvents.READ_RAW:
        io.write_raw(info["extended_events"])
        return

    event_types = [
        ExtendedEvents.Type.Hero,
        ExtendedEvents.Type.Player,
        ExtendedEvents.Type.Town,
        ExtendedEvents.Type.Quest,
    ]

    for event_type in event_types:
        _write_uint(len(info["extended_events"][event_type]["events"]), 4)
        for event in info["extended_events"][event_type]["events"]:
            write_extended_event_info(event)

    for event_type in event_types:
        _write_uint(info["extended_events"][event_type]["id_counter"], 4)
    _write_uint(info["extended_events"]["variable_id_counter"], 4)

    _write_uint(len(info["extended_events"]["variables"]), 4)
    for variable in info["extended_events"]["variables"]:
        _write_uint(variable["id"], 4)
        write_u32_string(variable["name"])
        _write_bool(variable["save_in_campaign"])
        _write_enum(variable["value_mode"], 1)
        if variable["value_mode"] == ExtendedEvents.VariableMode.InitialValue:
            _write_int(variable["value"], 4)

    for event_type in event_types:
        _write_uint(len(info["extended_events"][event_type]["ids"]), 4)
        for event_id in info["extended_events"][event_type]["ids"]:
            _write_uint(event_id, 4)
    _write_uint(len(info["extended_events"]["variable_ids"]), 4)
    for variable_id in info["extended_events"]["variable_ids"]:
        _write_uint(variable_id, 4)


def write_extended_event_info(event: dict) -> None:
    _write_uint(event["id"], 4)
    io.write_raw(event["unknown_bytes"])
    _write_uint(len(event["actions"]), 4)
    for action in event["actions"]:
        write_action(action)
    write_u32_string(event["name"])


def write_action(action: dict) -> None:
    _write_enum(action["action_id"], 4)
    action_id = action["action_id"]
    _write_action_payload(action, action_id)


def _write_action_payload(action: dict, action_id) -> None:

    if action_id == ExtendedEvents.Action.SetVariableBasedOnCondition:
        _write_uint(action["variable_id"], 4)
        write_condition(action["condition"])
        write_condition_value(action["true_value"])
        write_condition_value(action["false_value"])
    elif action_id == ExtendedEvents.Action.ModifyVariable:
        _write_uint(action["variable_id"], 4)
        _write_enum(action["operation"], 1)
        write_expression(action["expression"])
    elif action_id == ExtendedEvents.Action.ResourcesReward:
        write_resources_reward(action)
    elif action_id == ExtendedEvents.Action.RemoveCurrentObject_FinishQuest:
        pass
    elif action_id == ExtendedEvents.Action.MessageWithReward:
        write_u32_string(action["message"])
        write_reward_list(action["reward_list"])
    elif action_id == ExtendedEvents.Action.QuestAction:
        write_condition(action["condition"])
        write_u32_string(action["proposal_message"])
        write_u32_string(action["progress_message"])
        write_u32_string(action["completion_message"])
        write_u32_string(action["hint_message"])
        write_question_action_list(action["completion_actions"])
        _write_bool(action["set_quest_log_entry"])
    elif action_id == ExtendedEvents.Action.CreaturesReward:
        _write_enum(action["operation"], 1)
        _write_enum(action["creature_id"], 4)
        write_operand(action["quantity"])
        _write_bool(action["show_with_message"])
    elif action_id == ExtendedEvents.Action.ArtifactReward:
        _write_enum(action["operation"], 1)
        _write_enum(action["artifact_id"], 4)
        if _as_int(action["artifact_id"]) == _as_int(artifacts.ID.Spell_Scroll):
            _write_enum(action["spell_id"], 4)
        else:
            _write_uint(action["artifact_spell_id_none"], 4)
        _write_bool(action["show_with_message"])
    elif action_id == ExtendedEvents.Action.BuildTownStructure:
        _write_enum(action["building"], 4)
        _write_enum(action["town_type"], 4)
        _write_bool(action["show_with_message"])
    elif action_id == ExtendedEvents.Action.SetQuestHintAndLogEntry:
        write_u32_string(action["quest_hint"])
        _write_uint(len(action["quest_log_images"]), 4)
        for image in action["quest_log_images"]:
            write_quest_log_image(image)
        _write_bool(action["show_quest_in_log"])
    elif action_id == ExtendedEvents.Action.Question:
        _write_enum(action["image_mode"], 1)
        write_u32_string(action["question"])
        write_question_action_list(action["yes_actions"])
        write_question_action_list(action["no_actions"])
        if action["image_mode"] == ExtendedEvents.QuestionImageMode.SelectionCanExit:
            write_question_action_list(action["cancel_actions"])
        if action["image_mode"] in (
            ExtendedEvents.QuestionImageMode.NoImages,
            ExtendedEvents.QuestionImageMode.SpecifyImages,
        ):
            _write_uint(len(action.get("specified_images", [])), 4)
            for image in action.get("specified_images", []):
                write_message_image(image)
        else:
            write_message_image(action["first_choice_image"])
            write_message_image(action["second_choice_image"])
            _write_bool(action["show_or_text_between_images"])
            _write_uint(len(action.get("stale_specified_images", [])), 4)
            for image in action.get("stale_specified_images", []):
                write_message_image(image)
    elif action_id == ExtendedEvents.Action.AddCreaturesToHire:
        _write_enum(action["creature_level"], 4)
        write_operand(action["quantity"])
        _write_uint(action["unused_creature_id"], 4)
        _write_bool(action["show_with_message"])
    elif action_id == ExtendedEvents.Action.SpellReward:
        _write_enum(action["spell_id"], 4)
        _write_bool(action["show_with_message"])
    elif action_id == ExtendedEvents.Action.ExperienceReward:
        write_operand(action["amount"])
        _write_bool(action["show_with_message"])
    elif action_id == ExtendedEvents.Action.SpellPointsReward:
        write_operand(action["amount"])
        _write_enum(action["operation"], 4)
        _write_bool(action["show_with_message"])
    elif action_id == ExtendedEvents.Action.MovementPointsReward:
        write_operand(action["amount"])
        _write_enum(action["operation"], 4)
        _write_bool(action["show_with_message"])
    elif action_id == ExtendedEvents.Action.PrimarySkillsReward:
        write_operand(action["amount"])
        _write_enum(action["primary_skill"], 4)
        _write_bool(action["show_with_message"])
    elif action_id == ExtendedEvents.Action.SecondarySkillsReward:
        _write_enum(action["secondary_skill_level"], 4)
        _write_enum(action["secondary_skill"], 4)
        _write_bool(action["show_with_message"])
    elif action_id == ExtendedEvents.Action.LuckReward:
        _write_int(action["amount"], 4)
        _write_bool(action["show_with_message"])
    elif action_id == ExtendedEvents.Action.MoraleReward:
        _write_int(action["amount"], 4)
        _write_bool(action["show_with_message"])
    elif action_id == ExtendedEvents.Action.Combat:
        for stack in action["slots"]:
            write_combat_stack(stack)
    elif action_id == ExtendedEvents.Action.ExecuteEvent:
        _write_enum(action["event_type"], 4)
        _write_uint(action["event_id"], 4)
    elif action_id == ExtendedEvents.Action.WarMachineReward:
        _write_enum(action["operation"], 1)
        _write_enum(action["war_machine_artifact_id"], 4)
        _write_uint(action["hidden_extra"], 4)
        _write_bool(action["show_with_message"])
    elif action_id == ExtendedEvents.Action.SpellbookReward:
        _write_enum(action["operation"], 1)
        _write_uint(action["hidden_extra_1"], 4)
        _write_uint(action["hidden_extra_2"], 4)
        _write_bool(action["show_with_message"])
    elif action_id == ExtendedEvents.Action.DisableEvent:
        pass
    elif action_id == ExtendedEvents.Action.Cycle:
        write_action_list(action["sequence_actions"])
        write_condition_value(action["first_value"])
        write_condition_value(action["second_value"])
        _write_uint(action["variable_id"], 4)
    elif action_id == ExtendedEvents.Action.ShowMessage:
        write_u32_string(action["message"])
        _write_uint(len(action["images"]), 4)
        for image in action["images"]:
            write_message_image(image)
    elif action_id == ExtendedEvents.Action.IfThenElse:
        write_condition(action["condition"])
        write_action_list(action["then_actions"])
        write_action_list(action["else_actions"])
    elif action_id == ExtendedEvents.Action.IfThenElseIf:
        write_condition(action["first_pair"]["condition"])
        write_action_list(action["first_pair"]["then_actions"])
        write_if_then_else_if_tail(action["tail"])
    else:
        raise ValueError(f"Unsupported extended event action id {action_id} at byte position {io.get_position()}")


def write_if_then_else_if_tail(tail: dict) -> None:
    _write_uint(tail["chain_marker"], 1)
    _write_uint(tail["has_next_pair"], 4)
    if tail["has_next_pair"] != 0:
        write_condition(tail["next_pair"]["condition"])
        write_action_list(tail["next_pair"]["then_actions"])
        write_if_then_else_if_tail(tail["tail"])
    else:
        write_plain_action_list(tail["else_actions"])


def write_action_list(action_list: dict) -> None:
    _write_uint(action_list["action_list_marker"], 4)
    _write_uint(action_list["action_list_unknown"], 1)
    write_plain_action_list(action_list["actions"])


def write_plain_action_list(actions: list) -> None:
    _write_uint(len(actions), 4)
    for action in actions:
        write_action(action)


def write_question_action_list(action_list: dict) -> None:
    write_action_list(action_list)


def write_operand(operand: dict) -> None:
    _write_enum(operand["mode"], 1)
    if operand["mode"] == ExtendedEvents.ExpressionOperandMode.Integer:
        _write_int(operand["integer_value"], 4)
    elif operand["mode"] == ExtendedEvents.ExpressionOperandMode.Expression:
        write_expression(operand["expression"])
    else:
        raise ValueError(
            f"Unsupported extended event operand mode {operand['mode']} at byte position {io.get_position()}"
        )


def write_condition_value(condition_value: dict) -> None:
    write_operand(condition_value)


def write_expression(expression: dict) -> None:
    _write_uint(expression["item_count_or_flag"], 1)
    _write_enum(expression["expression_type"], 4)
    expression_type = expression["expression_type"]

    if expression_type == ExtendedEvents.ExpressionType.IntegerValue:
        _write_int(expression["integer_value"], 4)
    elif expression_type == ExtendedEvents.ExpressionType.VariableValue:
        _write_uint(expression["variable_id"], 4)
    elif expression_type == ExtendedEvents.ExpressionType.Resource:
        _write_expression_player(expression["player"], 1)
        _write_enum(expression["resource"], 4)
    elif expression_type == ExtendedEvents.ExpressionType.CreatureCount:
        _write_uint(expression["creature_id"], 4)
    elif expression_type == ExtendedEvents.ExpressionType.DifficultyLevel:
        _write_enum(expression["difficulty_level"], 4)
    elif expression_type == ExtendedEvents.ExpressionType.PrimarySkill:
        _write_enum(expression["primary_skill"], 4)
    elif expression_type == ExtendedEvents.ExpressionType.ArtifactCount:
        _write_enum(expression["artifact_id"], 4)
        if _as_int(expression["artifact_id"]) == _as_int(artifacts.ID.Spell_Scroll):
            _write_enum(expression["spell_id"], 4)
        else:
            _write_uint(expression["artifact_spell_id_none"], 4)
    elif expression_type == ExtendedEvents.ExpressionType.InvertSign:
        write_expression(expression["value_expression"])
    elif expression_type in (
        ExtendedEvents.ExpressionType.Add,
        ExtendedEvents.ExpressionType.Subtract,
        ExtendedEvents.ExpressionType.Multiply,
        ExtendedEvents.ExpressionType.Divide,
        ExtendedEvents.ExpressionType.Remainder,
    ):
        write_expression(expression["left_expression"])
        write_expression(expression["right_expression"])
    elif expression_type in (
        ExtendedEvents.ExpressionType.CurrentDifficultyLevel,
        ExtendedEvents.ExpressionType.CurrentDate,
        ExtendedEvents.ExpressionType.CurrentHeroExperience,
        ExtendedEvents.ExpressionType.CurrentHeroLevel,
    ):
        pass
    elif expression_type == ExtendedEvents.ExpressionType.RandomNumber:
        write_operand(expression["min_operand"])
        write_operand(expression["max_operand"])
    else:
        raise ValueError(
            f"Unsupported extended event expression type {expression_type} at byte position {io.get_position()}"
        )


def write_condition(condition: dict) -> None:
    _write_uint(condition["item_count_or_flag"], 1)
    write_condition_node(condition)


def write_condition_node(condition: dict) -> None:
    condition_type = condition["condition_type"]
    _write_enum(condition_type, 4)
    write_condition_node_body(condition, condition_type)


def write_condition_node_body(condition: dict, condition_type) -> None:
    if condition_type == ExtendedEvents.ConditionType.BooleanValue:
        _write_bool(condition["boolean_value"])
    elif condition_type == ExtendedEvents.ConditionType.HeroHasArtifact:
        _write_enum(condition["artifact_id"], 4)
        if _as_int(condition["artifact_id"]) == _as_int(artifacts.ID.Spell_Scroll):
            _write_enum(condition["spell_id"], 4)
        else:
            _write_uint(condition["artifact_spell_id_none"], 4)
    elif condition_type == ExtendedEvents.ConditionType.MonsterDefeatedByPlayer:
        _write_enum(condition["player"], 4, signed=True)
        _write_uint(condition["monster_uid"], 4)
    elif condition_type == ExtendedEvents.ConditionType.HeroDefeatedByPlayer:
        _write_enum(condition["player"], 4, signed=True)
        _write_uint(condition["hero_uid"], 4)
    elif condition_type == ExtendedEvents.ConditionType.TownControlledByPlayer:
        _write_enum(condition["player"], 4, signed=True)
        _write_uint(condition["town_uid"], 4)
    elif condition_type in (ExtendedEvents.ConditionType.CurrentHero, ExtendedEvents.ConditionType.PlayerDefeated):
        _write_player_index(condition["player"], 4)
    elif condition_type == ExtendedEvents.ConditionType.PlayerIsHuman:
        _write_enum(condition["player"], 4, signed=True)
    elif condition_type == ExtendedEvents.ConditionType.PlayerStartingTown:
        _write_enum(condition["player"], 4, signed=True)
        _write_enum(condition["town_type"], 4)
    elif condition_type == ExtendedEvents.ConditionType.HeroAffiliation:
        _write_enum(condition["hero_name"], 4)
        _write_enum(condition["location"], 4, signed=True)
    elif condition_type == ExtendedEvents.ConditionType.HeroClass:
        _write_enum(condition["hero_class"], 4)
    elif condition_type == ExtendedEvents.ConditionType.HeroSecondarySkill:
        _write_enum(condition["secondary_skill"], 4)
        _write_enum(condition["secondary_skill_level"], 4)
    elif condition_type in (
        ExtendedEvents.ConditionType.LessThan,
        ExtendedEvents.ConditionType.GreaterThan,
        ExtendedEvents.ConditionType.Equal,
        ExtendedEvents.ConditionType.GreaterThanOrEqual,
        ExtendedEvents.ConditionType.LessThanOrEqual,
        ExtendedEvents.ConditionType.NotEqual,
    ):
        write_condition_value(condition["left_value"])
        write_condition_value(condition["right_value"])
    elif condition_type == ExtendedEvents.ConditionType.Not:
        write_condition(condition["nested_condition"])
    elif condition_type in (ExtendedEvents.ConditionType.And, ExtendedEvents.ConditionType.Or):
        _write_uint(condition["condition_count"], 4)
        for child_condition in condition.get("child_conditions", []):
            write_condition_node(child_condition)
    else:
        raise ValueError(
            f"Unsupported extended event condition type {condition_type} at byte position {io.get_position()}"
        )


def write_resources_reward(reward: dict) -> None:
    _write_enum(reward["operation"], 1)
    for resource_name in ("wood", "mercury", "ore", "sulfur", "crystal", "gems", "gold"):
        write_operand(reward[resource_name])
    _write_bool(reward["show_with_message"])


def write_reward_list(reward_list: dict) -> None:
    _write_uint(reward_list["rewards_marker"], 1)
    _write_uint(reward_list["rewards_unknown"], 4)
    _write_uint(reward_list["reward_count"], 4)
    for reward in reward_list["rewards"]:
        write_reward_entry(reward)


def write_reward_entry(reward: dict) -> None:
    action_payload = dict(reward)
    if "action_id" not in action_payload:
        action_payload["action_id"] = action_payload.get("reward_type")

    reward_type = _as_int(action_payload["action_id"])
    if not _is_extended_event_action_id(reward_type):
        raise ValueError(
            f"Unsupported extended event reward type {action_payload.get('reward_type')} at byte position {io.get_position()}"
        )
    _write_uint(reward_type, 4)
    _write_action_payload(action_payload, ExtendedEvents.Action(reward_type))


def write_message_image(image: dict) -> None:
    _write_enum(image["image_type"], 4)
    image_type = image["image_type"]

    if image_type in (
        ExtendedEvents.MessageImageType.ResourcesPlus,
        ExtendedEvents.MessageImageType.ResourcesMinus,
        ExtendedEvents.MessageImageType.ResourcesPerDay,
        ExtendedEvents.MessageImageType.ResourcesSimple,
    ):
        _write_enum(image["resource"], 4)
        _write_value_mode_payload(image, ExtendedEvents.MessageImageValueMode, "amount")
    elif image_type == ExtendedEvents.MessageImageType.Artifact:
        _write_enum(image["artifact_id"], 4)
        _write_value_mode_payload(image, ExtendedEvents.MessageImageValueMode, "hidden_value")
    elif image_type in (ExtendedEvents.MessageImageType.Spell, ExtendedEvents.MessageImageType.SpellScroll):
        _write_enum(image["spell_id"], 4)
        _write_value_mode_payload(image, ExtendedEvents.MessageImageValueMode, "hidden_value")
    elif image_type == ExtendedEvents.MessageImageType.PlayerFlag:
        _write_player_index(image["player"], 4)
        _write_value_mode_payload(image, ExtendedEvents.MessageImageValueMode, "hidden_value")
    elif image_type in (ExtendedEvents.MessageImageType.Luck, ExtendedEvents.MessageImageType.Morale):
        _write_int(image["value"], 4)
        _write_value_mode_payload(image, ExtendedEvents.MessageImageValueMode, "hidden_value")
    elif image_type in (
        ExtendedEvents.MessageImageType.Experience,
        ExtendedEvents.MessageImageType.GoldSmallPlus,
        ExtendedEvents.MessageImageType.GoldSmallMinus,
        ExtendedEvents.MessageImageType.GoldSmall,
        ExtendedEvents.MessageImageType.GoldSmallPerDay,
    ):
        _write_int(image["subtype_placeholder"], 4)
        _write_value_mode_payload(image, ExtendedEvents.MessageImageValueMode, "amount")
    elif image_type == ExtendedEvents.MessageImageType.LevelPlusOne:
        _write_int(image["subtype_placeholder"], 4)
        _write_value_mode_payload(image, ExtendedEvents.MessageImageValueMode, "hidden_value")
    elif image_type == ExtendedEvents.MessageImageType.SecondarySkill:
        _write_enum(image["secondary_skill"], 4)
        _write_value_mode_payload(image, ExtendedEvents.MessageImageValueMode, "secondary_skill_level")
    elif image_type in (ExtendedEvents.MessageImageType.Creatures, ExtendedEvents.MessageImageType.CreaturesSimple):
        _write_enum(image["creature_id"], 4)
        _write_value_mode_payload(image, ExtendedEvents.MessageImageValueMode, "amount")
    elif image_type in (ExtendedEvents.MessageImageType.PrimarySkill, ExtendedEvents.MessageImageType.PrimarySkillPlus):
        _write_enum(image["primary_skill"], 4)
        _write_value_mode_payload(image, ExtendedEvents.MessageImageValueMode, "amount")
    elif image_type in (ExtendedEvents.MessageImageType.SpellPoints, ExtendedEvents.MessageImageType.MovementPoints):
        _write_int(image["direction"], 4)
        _write_value_mode_payload(image, ExtendedEvents.MessageImageValueMode, "amount")
    elif (
        ExtendedEvents.MessageImageType.BuildingCastle <= image_type <= ExtendedEvents.MessageImageType.BuildingBulwark
    ):
        _write_enum(image["building"], 4)
        _write_value_mode_payload(image, ExtendedEvents.MessageImageValueMode, "hidden_value")
    else:
        raise ValueError(
            f"Unsupported extended event message image type {image_type} at byte position {io.get_position()}"
        )


def write_quest_log_image(image: dict) -> None:
    _write_enum(image["image_type"], 4)
    image_type = image["image_type"]

    if image_type == ExtendedEvents.QuestLogImageType.Artifact:
        _write_enum(image["artifact_id"], 4)
    elif image_type == ExtendedEvents.QuestLogImageType.SpellScroll:
        _write_enum(image["spell_id"], 4)
    elif image_type == ExtendedEvents.QuestLogImageType.Creatures:
        _write_enum(image["creature_id"], 4)
    elif image_type == ExtendedEvents.QuestLogImageType.Resources:
        _write_enum(image["resource"], 4)
    elif image_type == ExtendedEvents.QuestLogImageType.PrimarySkill:
        _write_enum(image["primary_skill"], 4)
    elif image_type == ExtendedEvents.QuestLogImageType.SecondarySkill:
        _write_enum(image["secondary_skill"], 4)
    elif image_type == ExtendedEvents.QuestLogImageType.Level:
        _write_int(image["level_placeholder"], 4)
    elif image_type == ExtendedEvents.QuestLogImageType.PlayerFlag:
        _write_player_index(image["player"], 4)
    elif image_type == ExtendedEvents.QuestLogImageType.Hero:
        _write_enum(image["hero_name"], 4)
    elif image_type == ExtendedEvents.QuestLogImageType.HeroOnMap:
        _write_uint(image["hero_uid"], 4)
    elif image_type == ExtendedEvents.QuestLogImageType.MonsterOnMap:
        _write_uint(image["monster_uid"], 4)
    else:
        raise ValueError(
            f"Unsupported extended event quest log image type {image_type} at byte position {io.get_position()}"
        )

    _write_value_mode_payload(image, ExtendedEvents.QuestLogImageValueMode, "value")


def write_combat_stack(stack: dict) -> None:
    write_operand(stack)
    _write_int(stack["creature_id"], 4)


def _parse_extended_events_alt() -> bytes:
    marker = b"\xa6\x00\x00\x00"
    extended_events = b""
    buffer = b""

    while True:
        byte_data = io.read_raw(1)
        buffer += byte_data

        if buffer == marker:
            current_pos = io.get_position()
            io.read_raw(34)

            rumor_count = _read_uint(4)
            if rumor_count < 1000:
                for _ in range(rumor_count):
                    name_length = _read_uint(4)
                    io.read_raw(name_length)
                    desc_length = _read_uint(4)
                    io.read_raw(desc_length)

            hero_count = _read_uint(4)
            io.seek(current_pos - io.get_position())

            if hero_count == 215:
                io.seek(-4)
                return extended_events

        if len(buffer) == 4:
            extended_events += buffer[:1]
            buffer = buffer[1:]
