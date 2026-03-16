from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image
from src.common import MapZ
from src.defs import groups, objects
from src.minimap.mm_layers import MM_LAYERS
from src.minimap.mm_support import (
    BLOCKED_TERRAIN_ID_OFFSET,
    KM_ID_OFFSET,
    MM_BASE2_IGNORED_OBJECTS,
    MM_OBJECT_COLORS,
    MM_STANDARD_IGNORED_OBJECTS,
    MM_TERRAIN_COLORS,
    MM_TERRAIN_COLORS_ALT,
    MP1_ID_OFFSET,
    MP2_ID_OFFSET,
    MMObjectID,
    MMTerrainID,
    ObjectMask,
)

MINIMAP_STANDARD = "standard"
MINIMAP_EXTENDED = "extended"
MINIMAP_EXTENDED_ZONE_TYPES = "extended_zonetypes"
MINIMAP_EXTENDED_ZONE_OWNERS = "extended_zoneowners"


def preview_layer_options() -> list[tuple[str, str]]:
    options = []
    for key, layer in MM_LAYERS.items():
        if key in {"standard", "base1", "base2"}:
            continue
        options.append((key, layer["display_name"]))
    return options


def render_minimap_preview(
    map_data: dict[str, Any],
    mode: str,
    selected_layers: list[str] | None = None,
    output_size: int = 512,
    gap_size: int = 16,
) -> Image.Image:
    selected_layers = selected_layers or []

    ground = _render_mode_layer(
        map_data,
        MapZ.Ground,
        mode,
        selected_layers,
        output_size,
    )

    if not map_data["general"].get("has_underground"):
        return ground

    underground = _render_mode_layer(
        map_data,
        MapZ.Underground,
        mode,
        selected_layers,
        output_size,
    )

    combined = Image.new(
        "RGBA",
        (ground.width + gap_size + underground.width, max(ground.height, underground.height)),
        (0, 0, 0, 0),
    )
    combined.paste(ground, (0, 0))
    combined.paste(underground, (ground.width + gap_size, 0))
    return combined


def _render_mode_layer(
    map_data: dict[str, Any],
    map_z: MapZ,
    mode: str,
    selected_layers: list[str],
    output_size: int,
) -> Image.Image:
    if mode == MINIMAP_STANDARD:
        return render_standard_minimap_layer(map_data, map_z, output_size=output_size)

    return render_extended_minimap_layer(
        map_data,
        map_z,
        selected_layers=selected_layers,
        output_size=output_size,
        overlay_name=_overlay_name_for_mode(mode),
    )


def render_standard_minimap_layer(map_data: dict[str, Any], map_z: MapZ, output_size: int = 512) -> Image.Image:
    map_size = map_data["general"]["map_size"]

    terrain_chunks = _split_terrain(map_data)
    blocked_tiles = {
        MapZ.Ground: set(),
        MapZ.Underground: set(),
    }
    tile_ownership = {
        MapZ.Ground: [[None for _ in range(map_size)] for _ in range(map_size)],
        MapZ.Underground: [[None for _ in range(map_size)] for _ in range(map_size)],
    }

    for obj in map_data["object_data"]:
        object_layer = MapZ(obj["coords"][2])
        object_id = _determine_standard_owner(obj)

        def_ = map_data["object_defs"][obj["def_id"]]
        blockmask = def_["red_squares"]
        interactivemask = def_["yellow_squares"]

        if object_id is None and _should_skip_object(blockmask, interactivemask):
            continue

        _process_object_standard(obj, blockmask, blocked_tiles, tile_ownership, object_id, map_size, object_layer)

    terrain_chunk = terrain_chunks[map_z]
    image = Image.new("RGB", (map_size, map_size))

    for i, tile in enumerate(terrain_chunk):
        x = i % map_size
        y = i // map_size

        object_id = tile_ownership[map_z][y][x]
        if object_id is not None:
            color = MM_OBJECT_COLORS[object_id]
        elif (x, y) in blocked_tiles[map_z]:
            color = MM_TERRAIN_COLORS[MMTerrainID(tile["terrain_type"]) + BLOCKED_TERRAIN_ID_OFFSET]
        else:
            color = MM_TERRAIN_COLORS[tile["terrain_type"]]

        image.putpixel((x, y), color)

    return image.resize((output_size, output_size), resample=Image.Resampling.NEAREST)


def render_extended_minimap_layer(
    map_data: dict[str, Any],
    map_z: MapZ,
    selected_layers: list[str],
    output_size: int = 512,
    overlay_name: str | None = None,
) -> Image.Image:
    base1 = _render_extended_layer(map_data, map_z, "base1")
    base2 = _render_extended_layer(map_data, map_z, "base2")

    canvas = Image.new("RGBA", base1.size)
    canvas.paste(base1, (0, 0), base1)
    canvas.paste(base2, (0, 0), base2)

    overlay = _load_map_overlay(map_data, map_z, overlay_name)
    if overlay is not None:
        overlay = overlay.resize(base1.size, resample=Image.Resampling.NEAREST)
        canvas.paste(overlay, (0, 0), overlay)

    for key in selected_layers:
        if key in {"standard", "base1", "base2"}:
            continue
        if key not in MM_LAYERS:
            continue
        layer_image = _render_extended_layer(map_data, map_z, key)
        canvas.paste(layer_image, (0, 0), layer_image)

    return canvas.convert("RGB").resize((output_size, output_size), resample=Image.Resampling.NEAREST)


def _split_terrain(map_data: dict[str, Any]) -> dict[MapZ, list[dict[str, Any]]]:
    map_size = map_data["general"]["map_size"]
    has_underground = map_data["general"]["has_underground"]

    if has_underground:
        half = map_size * map_size
        return {
            MapZ.Ground: map_data["terrain"][:half],
            MapZ.Underground: map_data["terrain"][half:],
        }

    return {
        MapZ.Ground: map_data["terrain"],
        MapZ.Underground: [],
    }


def _determine_standard_owner(obj: dict[str, Any]) -> int | None:
    if "owner" in obj and obj["id"] not in MM_STANDARD_IGNORED_OBJECTS:
        return obj["owner"]
    return None


def _should_skip_object(blockmask: list[int], interactivemask: list[int]) -> bool:
    has_yellow_tiles = False
    has_red_tiles = False
    has_red_or_yellow_tiles = False

    for b, i in zip(blockmask, interactivemask):
        if i == 1:
            has_yellow_tiles = True
        if b == 0 and i == 0:
            has_red_tiles = True
        if b == 0:
            has_red_or_yellow_tiles = True

        if has_red_tiles:
            return False

    return (has_yellow_tiles and not has_red_tiles) or not has_red_or_yellow_tiles


def _determine_extended_owner(obj: dict[str, Any]) -> int | tuple[int, int] | None:
    if (
        (obj["id"] == objects.ID.Border_Gate and obj["sub_id"] != objects.SubID.Border.Grave)
        or obj["id"] == objects.ID.Border_Guard
        or obj["id"] == objects.ID.Keymasters_Tent
    ):
        return obj["sub_id"] + KM_ID_OFFSET
    if obj["id"] == objects.ID.Garrison or obj["id"] == objects.ID.Garrison_Vertical:
        return (MMObjectID.GARRISON, obj["owner"])
    if obj["id"] == objects.ID.Quest_Guard:
        return MMObjectID.QUEST
    if obj["id"] in {objects.ID.One_Way_MonolithPortal_Entrance, objects.ID.One_Way_MonolithPortal_Exit}:
        return obj["sub_id"] + MP1_ID_OFFSET
    if obj["id"] == objects.ID.Two_Way_MonolithPortal:
        return obj["sub_id"] + MP2_ID_OFFSET
    if obj["id"] == objects.ID.Redwood_Observatory and obj["sub_id"] == objects.SubID.Observation.Redwood_Observatory:
        return MMObjectID.REDWOOD
    if obj["id"] == objects.ID.Pillar_of_Fire:
        return MMObjectID.PILLAR
    if obj["id"] == objects.ID.Mercenary_Camp:
        return MMObjectID.MERCENARY_CAMP
    if obj["id"] == objects.ID.Marletto_Tower:
        return MMObjectID.MARLETTO_TOWER
    if obj["id"] == objects.ID.Star_Axis:
        return MMObjectID.STAR_AXIS
    if obj["id"] == objects.ID.Garden_of_Revelation:
        return MMObjectID.GARDEN_OF_REVELATION
    if obj["id"] == objects.ID.School_of_War:
        return MMObjectID.SCHOOL_OF_WAR
    if obj["id"] == objects.ID.School_of_Magic and obj["sub_id"] == 0:
        return MMObjectID.SCHOOL_OF_MAGIC_LAND
    if obj["id"] == objects.ID.School_of_Magic and obj["sub_id"] == 1:
        return MMObjectID.SCHOOL_OF_MAGIC_SEA
    if obj["id"] == objects.ID.Arena:
        return MMObjectID.ARENA
    if obj["id"] == objects.ID.HotA_Visitable_1 and obj["sub_id"] == objects.SubID.HotAVisitable1.Colosseum_of_the_Magi:
        return MMObjectID.COLOSSEUM_OF_THE_MAGI
    if obj["id"] == objects.ID.Library_of_Enlightenment:
        return MMObjectID.LIBRARY_OF_ENLIGHTENMENT
    if obj["id"] not in groups.DECOR:
        return MMObjectID.ALL_OTHERS
    return None


def _render_extended_layer(map_data: dict[str, Any], map_z: MapZ, mm_key: str) -> Image.Image:
    map_size = map_data["general"]["map_size"]
    transparent = (0, 0, 0, 0)
    terrain_chunks = _split_terrain(map_data)

    blocked_tiles = set()
    tile_ownership = [[None for _ in range(map_size)] for _ in range(map_size)]

    mm_layer = MM_LAYERS[mm_key]
    filtered_objects = _filter_objects(map_data["object_data"], mm_layer)
    filtered_objects = [obj for obj in filtered_objects if MapZ(obj["coords"][2]) == map_z]

    for obj in filtered_objects:
        if mm_key == "base2" and (
            obj["id"] in MM_BASE2_IGNORED_OBJECTS or (obj["id"] == objects.ID.Border_Gate and obj["sub_id"] == 1001)
        ):
            continue
        if mm_key == "border" and obj["id"] == objects.ID.Border_Gate and obj["sub_id"] == 1001:
            continue

        def_ = map_data["object_defs"][obj["def_id"]]
        blockmask = def_["red_squares"]
        interactivemask = def_["yellow_squares"]
        object_id = _determine_extended_owner(obj)

        if object_id is None and _should_skip_object(blockmask, interactivemask):
            continue

        _process_object_extended(
            obj, blockmask, interactivemask, blocked_tiles, tile_ownership, object_id, mm_key, map_size
        )

    image = Image.new("RGBA", (map_size, map_size), transparent)
    terrain_chunk = terrain_chunks[map_z]
    for i, tile in enumerate(terrain_chunk):
        x = i % map_size
        y = i // map_size
        color = _extended_pixel_color(mm_key, tile, tile_ownership[y][x], blocked_tiles, x, y, transparent)
        image.putpixel((x, y), color)

    return image


def _filter_objects(object_data: list[dict[str, Any]], mm_layer: dict[str, Any]) -> list[dict[str, Any]]:
    mm_filter = mm_layer.get("filter")
    mm_subfilter = mm_layer.get("subfilter")
    mm_combofilter = mm_layer.get("combofilter")

    if mm_filter is not None:
        objs = [obj for obj in object_data if obj["id"] in mm_filter]
        if mm_subfilter is not None:
            objs = [obj for obj in objs if obj["sub_id"] in mm_subfilter]
        return objs
    if mm_combofilter is not None:
        objs = []
        for obj_id, sub_ids in mm_combofilter:
            objs.extend([obj for obj in object_data if obj["id"] == obj_id and obj["sub_id"] in sub_ids])
        return objs
    return object_data


def _process_object_extended(
    obj: dict[str, Any],
    blockmask: list[int],
    interactivemask: list[int],
    blocked_tiles: set[tuple[int, int]],
    tile_ownership: list[list[int | None]],
    object_id: int | tuple[int, int] | None,
    mm_key: str,
    map_size: int,
) -> None:
    obj_x, obj_y, _ = obj["coords"]
    for r in range(ObjectMask.ROWS):
        for c in range(ObjectMask.COLUMNS):
            index = r * ObjectMask.COLUMNS + c
            if blockmask[index] == 1:
                continue

            blocked_x = obj_x - 7 + c
            blocked_y = obj_y - 5 + r
            if not (0 <= blocked_x < map_size and 0 <= blocked_y < map_size):
                continue

            blocked_tiles.add((blocked_x, blocked_y))
            if tile_ownership[blocked_y][blocked_x] is not None:
                continue

            if mm_key == "base2" and interactivemask[index] == 1:
                tile_ownership[blocked_y][blocked_x] = None
            elif mm_key == "border" and isinstance(object_id, tuple):
                if object_id[1] != 255 and ((r == 5 and c == 6) or (r == 4 and c == 7)):
                    tile_ownership[blocked_y][blocked_x] = object_id[1]
                else:
                    tile_ownership[blocked_y][blocked_x] = object_id[0]
            else:
                tile_ownership[blocked_y][blocked_x] = object_id


def _extended_pixel_color(
    mm_key: str,
    tile: dict[str, Any],
    object_id: int | None,
    blocked_tiles: set[tuple[int, int]],
    x: int,
    y: int,
    transparent: tuple[int, int, int, int],
) -> tuple[int, int, int] | tuple[int, int, int, int]:
    if mm_key == "base1":
        if (x, y) in blocked_tiles:
            return MM_TERRAIN_COLORS_ALT[MMTerrainID(tile["terrain_type"]) + BLOCKED_TERRAIN_ID_OFFSET] + (255,)
        return MM_TERRAIN_COLORS_ALT[tile["terrain_type"]] + (255,)

    if mm_key == "base2":
        if object_id == MMObjectID.ALL_OTHERS:
            color = MM_TERRAIN_COLORS_ALT[MMTerrainID(tile["terrain_type"]) + BLOCKED_TERRAIN_ID_OFFSET]
            if color == MM_TERRAIN_COLORS_ALT[MMTerrainID.BROCK]:
                return transparent
            return color + (255,)
        return transparent

    if object_id is None:
        return transparent

    if mm_key in {
        "mercenarycamps",
        "marlettotowers",
        "staraxis",
        "gardensofrevelation",
        "schoolsofwar",
        "schoolsofmagicland",
        "schoolsofmagicsea",
        "arenas",
        "colosseumsofthemagi",
        "librariesofenlightenment",
    }:
        return (0xFF, 0xFF, 0xFF, 255)

    return MM_OBJECT_COLORS[object_id] + (255,)


def _overlay_name_for_mode(mode: str) -> str | None:
    if mode == MINIMAP_EXTENDED_ZONE_TYPES:
        return "types"
    if mode == MINIMAP_EXTENDED_ZONE_OWNERS:
        return "players"
    return None


def _load_map_overlay(map_data: dict[str, Any], map_z: MapZ, overlay_name: str | None) -> Image.Image | None:
    if overlay_name is None:
        return None

    map_stem = Path(map_data["filename"]).stem
    suffix = "g" if map_z == MapZ.Ground else "u"
    overlay_filename = f"{map_stem}_zone{overlay_name}_{suffix}.png"
    overlay_path = Path(__file__).resolve().parents[2] / "maps" / "images" / overlay_filename
    if not overlay_path.exists():
        return None
    return Image.open(overlay_path).convert("RGBA")


def _process_object_standard(
    obj: dict[str, Any],
    blockmask: list[int],
    blocked_tiles: dict[MapZ, set[tuple[int, int]]],
    tile_ownership: dict[MapZ, list[list[int | None]]],
    object_id: int | None,
    map_size: int,
    object_layer: MapZ,
) -> None:
    obj_x, obj_y, _ = obj["coords"]

    for r in range(ObjectMask.ROWS):
        for c in range(ObjectMask.COLUMNS):
            index = r * ObjectMask.COLUMNS + c
            if blockmask[index] == 1:
                continue

            blocked_x = obj_x - 7 + c
            blocked_y = obj_y - 5 + r
            if not (0 <= blocked_x < map_size and 0 <= blocked_y < map_size):
                continue

            blocked_tiles[object_layer].add((blocked_x, blocked_y))
            if tile_ownership[object_layer][blocked_y][blocked_x] is None:
                tile_ownership[object_layer][blocked_y][blocked_x] = object_id
