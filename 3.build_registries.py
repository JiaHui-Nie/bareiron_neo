#!/usr/bin/env python3
"""
Generate C source (registries.c / registries.h) from Minecraft data dumps.
"""

import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ------------------------------------------------------------------
# Block-to-item conversion overrides
# ------------------------------------------------------------------
BLOCK_TO_ITEM_OVERRIDES = {
    "grass_block": "dirt",
    "snowy_grass_block": "dirt",
    "stone": "cobblestone",
    "diamond_ore": "diamond",
    "gold_ore": "raw_gold",
    "redstone_ore": "redstone",
    "iron_ore": "raw_iron",
    "coal_ore": "coal",
    "copper_ore": "raw_copper",
    "snow": "snowball",
    "dead_bush": "stick",
}

# Blacklisted block name substrings
BLOCK_BLACKLIST = [
    "spruce_",
    "birch_",
    "jungle_",
    "acacia_",
    "dark_oak_",
    "mangrove_",
    "cherry_",
    "pale_oak_",
    "crimson_",
    "warped_",
    "bamboo_",
    "deepslate",
    "infested_",
    "stained_",
    "_terracotta",
    "_head",
]

# Whitelisted blocks — guaranteed inclusion in the 256-entry palette
BLOCK_WHITELIST = [
    "air",
    "water",
    "water_1",
    "water_2",
    "water_3",
    "water_4",
    "water_5",
    "water_6",
    "water_7",
    "lava",
    "lava_2",
    "lava_4",
    "lava_6",
    "snowy_grass_block",
    "mud",
    "moss_carpet",
    "oak_slab",
    "stone_slab",
    "cobblestone_slab",
    "composter",
    "coal_block",
    "copper_ore",
    "copper_block",
]

# Supported biomes ("beach" is listed but not yet fully supported)
BIOMES = [
    "plains",
    "mangrove_swamp",
    "desert",
    "snowy_plains",
    "beach",
]

REQUIRED_REGISTRIES = [
    "cat_variant",
    "chicken_variant",
    "cow_variant",
    "frog_variant",
    "painting_variant",
    "pig_variant",
    "wolf_sound_variant",
    "wolf_variant",
    "damage_type",
]


# ------------------------------------------------------------------
# VarInt encoding (Minecraft protocol)
# ------------------------------------------------------------------
def write_varint(value):
    """Encode a non-negative integer as a Minecraft VarInt."""
    out = bytearray()
    while True:
        if value < 0x80:
            out.append(value)
            return bytes(out)
        out.append((value & 0x7F) | 0x80)
        value >>= 7


# ------------------------------------------------------------------
# Binary serialization helpers
# ------------------------------------------------------------------
def serialize_registry(name, entries):
    """Serialize a single Registry Data packet (ID 0x07)."""
    parts = bytearray()
    parts.append(0x07)  # packet ID

    name_buf = name.encode("utf-8")
    parts += write_varint(len(name_buf))
    parts += name_buf

    parts += write_varint(len(entries))

    for entry_name in entries:
        entry_buf = entry_name.encode("utf-8")
        parts += write_varint(len(entry_buf))
        parts += entry_buf
        parts.append(0x00)

    length_buf = write_varint(len(parts))
    return length_buf + bytes(parts)


def serialize_tags(tags):
    """Serialize an Update Tags packet (ID 0x0D)."""
    parts = bytearray()
    parts.append(0x0D)  # packet ID

    parts += write_varint(len(tags))

    for tag_type, tag_entries in tags.items():
        identifier = tag_type.encode("utf-8")
        parts += write_varint(len(identifier))
        parts += identifier

        parts += write_varint(len(tag_entries))

        for tag_name, ids in tag_entries.items():
            tag_id = tag_name.encode("utf-8")
            parts += write_varint(len(tag_id))
            parts += tag_id
            parts += write_varint(len(ids))
            for bid in ids:
                parts += write_varint(bid)

    length_buf = write_varint(len(parts))
    return length_buf + bytes(parts)


def to_varint_buffer(values):
    """Concatenate multiple VarInt-encoded values into a single byte string."""
    return b"".join(write_varint(v) for v in values)


def to_c_array(data):
    """Convert bytes to a C-style hex array string."""
    hex_bytes = [f"0x{b:02x}" for b in data]
    lines = []
    for i in range(0, len(hex_bytes), 12):
        lines.append("  " + ", ".join(hex_bytes[i:i + 12]))
    return ",\n".join(lines)


# ------------------------------------------------------------------
# Data extraction
# ------------------------------------------------------------------
def scan_directory(base_path):
    """Recursively scan a directory for JSON files.

    Returns a dict mapping registry name (relative dir path with '/')
    to a list of entry names (filenames without .json).
    """
    entries = {}
    for root, _dirs, files in os.walk(base_path):
        for fname in files:
            if not fname.endswith(".json"):
                continue
            rel_path = os.path.relpath(root, base_path)
            rel_path = rel_path.replace(os.sep, "/")
            registry_name = "" if rel_path == "." else rel_path
            entry_name = fname[:-5]  # strip ".json"
            entries.setdefault(registry_name, []).append(entry_name)

    # Sort entries alphabetically for deterministic output
    for key in entries:
        entries[key].sort()

    return entries


def extract_items_and_blocks():
    """Extract block/item data from the Minecraft registry dumps."""

    blocks_path = os.path.join(SCRIPT_DIR, "notchian", "generated", "reports", "blocks.json")
    registries_path = os.path.join(SCRIPT_DIR, "notchian", "generated", "reports", "registries.json")

    with open(blocks_path, "r", encoding="utf-8") as f:
        block_source = json.load(f)

    with open(registries_path, "r", encoding="utf-8") as f:
        registries_json = json.load(f)

    item_source = registries_json["minecraft:item"].get("entries", {})
    block_registry_source = registries_json["minecraft:block"].get("entries", {})

    # Sort blocks by their default state's network ID
    def sort_key(entry):
        _name, data = entry
        for state in data.get("states", []):
            if state.get("default"):
                return state["id"]
        return float("inf")

    sorted_blocks = sorted(block_source.items(), key=sort_key)

    blocks = {}
    items = {}

    for block_name, block_data in sorted_blocks:
        default_state = None
        for state in block_data.get("states", []):
            if state.get("default"):
                default_state = state
                break
        if default_state is None:
            continue

        # Skip blacklisted blocks
        name_no_prefix = block_name.replace("minecraft:", "")
        if any(sub in block_name for sub in BLOCK_BLACKLIST):
            continue

        blocks[name_no_prefix] = default_state["id"]

        # Include snowy variants
        props = default_state.get("properties", {})
        if "snowy" in props:
            snowy_state = None
            for state in block_data.get("states", []):
                if state.get("properties", {}).get("snowy"):
                    snowy_state = state
                    break
            if snowy_state is not None:
                blocks["snowy_" + name_no_prefix] = snowy_state["id"]

        # Include fluid levels
        definition = block_data.get("definition", {})
        if "fluid" in definition:
            for i in range(1, 8):
                blocks[name_no_prefix + "_" + str(i)] = default_state["id"] + i

    for item_name, item_data in item_source.items():
        items[item_name.replace("minecraft:", "")] = item_data["protocol_id"]

    # Build the 256-entry block palette
    palette = {}
    mapping = []
    mapping_with_overrides = []

    # Whitelisted blocks first
    for block in BLOCK_WHITELIST:
        palette[block] = blocks.get(block, 0)
        mapping.append(items.get(block, 0))
        override = BLOCK_TO_ITEM_OVERRIDES.get(block)
        val = items.get(override) or items.get(block) or 0
        mapping_with_overrides.append(val)
        if len(mapping) == 256:
            break

    # Then add blocks that have matching items
    for block in blocks:
        if block not in items:
            continue
        if block in BLOCK_WHITELIST:
            continue
        palette[block] = blocks[block]
        mapping.append(items.get(block, 0))
        override = BLOCK_TO_ITEM_OVERRIDES.get(block)
        val = items.get(override) or items.get(block) or 0
        mapping_with_overrides.append(val)
        if len(mapping) == 256:
            break

    # Build block registry (IDs from registries.json, used by tags)
    block_registry = {}
    for block_name, block_data in block_registry_source.items():
        block_registry[block_name.replace("minecraft:", "")] = block_data["protocol_id"]

    return {
        "blocks": blocks,
        "items": items,
        "palette": palette,
        "mapping": mapping,
        "mappingWithOverrides": mapping_with_overrides,
        "blockRegistry": block_registry,
    }


# ------------------------------------------------------------------
# Main code generation
# ------------------------------------------------------------------
def convert():
    input_path = os.path.join(SCRIPT_DIR, "notchian", "generated", "data", "minecraft")
    output_path = os.path.join(SCRIPT_DIR, "src", "registries.c")
    header_path = os.path.join(SCRIPT_DIR, "include", "registries.h")

    registries = scan_directory(input_path)
    registry_buffers = []

    for registry in REQUIRED_REGISTRIES:
        if registry not in registries:
            print(f'Missing required registry "{registry}"!', file=sys.stderr)
            return
        if registry.endswith("variant"):
            entry_list = registries[registry]
            if "temperate" in entry_list:
                registry_buffers.append(serialize_registry(registry, ["temperate"]))
            else:
                shortest = min(entry_list, key=len)
                registry_buffers.append(serialize_registry(registry, [shortest]))
        else:
            registry_buffers.append(serialize_registry(registry, registries[registry]))

    # Biomes and dimensions
    registry_buffers.append(serialize_registry("worldgen/biome", BIOMES))
    registry_buffers.append(serialize_registry("dimension_type", ["overworld"]))
    full_registry_buffer = b"".join(registry_buffers)

    ib = extract_items_and_blocks()
    br = ib["blockRegistry"]

    tag_buffer = serialize_tags({
        "fluid": {
            "water": [1, 2],
            "lava": [3, 4],
        },
        "block": {
            "mineable/pickaxe": [
                br.get("stone", 0),
                br.get("stone_slab", 0),
                br.get("cobblestone", 0),
                br.get("cobblestone_slab", 0),
                br.get("sandstone", 0),
                br.get("sandstone_slab", 0),
                br.get("ice", 0),
                br.get("diamond_ore", 0),
                br.get("gold_ore", 0),
                br.get("redstone_ore", 0),
                br.get("iron_ore", 0),
                br.get("coal_ore", 0),
                br.get("copper_ore", 0),
                br.get("furnace", 0),
                br.get("iron_block", 0),
                br.get("gold_block", 0),
                br.get("diamond_block", 0),
                br.get("redstone_block", 0),
                br.get("coal_block", 0),
                br.get("copper_block", 0),
            ],
            "mineable/axe": [
                br.get("oak_log", 0),
                br.get("oak_planks", 0),
                br.get("oak_wood", 0),
                br.get("oak_slab", 0),
                br.get("crafting_table", 0),
                br.get("chest", 0),
            ],
            "mineable/shovel": [
                br.get("grass_block", 0),
                br.get("dirt", 0),
                br.get("sand", 0),
                br.get("snow", 0),
                br.get("snow_block", 0),
                br.get("mud", 0),
            ],
            "leaves": [
                br.get("oak_leaves", 0),
            ],
        },
        "item": {
            "planks": [
                ib["items"].get("oak_planks", 0),
            ],
        },
    })

    network_block_palette = to_varint_buffer(ib["palette"].values())

    # --- Generate registries.c ---
    block_palette_str = ", ".join(str(v) for v in ib["palette"].values())
    b_to_i_str = ", ".join(str(v) for v in ib["mappingWithOverrides"])

    switch_lines = []
    for i, c in enumerate(ib["mapping"]):
        if c:
            switch_lines.append(f"case {c}: return {i};")
    switch_body = "\n    ".join(switch_lines)

    source_code = f"""\
#include <stdint.h>
#include "registries.h"

// Binary contents of required "Registry Data" packets
uint8_t registries_bin[] = {{
{to_c_array(full_registry_buffer)}
}};
// Binary contents of "Update Tags" packets
uint8_t tags_bin[] = {{
{to_c_array(tag_buffer)}
}};

// Block palette
uint16_t block_palette[] = {{ {block_palette_str} }};
// Block palette as VarInt buffer
uint8_t network_block_palette[] = {{
{to_c_array(network_block_palette)}
}};

// Block-to-item mapping
uint16_t B_to_I[] = {{ {b_to_i_str} }};
// Item-to-block mapping
uint8_t I_to_B (uint16_t item) {{
  switch (item) {{
    {switch_body}
    default: break;
  }}
  return 0;
}}
"""

    # --- Generate registries.h ---
    block_defines = "\n".join(
        f"#define B_{name} {i}" for i, name in enumerate(ib["palette"].keys())
    )
    item_defines = "\n".join(
        f"#define I_{name} {id}" for name, id in ib["items"].items()
    )
    biome_defines = "\n".join(
        f"#define W_{name} {i}" for i, name in enumerate(BIOMES)
    )
    damage_defines = "\n".join(
        f"#define D_{name} {i}" for i, name in enumerate(registries.get("damage_type", []))
    )

    header_code = f"""\
#ifndef H_REGISTRIES
#define H_REGISTRIES

#include <stdint.h>

// Binary packet data ({len(full_registry_buffer) + len(tag_buffer)} bytes total)
extern uint8_t registries_bin[{len(full_registry_buffer)}];
extern uint8_t tags_bin[{len(tag_buffer)}];

extern uint16_t block_palette[256]; // Block palette
extern uint8_t network_block_palette[{len(network_block_palette)}]; // Block palette as VarInt buffer
extern uint16_t B_to_I[256]; // Block-to-item mapping
uint8_t I_to_B (uint16_t item); // Item-to-block mapping

// Block identifiers
{block_defines}

// Item identifiers
{item_defines}

// Biome identifiers
{biome_defines}

// Damage type identifiers
{damage_defines}

#endif
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(source_code)
    with open(header_path, "w", encoding="utf-8") as f:
        f.write(header_code)

    print("Done. Wrote to `registries.c` and `registries.h`")


def main():
    convert()


if __name__ == "__main__":
    main()
