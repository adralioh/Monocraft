# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

from __future__ import annotations

__all__ = [
	'groupChars',
	'createAtlases',
	'writeResourcePack',
	'AtlasKey',
	'AtlasCharacter',
	'Atlas',
]

import json
import math
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from PIL import Image, ImageDraw
from polygonizer import PixelImage

BACKGROUND_COLOR = "#00000000"
TEXT_COLOR = "#FFFFFFFF"
EXPANDER_COLOR = "#FFFFFF01"

FALLBACK_FONT_PROVIDERS = (
    {
        "type": "reference",
        "id": "minecraft:include/default"
    },
    {
        "type": "reference",
        "id": "minecraft:include/unifont"
    },
)
"""Fallback font providers that are used to render glyphs not included
in Monocraft"""

@dataclass(frozen=True)
class AtlasKey:
	"""Size info of a character

	This is used to group characters by their size. For simplicity, we
	create a separate atlas for each distinct size
	"""

	width: int
	height: int
	ascent: int


@dataclass(frozen=True)
class AtlasCharacter:
	"""Single character in the atlas"""

	codepoint: int
	image: PixelImage


@dataclass(frozen=True)
class Atlas:
	"""Texture atlas containing a grid of characters"""

	chars: Sequence[str]
	"""Grid of characters in the image

	This is used for the "chars" array of the font provider
	"""

	image: Image.Image


def groupChars(chars: Iterable[AtlasCharacter]) -> dict[AtlasKey, list[AtlasCharacter]]:
	"""Groups the chars together based on their size"""
	grouped: dict[AtlasKey, list[AtlasCharacter]] = {}
	for char in chars:
		key = AtlasKey(width=char.image.width, height=char.image.height, ascent=char.image.y_end)
		if key not in grouped:
			grouped[key] = []

		grouped[key].append(char)

	return grouped


def createAtlases(chars: Mapping[AtlasKey, Sequence[AtlasCharacter]]) -> dict[AtlasKey, Atlas]:
	"""Draws a texture atlas for each grouped char sequence

	The chars in each sequence must be the same size. Use `groupChars()`
	to group them.
	"""
	atlases: dict[AtlasKey, Atlas] = {}
	for key, char_list in chars.items():
		char_count = len(char_list)
		grid_width, grid_height = _calcSquareDimensions(char_count)
		char_grid: list[list[str]] = [[] for _ in range(grid_height)]

		atlas_width = grid_width * key.width
		atlas_height = grid_height * key.height
		image = Image.new("RGBA", size=(atlas_width, atlas_height), color=BACKGROUND_COLOR)

		for i, char in enumerate(char_list):
			grid_x = i % grid_width
			grid_y = i // grid_width
			char_grid[grid_y].append(chr(char.codepoint))

			atlas_x = grid_x * char.image.width
			atlas_y = grid_y * char.image.height
			_drawChar(image, char, (atlas_x, atlas_y))

		# Pad last row with null bytes so the chars aren't stretched
		if char_grid:
			last_row = char_grid[-1]
			if len(last_row) < grid_width:
				last_row.extend("\u0000" for _ in range(grid_width - len(last_row)))

		provider_chars = tuple("".join(row) for row in char_grid)
		atlases[key] = Atlas(image=image, chars=provider_chars)

	return atlases


def writeResourcePack(zip: zipfile.ZipFile, *, atlases: Mapping[AtlasKey, Atlas], namespace: str, font_name: str, description: str, license_file: str) -> None:
	"""Writes the contents of the resource pack to the zip file"""
	font_providers: list[dict[str, Any]] = []

	for key, atlas in atlases.items():
		texture_path = f"font/monocraft/{font_name}_w{key.width}_h{key.height}_a{key.ascent}.png"
		font_providers.append({
			"type": "bitmap",
			"ascent": key.ascent,
			"chars": atlas.chars,
			"file": f"{namespace}:{texture_path}",
			"height": key.height,
		})

		with zip.open(f"assets/{namespace}/textures/{texture_path}", "w") as fp:
			atlas.image.save(fp)

	font_providers.extend(FALLBACK_FONT_PROVIDERS)

	font_obj = {
		"providers": font_providers,
	}
	zip.writestr(f"assets/{namespace}/font/{font_name}.json", json.dumps(font_obj, indent=4))

	pack_meta = {
		"pack": {
			"description": description,
			"pack_format": 15,
			"supported_formats": {
				"min_inclusive": 15,
				"max_inclusive": 46,
			},
		},
	}
	zip.writestr("pack.mcmeta", json.dumps(pack_meta, indent=4))

	zip.write(license_file, "LICENSE")


def _calcSquareDimensions(count) -> tuple[int, int]:
	"""Calculates the minimum grid size needed to fit `count` characters

	This is used to make the texture atlases as small as possible, while
	still being roughly square-shaped
	"""
	base = math.floor(math.sqrt(count))
	if base ** 2 >= count:
		return (base, base)
	elif (base + 1) * base >= count:
		return (base + 1, base)
	else:
		return (base + 1, base + 1)


def _drawChar(image: Image.Image, char: AtlasCharacter, position: tuple[int, int]) -> None:
	"""Draws the char on the image at the position"""
	draw = ImageDraw.Draw(image)
	coords: list[tuple[int, int]] = []

	for y in range(char.image.height):
		atlas_y = position[1] + y
		char_y = char.image.y_end - y - 1  # Iterate in reverse because it's upside-down

		for x in range(char.image.width):
			atlas_x = position[0] + x
			char_x = char.image.x + x

			pixel = char.image[char_x, char_y]
			if pixel:
				coords.append((atlas_x, atlas_y))
			elif char_x == (char.image.x_end - 1) and char_y == (char.image.y_end - 1):
				# Draw a nearly-invisible pixel in the top-right corner
				# of the char.
				#
				# By default, Minecraft automatically shrinks the width
				# of narrow chars. By adding an invisible pixel, we
				# preserve the original monospaced size
				draw.point((atlas_x, atlas_y), EXPANDER_COLOR)

	draw.point(coords, TEXT_COLOR)
