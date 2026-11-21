"""Pack the inherited T3 frame and both new armor LODs into one atlas."""
from dataclasses import dataclass
from math import ceil
from pathlib import Path

import bpy
from mathutils import Vector
import numpy as np


ROOT = Path(__file__).resolve().parent
SIZE = 2048
FRAME_SIZE = 1216
FRAME_PAD = 8
PAD = 3
ARMOR_START = FRAME_SIZE + 2 * FRAME_PAD
REGIONS = (
    (ARMOR_START, 0, SIZE - ARMOR_START, SIZE),
    (0, ARMOR_START, ARMOR_START, SIZE - ARMOR_START),
)

# Titanium, composite, exposed rim, fastener, secondary titanium, dark rim.
BASE_COLOR = np.array([
    (.425, .432, .439), (.112, .118, .124), (.505, .511, .519),
    (.331, .340, .347), (.345, .354, .365), (.285, .294, .305),
], dtype=np.float32)
GLOSS = np.array([.445, .225, .55, .50, .425, .40], dtype=np.float32)

# Rest-space positions shared by both LODs. Each pair is a shallow inspection
# datum cut, placed in the clear central field between the stamped stiffeners.
DATUMS = {
    'armorChest': (0.00, 1.468, .024),
    'armorAbdomen': (0.00, 1.166, .018),
    'armorBackYoke': (0.00, 1.469, .024),
}


@dataclass
class Chart:
    mesh: object
    face: object
    finish: int
    datum: tuple | None
    channel: object
    projected: np.ndarray
    world: np.ndarray
    triangles: np.ndarray


def _charts(objects):
    result = []
    for obj in objects:
        mesh = obj.data
        finish = mesh.attributes.get('armor_finish')
        if finish is None or finish.domain != 'FACE' or finish.data_type != 'INT':
            raise ValueError(f'{obj.name} needs an integer armor_finish face attribute')
        if not mesh.uv_layers:
            mesh.uv_layers.new(name='EXO_Atlas')
        mesh.calc_loop_triangles()
        triangles = [[] for _ in mesh.polygons]
        for tri in mesh.loop_triangles:
            face = mesh.polygons[tri.polygon_index]
            triangles[tri.polygon_index].append(
                [index - face.loop_start for index in tri.loops]
            )
        orientation = obj.matrix_world.to_3x3().inverted().transposed()
        datum = DATUMS.get(obj.name.split('_', 1)[-1])
        channel=obj.get('formed_channel')
        for face, chart_triangles in zip(mesh.polygons, triangles):
            finish_index = finish.data[face.index].value
            if not 0 <= finish_index < len(BASE_COLOR):
                raise ValueError(f'{obj.name} face {face.index} has unknown finish {finish_index}')
            normal = (orientation @ face.normal).normalized()
            up = Vector((0, 0, 1)) if abs(normal.z) < .97 else Vector((0, 1, 0))
            right = up.cross(normal).normalized()
            up = normal.cross(right)
            points = [obj.matrix_world @ mesh.vertices[index].co for index in face.vertices]
            world = np.asarray(points, dtype=np.float64)
            projected = np.asarray([(point.dot(right), point.dot(up)) for point in points])
            chart_triangles = np.asarray(chart_triangles, dtype=np.int32)
            corners = projected[chart_triangles]
            sides = corners[:, 1:] - corners[:, :1]
            areas = sides[:, 0, 0] * sides[:, 1, 1] - sides[:, 0, 1] * sides[:, 1, 0]
            if min(areas) <= 1e-12:
                # A folded quad cannot retain its planar shape without UV overlap.
                angles = np.arange(len(points)) * (2 * np.pi / len(points))
                radius = np.sqrt(max(face.area, 1e-10) / np.pi)
                projected = radius * np.column_stack((np.cos(angles), np.sin(angles)))
            projected -= projected.min(axis=0)
            result.append(Chart(mesh, face, finish_index, datum, channel, projected, world, chart_triangles))
    return result


def _try_pack(charts, scale):
    specs = []
    for index, chart in enumerate(charts):
        width, height = (max(3, ceil(d * scale)) for d in chart.projected.max(axis=0))
        specs.append((width + 2 * PAD, height + 2 * PAD, index))
    specs.sort(key=lambda spec: (spec[1], spec[0]), reverse=True)
    shelves = []
    positions = [None] * len(charts)
    next_rows = [0] * len(REGIONS)
    for width, height, index in specs:
        candidates = [
            (shelf[3] - shelf[1] - width, slot)
            for slot, shelf in enumerate(shelves)
            if width <= shelf[3] - shelf[1] and height <= shelf[4]
        ]
        if candidates:
            _, slot = min(candidates)
            shelf = shelves[slot]
        else:
            for region, (x, y, available_width, available_height) in enumerate(REGIONS):
                if width <= available_width and next_rows[region] + height <= available_height:
                    shelf = [x, x, y + next_rows[region], x + available_width, height]
                    shelves.append(shelf)
                    next_rows[region] += height
                    break
            else:
                return None
        positions[index] = (shelf[1], shelf[2], width, height)
        shelf[1] += width
    return positions


def _pack(charts):
    if not charts:
        raise ValueError('No armor charts to pack')
    low, high = 0.0, SIZE / max(chart.projected.max() for chart in charts)
    placements = _try_pack(charts, low)
    if placements is None:
        raise ValueError('Armor face count leaves insufficient atlas padding')
    for _ in range(17):
        scale = (low + high) * .5
        test = _try_pack(charts, scale)
        if test is None:
            high = scale
        else:
            low, placements = scale, test
    return low, placements


def _resample_frame(name):
    source = bpy.data.images.load(str(ROOT / 'textures_t3' / (name + '.png')), check_existing=False)
    if name != 'exo_dif':
        source.colorspace_settings.name = 'Non-Color'
    width, height = source.size
    pixels = np.empty(width * height * 4, dtype=np.float32)
    source.pixels.foreach_get(pixels)
    bpy.data.images.remove(source)
    pixels = pixels.reshape(height, width, 4)
    # Sample through texel centers so the source UVs retain the same alignment.
    xs = (np.arange(FRAME_SIZE) + .5) * (width / FRAME_SIZE) - .5
    ys = (np.arange(FRAME_SIZE) + .5) * (height / FRAME_SIZE) - .5
    ix, iy = xs.astype(int), ys.astype(int)
    xfrac = (xs - ix).astype(np.float32)[None, :, None]
    yfrac = (ys - iy).astype(np.float32)[:, None, None]
    lower = pixels[iy[:, None], ix] * (1 - xfrac) + pixels[iy[:, None], ix + 1] * xfrac
    upper = pixels[iy[:, None] + 1, ix] * (1 - xfrac) + pixels[iy[:, None] + 1, ix + 1] * xfrac
    section = lower * (1 - yfrac) + upper * yfrac
    return np.pad(section, ((FRAME_PAD, FRAME_PAD), (FRAME_PAD, FRAME_PAD), (0, 0)), mode='edge')


def _world_samples(chart, local_uv, width, height):
    x = np.arange(width, dtype=np.float32)[None, :] + .5
    y = np.arange(height, dtype=np.float32)[:, None] + .5
    best = np.full((height, width), -np.inf, dtype=np.float32)
    samples = np.zeros((height, width, 3), dtype=np.float32)
    for indices in chart.triangles:
        a, b, c = local_uv[indices]
        det = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        u = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / det
        v = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / det
        weights = np.stack((u, v, 1 - u - v), axis=-1)
        confidence = np.min(weights, axis=-1)
        choose = confidence > best
        best[choose] = confidence[choose]
        # Clamping barycentrics extends the finish past the island for mipmaps.
        weights = np.maximum(weights[choose], 0)
        weights /= weights.sum(axis=-1, keepdims=True)
        samples[choose] = weights @ chart.world[indices]
    return np.moveaxis(samples, -1, 0)


def _datum_mask(x, z, datum):
    origin_x, origin_z, length = datum
    lower = origin_z - .006
    d0 = np.hypot(np.maximum(np.abs(x - origin_x) - length / 2, 0), z - origin_z)
    d1 = np.hypot(np.maximum(np.abs(x - origin_x) - length * .33, 0), z - lower)
    distance = np.minimum(d0, d1)
    return np.clip((.0024 - distance) / .0014, 0, 1)


def _texture_patch(world, finish, datum, channel):
    x, y, z = world
    along = x + .73 * y
    across = z + .09 * x + .03 * y
    slow = np.sin(y * 62 + z * 31) * np.sin(x * 57 - z * 22)
    scuff = np.sin(along * 142 - across * 22) * np.sin(across * 285 + y * 45)
    brush = np.sin(across * 2820 + np.sin(along * 74) * 1.8)
    brush += np.sin(across * 4260 - np.sin(along * 49) * 1.4) * .54

    # Interrupted scratches in rest-space coordinates continue across UV seams.
    scratch_u = 53 * along - 12 * across
    scratch_v = 155 * across + 14 * along
    row = np.floor(scratch_v)
    phase = np.remainder(np.sin(row * 12.9898) * 43758.5453, 1.0)
    streak = np.clip(1 - np.abs(np.remainder(scratch_v, 1) - .18 - .64 * phase) * 15, 0, 1)
    streak *= np.clip((np.sin(3 * scratch_u + phase * 16) - .67) * 4, 0, 1)
    streak *= np.clip((phase - .51) * 3, 0, 1)

    if finish == 1:
        fleck = np.sin(x * 1876 + y * 1037) * np.sin(z * 1628 + y * 1592)
        tint = .009 * slow + .007 * fleck
        gloss = GLOSS[finish] + .013 * fleck + .013 * slow
        relief = .002 * fleck
    else:
        rim = .027 * np.maximum(0, slow) if finish in (2, 5) else 0
        tint = .008 * slow + .004 * scuff + .005 * brush + .056 * streak + rim
        gloss = GLOSS[finish] + .014 * slow + .008 * brush + .042 * streak
        relief = .002 * brush - .014 * streak
        if finish == 0 and datum:
            cut = _datum_mask(x, z, datum)
            lip = _datum_mask(x, z + .0019, datum) * (1 - cut)
            tint += .038 * lip - .100 * cut
            gloss += .036 * lip - .052 * cut
            relief -= .032 * cut
        if finish == 0 and channel is not None:
            # Shallow stamped flute with closed, round ends. Baking the recess
            # allows it to follow the formed metal continuously across UV seams.
            pos=world-np.asarray(channel[:3])[:,None,None]
            across=np.einsum('i,ijk->jk',channel[3:6],pos)
            along=np.einsum('i,ijk->jk',channel[6:9],pos)
            half_length=channel[10]*.245
            span=channel[9]*.145
            transverse=np.abs(across)-span-.14*along
            dist=np.hypot(transverse,np.maximum(0,np.abs(along)-half_length))
            shoulder=np.clip((.0047-dist)/.0025,0,1)
            bottom=np.clip((.0029-dist)/.0019,0,1)
            relief-=.50*shoulder+.34*bottom
            tint-=.025*bottom
            gloss+=.045*(shoulder-bottom)
    albedo = np.clip(BASE_COLOR[finish] + tint[..., None], 0, 1)
    du = np.gradient(relief, axis=1)
    dv = np.gradient(relief, axis=0)
    normal = np.stack((-du, -dv, np.ones_like(du)), axis=-1)
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    return albedo, normal * .5 + .5, np.clip(gloss, 0, 1)[..., None]


def _save_image(name, atlas, directory):
    previous = bpy.data.images.get(name)
    if previous:
        previous.name = name + '_source_t3'
    image = bpy.data.images.new(name, width=SIZE, height=SIZE, alpha=True)
    if name != 'exo_dif':
        image.colorspace_settings.name = 'Non-Color'
    image.pixels.foreach_set(np.ascontiguousarray(atlas).ravel())
    image.file_format = 'PNG'
    image.filepath_raw = str(directory / (name + '.png'))
    image.save()
    image.filepath = '//textures_t3a/' + name + '.png'
    return image


def _wire_material(material, images):
    tree = material.node_tree
    for node in tree.nodes:
        if node.type == 'TEX_IMAGE' and node.image:
            for name, image in images.items():
                if node.image.name.startswith(name):
                    node.image = image
                    node.extension = 'EXTEND'
                    break
    shader = next(node for node in tree.nodes if node.type == 'BSDF_PRINCIPLED')
    coords = tree.nodes.new('ShaderNodeTexCoord')
    coords.location = (-1050, -720)
    axes = tree.nodes.new('ShaderNodeSeparateXYZ')
    axes.location = (-830, -720)
    tree.links.new(coords.outputs['UV'], axes.inputs[0])
    masks = []
    for index, axis in enumerate(('X', 'Y')):
        mask = tree.nodes.new('ShaderNodeMath')
        mask.operation = 'GREATER_THAN'
        mask.inputs[1].default_value = ARMOR_START / SIZE
        mask.location = (-625, -670 - 135 * index)
        tree.links.new(axes.outputs[axis], mask.inputs[0])
        masks.append(mask)
    region = tree.nodes.new('ShaderNodeMath')
    region.operation = 'MAXIMUM'
    region.location = (-420, -725)
    for index, mask in enumerate(masks):
        tree.links.new(mask.outputs[0], region.inputs[index])
    metallic = tree.nodes.new('ShaderNodeMath')
    metallic.operation = 'MULTIPLY_ADD'
    metallic.label = 'T3 frame and titanium plate metallic'
    metallic.location = (-210, -725)
    metallic.inputs[1].default_value = .10
    metallic.inputs[2].default_value = shader.inputs['Metallic'].default_value
    tree.links.new(region.outputs[0], metallic.inputs[0])
    tree.links.new(metallic.outputs[0], shader.inputs['Metallic'])


def apply(frame_objects, armor_objects):
    """Build atlas images and remap both LODs. Return the shared exo_mat."""
    frame_objects = list(frame_objects)
    armor_objects = list(armor_objects)
    charts = _charts(armor_objects)
    scale, positions = _pack(charts)
    names = ('exo_dif', 'exo_nrm', 'exo_gloss')
    atlases = [np.ones((SIZE, SIZE, 4), dtype=np.float32) for _ in names]
    defaults = ((.16, .17, .18), (.5, .5, 1), (.36, .36, .36))
    for name, atlas, background in zip(names, atlases, defaults):
        atlas[..., :3] = background
        atlas[:ARMOR_START, :ARMOR_START] = _resample_frame(name)

    # Frame UVs were already mutually disjoint across both LODs.
    for mesh in dict.fromkeys(obj.data for obj in frame_objects):
        layer = mesh.uv_layers.active.data
        for loop in layer:
            loop.uv = (loop.uv * FRAME_SIZE + Vector((FRAME_PAD, FRAME_PAD))) / SIZE
    for chart, (x, y, width, height) in zip(charts, positions):
        local_uv = chart.projected * scale
        # Very thin facets still receive three usable texels across each axis.
        extent = local_uv.max(axis=0)
        local_uv *= np.maximum(extent, 3) / extent
        local_uv += PAD
        layer = chart.mesh.uv_layers.active.data
        for loop, uv in zip(chart.face.loop_indices, (local_uv + (x, y)) / SIZE):
            layer[loop].uv = uv
        values = _texture_patch(_world_samples(chart, local_uv, width, height),
                                chart.finish, chart.datum, chart.channel)
        for atlas, rgb in zip(atlases, values):
            atlas[y:y + height, x:x + width, :3] = rgb

    directory = ROOT / 'textures_t3a'
    directory.mkdir(exist_ok=True)
    images = {name: _save_image(name, atlas, directory) for name, atlas in zip(names, atlases)}
    material = bpy.data.materials['exo_mat']
    _wire_material(material, images)
    for obj in frame_objects + armor_objects:
        if list(obj.data.materials) != [material]:
            obj.data.materials.clear()
            obj.data.materials.append(material)
        for face in obj.data.polygons:
            face.material_index = 0
    print(f'T3A atlas packed {len(charts)} armor faces at {scale:.0f} px/m plus the 1216 px frame')
    return material
