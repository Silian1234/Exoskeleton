"""Read-only Tier 3 armor audit. Run in Blender background against exo_t3a.blend."""
from collections import Counter
from itertools import combinations
from pathlib import Path
import hashlib
import json
import struct
import sys

import bpy
import numpy as np
from mathutils import Vector
from mathutils.geometry import closest_point_on_tri
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import review
from proximity import Garment, Pair, edges_of
from validate import uv_stats


LIMITS = {0: 30000, 1: 10000}
REFS = ('REF_top', 'REF_pants')
TARGET = (0.005, 0.030)
GAP_SEARCH_REACH = .031
RAY_DIRECTIONS = tuple(Vector(direction).normalized() for direction in (
    (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1),
    (1, 1, 1), (1, -1, 1), (1, -1, -1), (-1, -1, -1),
))
TEXTURES = dict(exo_dif='sRGB', exo_nrm='Non-Color', exo_gloss='Non-Color')
AXIAL_BONES = {
    'chest': ('Spine2', 'Spine3'), 'abdomen': ('Spine2', 'Spine3'),
    'back': ('Spine2', 'Spine3'), 'flank': ('Spine2',),
    'gorget': ('Neck', 'Spine3'), 'fauld': ('Pelvis',),
}
LIMB_BONES = {
    'pauldron': 'Upperarm', 'vambrace': 'Forearm1', 'thigh': 'Thigh1', 'greave': 'Calf',
}
LEGACY = '--' in sys.argv and '--baseline' in sys.argv[sys.argv.index('--') + 1:]


def is_armor(obj):
    return bool(obj.get('t3a_armor')) or obj.name.lower().startswith(('exo_armor', 'exo1_armor'))


def part_role(obj):
    if is_armor(obj):
        return 'armor'
    if obj.get('t3a_carrier'):
        return 'carrier'
    return 'frame'


def allowed_armor_bones(name):
    zone = name.split('_', 1)[1].removeprefix('armor').lower()
    for part, bones in AXIAL_BONES.items():
        if zone.startswith(part):
            return {'Base Human' + bone for bone in bones}
    for part, bone in LIMB_BONES.items():
        if zone.startswith(part) and zone[-1] in ('l', 'r'):
            return {'Base Human' + zone[-1].upper() + bone}
    return set()


def mm(value):
    return round(float(value) * 1000, 3)


def bone_parent(bone):
    return bone.parent.name if bone.parent else None


def rig_errors(rig):
    with bpy.data.libraries.load(str(ROOT / 'base_scene.blend')) as (_, loaded):
        loaded.objects = ['EFT_Bind']
    source = loaded.objects[0]
    errors = []
    if rig.matrix_world != source.matrix_world:
        errors.append('Armature world transform differs from base_scene.blend')
    if set(rig.data.bones.keys()) != set(source.data.bones.keys()):
        errors.append('Armature bone name set differs from base_scene.blend')
    for bone in rig.data.bones:
        other = source.data.bones.get(bone.name)
        if other is not None and (
            bone.matrix_local != other.matrix_local or bone.head_local != other.head_local
            or bone.tail_local != other.tail_local or bone_parent(bone) != bone_parent(other)
        ):
            errors.append(f'Bind bone differs from base_scene.blend: {bone.name}')
    if rig.data.pose_position != 'REST':
        errors.append('Saved armature pose position is not REST')
    bpy.data.objects.remove(source)
    return errors


def texture_audit(errors):
    mat = bpy.data.materials.get('exo_mat')
    nodes = list(mat.node_tree.nodes) if mat and mat.node_tree else []
    images = [node.image for node in nodes if node.type == 'TEX_IMAGE' and node.image]
    results = {}
    folder = ROOT / ('textures_t3' if LEGACY else 'textures_t3a')
    for name, space in TEXTURES.items():
        path = folder / (name + '.png')
        node_matches = [
            img for img in images
            if Path(bpy.path.abspath(img.filepath)).resolve() == path.resolve()
        ]
        if len(node_matches) != 1:
            errors.append(f'Found {len(node_matches)} material image nodes resolving to {name}.png')
        for image in node_matches:
            if not image.filepath.startswith('//'):
                errors.append(f'External image path is not relative: {name}')
            if image.colorspace_settings.name != space:
                errors.append(f'Image color space differs from {space}: {name}')
        if not path.is_file():
            errors.append(f'Missing texture {path.parent.name}/{path.name}')
            continue
        with path.open('rb') as file:
            head = file.read(33)
        if len(head) != 33 or head[:8] != b'\x89PNG\r\n\x1a\n':
            errors.append(f'Invalid PNG header: {name}')
            continue
        size = struct.unpack('>II', head[16:24])
        if size != (2048, 2048):
            errors.append(f'Expected 2048 x 2048 pixels: {name}')
        image = bpy.data.images.load(str(path), check_existing=False)
        rgba = np.empty(len(image.pixels), dtype=np.float32)
        image.pixels.foreach_get(rgba)
        bpy.data.images.remove(image)
        if not rgba.size:
            errors.append(f'Could not decode pixels: {name}')
            continue
        rgba = rgba.reshape(-1, 4)
        alpha_min = float(rgba[:, 3].min())
        if alpha_min < .9999:
            errors.append(f'Nonopaque pixels: {name}')
        if name == 'exo_gloss' and not (
            np.array_equal(rgba[:, 0], rgba[:, 1]) and np.array_equal(rgba[:, 1], rgba[:, 2])
        ):
            errors.append('Gloss texture is not grayscale')
        results[name] = {
            'size': list(size), 'bit_depth': head[24], 'png_color_type': head[25],
            'alpha_min': alpha_min, 'node_color_space': [img.colorspace_settings.name for img in node_matches],
        }
    return results


def frame_fingerprint(obj):
    mesh = obj.data
    source = {
        'matrix': [list(row) for row in obj.matrix_world],
        'vertices': [list(vertex.co) for vertex in mesh.vertices],
        'faces': [list(face.vertices) for face in mesh.polygons],
        'weights': [
            sorted((obj.vertex_groups[g.group].name, g.weight) for g in vertex.groups)
            for vertex in mesh.vertices
        ],
    }
    return hashlib.sha256(json.dumps(source, separators=(',', ':')).encode()).hexdigest()


def structural(sets):
    rig = review.ARM
    errors = rig_errors(rig)
    data = {
        'blend': Path(bpy.data.filepath).name,
        'blend_sha256': hashlib.sha256(Path(bpy.data.filepath).read_bytes()).hexdigest(),
        'saved_pose_position': rig.data.pose_position,
        'bind_bones': len(rig.data.bones),
        'errors': errors, 'lods': {}, 'parts': {},
    }
    all_uvs = []
    for lod, objects in sets.items():
        uvs = []
        counts = Counter()
        for obj in objects:
            if obj.type != 'MESH':
                errors.append(f'Non-mesh in LOD{lod}: {obj.name}')
                continue
            prefix = 'EXO1_' if lod else 'EXO_'
            mesh = obj.data
            role = part_role(obj)
            armor = role == 'armor'
            if not obj.name.startswith(prefix):
                errors.append(f'Unexpected LOD{lod} object name: {obj.name}')
            if len(obj.modifiers) != 1 or obj.modifiers[0].type != 'ARMATURE' or obj.modifiers[0].object != rig:
                errors.append(f'Expected a single EFT_Bind armature modifier: {obj.name}')
            if [mat.name if mat else None for mat in mesh.materials] != ['exo_mat']:
                errors.append(f'Material slots differ from [exo_mat]: {obj.name}')
            if any(len(poly.vertices) > 4 for poly in mesh.polygons):
                errors.append(f'Face with more than 4 vertices: {obj.name}')
            if len(mesh.uv_layers) != 1:
                errors.append(f'Expected a single UV map: {obj.name}')
            mesh.calc_loop_triangles()
            if any(tri.area <= 1e-12 for tri in mesh.loop_triangles):
                errors.append(f'Degenerate mesh triangles: {obj.name}')
            if mesh.uv_layers.active:
                uv = mesh.uv_layers.active.uv
                uvs.extend([tuple(uv[i].vector) for i in tri.loops] for tri in mesh.loop_triangles)
            used = Counter()
            max_weights = 0
            max_weight_error = 0.
            invalid = 0
            for vertex in mesh.vertices:
                weights = {obj.vertex_groups[g.group].name: g.weight for g in vertex.groups if g.weight > 0}
                max_weights = max(max_weights, len(weights))
                error = abs(sum(weights.values()) - 1)
                max_weight_error = max(max_weight_error, error)
                used.update(weights.keys())
                invalid += int(
                    not 1 <= len(weights) <= 4 or error > 1e-5
                    or any(name not in rig.data.bones for name in weights)
                )
            if invalid:
                errors.append(f'{invalid} vertices with invalid skinning: {obj.name}')
            if armor:
                allowed = allowed_armor_bones(obj.name)
                if not allowed:
                    errors.append(f'Unrecognized armor zone for assignment check: {obj.name}')
                elif len(used) != 1 or not used.keys() <= allowed or max_weights != 1:
                    errors.append(f'Expected rigid armor assignment to {sorted(allowed)}: {obj.name}')
            triangles = len(mesh.loop_triangles)
            counts[role] += triangles
            data['parts'][obj.name] = {
                'triangles': triangles, 'bones': sorted(used), 'bone_vertex_counts': dict(used),
                'max_influences': max_weights, 'max_weight_sum_error': max_weight_error,
                'armor': armor, 'role': role, 'lod': lod,
            }
            if role == 'frame':
                data['parts'][obj.name]['frame_fingerprint'] = frame_fingerprint(obj)
        if not LEGACY and not counts['armor']:
            errors.append(f'LOD{lod} contains no identified armor')
        total = sum(counts.values())
        if total > LIMITS[lod]:
            errors.append(f'LOD{lod} triangle budget exceeded: {total:,}/{LIMITS[lod]:,}')
        data['lods'][f'LOD{lod}'] = {
            'triangles': total, 'armor_triangles': counts['armor'], 'frame_triangles': counts['frame'],
            'carrier_triangles': counts['carrier'],
            'limit': LIMITS[lod], 'uv': uv_stats(uvs) if uvs else {},
        }
        all_uvs.extend(uvs)
    data['uv_combined'] = uv_stats(all_uvs) if all_uvs else {}
    for name, stats in [
        ('both LODs', data['uv_combined']),
        *((lod, info['uv']) for lod, info in data['lods'].items()),
    ]:
        for metric in ('degenerate_uv_triangles', 'outside_unit_square', 'positive_overlap_pairs'):
            if stats.get(metric):
                errors.append(f'UV atlas {name}, {metric}: {stats[metric]:,}')
    data['textures'] = texture_audit(errors)
    return data


def mesh_tree(vertices, triangles):
    return BVHTree.FromPolygons(vertices, triangles, all_triangles=True)


def contact_depth(mesh, ids, other_tree):
    vertices, tris = mesh
    samples = [vertices[i] for i in {i for tri_id in ids for i in tris[tri_id]}]
    samples.extend(sum((vertices[i] for i in tris[tri_id]), vertices[0] * 0.) / 3 for tri_id in ids)
    depths = []
    for point in samples:
        hit, normal, _, distance = other_tree.find_nearest(point)
        if (point - hit).dot(normal) < -1e-6 and odd_ray_count(other_tree, point) >= 8:
            depths.append(distance)
    return mm(max(depths)) if depths else None


def odd_ray_count(tree, point):
    count = 0
    for direction in RAY_DIRECTIONS:
        origin = point
        intersections = 0
        while True:
            hit, _, _, _ = tree.ray_cast(origin, direction)
            if hit is None:
                break
            intersections += 1
            origin = hit + direction * .00001
        count += intersections % 2
    return count


def certify_upper_bound(points, faces, cloth_points, cloth_tris, tree):
    """Cover each armor facet with convex 30 mm neighborhoods of cloth triangles."""
    def issue(a,b,c,depth):
        center=(a+b+c)/3
        near,_,tri,d=tree.find_nearest(center)
        if d>.030:
            return {'distance_mm':mm(d),'world_m':list(center)}
        geometry=[cloth_points[k] for k in cloth_tris[tri]]
        if all((p-closest_point_on_tri(p,*geometry)).length<=.029999
               for p in (a,b,c)):
            return None
        if max((p-center).length for p in (a,b,c))+d<=.029999:
            return None
        if depth>=10:
            return {'unresolved':True,'world_m':list(center)}
        ab,bc,ca=(a+b)/2,(b+c)/2,(c+a)/2
        for child in ((a,ab,ca),(ab,b,bc),(ca,bc,c),(ab,bc,ca)):
            problem=issue(*child,depth+1)
            if problem:
                return problem
        return None
    problems=[]
    for i,(a,b,c) in enumerate(faces):
        result=issue(points[a],points[b],points[c],0)
        if result:
            problems.append({'triangle':i,**result})
    return problems


def evaluated_pose(objects, pose):
    review.set_pose(pose)
    deps = bpy.context.evaluated_depsgraph_get()
    clothing = {name: review._mesh(bpy.data.objects[name], deps) for name in REFS}
    vertices = []
    triangles = []
    for ref_vertices, ref_triangles in clothing.values():
        triangles.extend(tuple(i + len(vertices) for i in tri) for tri in ref_triangles)
        vertices.extend(ref_vertices)
    refs = {name: mesh_tree(*surface) for name, surface in clothing.items()}
    garment = Garment(vertices, triangles) if not LEGACY else None
    combined = garment.tree if garment else mesh_tree(vertices, triangles)
    parts = {}
    armor_trees = {}
    armor_meshes = {}
    for lod, items in objects.items():
        for obj in items:
            if obj.type != 'MESH':
                continue
            verts, tris = review._mesh(obj, deps)
            if not tris:
                continue
            tree = mesh_tree(verts, tris)
            role = part_role(obj)
            overlaps = {name: tree.overlap(ref) for name, ref in refs.items()}
            hits = {name: len(pairs) for name, pairs in overlaps.items()}
            part = {'surface_crossings': hits}
            parts[obj.name] = part
            if role != 'frame' and any(hits.values()):
                details = {}
                for name, pairs in overlaps.items():
                    if not pairs:
                        continue
                    vertex_ids = sorted({idx for tri, _ in pairs for idx in tris[tri]})
                    points = np.asarray([verts[idx] for idx in vertex_ids])
                    details[name] = {
                        'evaluated_vertex_indices': vertex_ids,
                        'world_min_m': points.min(axis=0).round(5).tolist(),
                        'world_max_m': points.max(axis=0).round(5).tolist(),
                    }
                part['surface_crossing_details'] = details
            if role == 'frame':
                continue
            if role == 'armor':
                armor_trees[obj.name] = (lod, tree)
                armor_meshes[obj.name] = (verts, tris)
            samples = list(verts)
            samples.extend((verts[a] + verts[b]) / 2 for a, b in edges_of(tris))
            samples.extend((verts[a] + verts[b] + verts[c]) / 3 for a, b, c in tris)
            nearest = [combined.find_nearest(p) for p in samples]
            distances = np.asarray([hit[3] for hit in nearest])
            signed = np.asarray([(p - hit[0]).dot(hit[1]) for p, hit in zip(samples, nearest)])
            negative_ids = np.where(signed < -.0005)[0]
            enclosed = 0
            for sample_id in negative_ids:
                nearest_tri = nearest[sample_id][2]
                ref_name = REFS[0] if nearest_tri < len(clothing[REFS[0]][1]) else REFS[1]
                enclosed += odd_ray_count(refs[ref_name], samples[sample_id]) >= 8
            part.update({
                'surface_samples': len(samples),
                'sample_distance_mm_min_median_p95_max': [mm(d) for d in np.quantile(distances, (0, .5, .95, 1))],
                'sample_percent_5_to_30_mm': round(100 * float(np.mean(
                    (distances >= TARGET[0]) & (distances <= TARGET[1])
                )), 2),
                'sample_percent_below_5_mm': round(100 * float(np.mean(distances < TARGET[0])), 2),
                'sample_percent_above_30_mm': round(100 * float(np.mean(distances > TARGET[1])), 2),
                'nearest_normal_negative_samples': len(negative_ids),
                'enclosure_suspect_samples': enclosed,
                'lowest_local_normal_offset_mm': mm(signed.min()),
            })
            if garment and role == 'armor':
                part['outside_30mm_or_unresolved']=certify_upper_bound(
                    verts,tris,vertices,triangles,combined)
                points = np.asarray(verts)
                gap = 0. if any(hits.values()) else min(
                    (gap for _, _, gap in Pair(
                        garment, points, tris, GAP_SEARCH_REACH
                    ).features(points, GAP_SEARCH_REACH)), default=None,
                )
                part['closest_gap_mm_within_31'] = mm(gap) if gap is not None else None
    contacts = []
    for (name_a, (lod_a, tree_a)), (name_b, (lod_b, tree_b)) in combinations(armor_trees.items(), 2):
        if lod_a != lod_b:
            continue
        hits = tree_a.overlap(tree_b)
        if hits:
            sides = (set(), set())
            for a, b in hits:
                sides[0].add(a)
                sides[1].add(b)
            depths = [
                contact_depth(armor_meshes[name_a], sides[0], tree_b),
                contact_depth(armor_meshes[name_b], sides[1], tree_a),
            ]
            contacts.append({
                'lod': lod_a, 'parts': [name_a, name_b], 'surface_crossings': len(hits),
                'triangles_in_contact': [len(side) for side in sides],
                'sampled_depth_mm_by_part': depths,
            })
    return {
        'parts': parts, 'plate_contacts': contacts,
        'clothing_topology': {name: review._topology(mesh[1]) for name, mesh in clothing.items()},
    }


def crossing_total(part):
    return sum(part['surface_crossings'].values())


def compare_frame(data):
    baseline_file = ROOT / 'armor_qa_baseline.json'
    if not baseline_file.is_file():
        return []
    baseline = json.loads(baseline_file.read_text(encoding='utf-8'))
    before = {name: part['frame_fingerprint'] for name, part in baseline['parts'].items() if not part['armor']}
    after = {name: part['frame_fingerprint'] for name, part in data['parts'].items() if part['role'] == 'frame'}
    differences = [name for name in sorted(before.keys() | after.keys()) if before.get(name) != after.get(name)]
    if differences:
        lines = ['- С исходной рамой расходятся геометрия, трансформации или веса объектов '
                 + ', '.join(f'`{name}`' for name in differences) + '.']
    else:
        lines = ['- Геометрия, трансформации и веса рамы совпадают с исходной рамой `exo_t3.blend`.']
    changes = []
    for pose, result in data['poses'].items():
        source_parts = baseline['poses'][pose]['parts']
        for name, part in result['parts'].items():
            if name in after and name in source_parts:
                old = source_parts[name]['surface_crossings']
                new = part['surface_crossings']
                if old != new:
                    changes.append((pose, name, sum(old.values()), sum(new.values())))
    if changes:
        lines.append('- Число пересечений рамы с одеждой изменилось по сравнению с исходной рамой: ' + ', '.join(
            f'{pose}, `{name}` ({old} → {new})' for pose, name, old, new in changes
        ) + '.')
    else:
        lines.append('- Число пересечений рамы с одеждой совпадает с исходной рамой во всех шести позах.')
    return lines


def neck_turns(objects):
    """Exercise the neckline actually influenced by the game's neck bone."""
    measured={}
    for degrees in range(-75,76,5):
        review.set_pose('rest')
        review._rotate('Base HumanNeck',Vector((0,0,1)),degrees)
        deps=bpy.context.evaluated_depsgraph_get()
        top=mesh_tree(*review._mesh(bpy.data.objects['REF_top'],deps))
        results=[]
        for lod,parts in objects.items():
            hits=0
            closest=1.
            for obj in parts:
                if 'armorGorget' not in obj.name and 'gorgetBacking' not in obj.name:
                    continue
                points,tris=review._mesh(obj,deps)
                shell=mesh_tree(points,tris)
                hits+=len(shell.overlap(top))
                closest=min(closest,min(top.find_nearest(p)[3] for p in points))
            results.append({'lod':lod,'crossings':hits,'min_vertex_gap_mm':mm(closest)})
        measured[str(degrees)]=results
    return measured


def summarize(data):
    parts = data['parts']
    lines = [
        '# Бронированный экзоскелет T3',
        '',
        f"Проверка `{data['blend']}` в Blender {bpy.app.version_string} в фоновом режиме. "
        f"Положение сохранённого рига — `{data['saved_pose_position']}`. "
        f"Проверено костей по `base_scene.blend` — {data['bind_bones']}.",
        '',
        'В каждом LOD установлены 24 жёсткие пластины. Нагрудник, спинная кокетка и поясничная '
        'пластина защищают корпус. Боковые секции охватывают рёбра спереди и сзади от опущенного рукава. '
        'Четыре сегмента горжета сидят на общей подложке. Верхняя и нижняя секции каждого бедра '
        'оставляют открытым ремень рамы. Узлы на спине, локтях, коленях и лодыжках сохранены.',
        '',
        '[Модель](exo_t3a.blend) · [Вид в три четверти](previews_t3a/three_quarter.png) · '
        '[Вид со спины](previews_t3a/back.png) · [Сравнение уровней](previews_tiers_v2.png)',
        '',
        '## Геометрия и атлас',
        '',
        '| LOD | Треугольники рамы | Треугольники пластин | Треугольники подложек и креплений | Всего | Лимит | Пересечения UV |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: |',
    ]
    for name, lod in data['lods'].items():
        lines.append(
            f"| {name} | {lod['frame_triangles']:,} | {lod['armor_triangles']:,} | "
            f"{lod['carrier_triangles']:,} | {lod['triangles']:,} | {lod['limit']:,} | "
            f"{lod['uv'].get('positive_overlap_pairs', 0):,} |"
        )
    lines += [
        '',
        f"Пар UV-треугольников с ненулевой площадью пересечения в общем атласе — "
        f"{data['uv_combined'].get('positive_overlap_pairs', 0):,}. Общие рёбра соседних треугольников допускаются.",
        '',
        'Под исходную развёртку рамы выделен квадрат 1216 × 1216 пикселей общего атласа 2048 × 2048. '
        'На оставшейся площади размещены пластины и крепления обоих LOD. '
        'Карты содержат цвет, нормали OpenGL (+Y) и глянец. [Текстуры](textures_t3a/)',
    ]
    if data['errors']:
        lines += ['', 'Замечания автоматической проверки', ''] + [f'- {error}' for error in data['errors']]
    else:
        lines += [
            '',
            'Проверены параметры исходного рига, жёсткая привязка пластин к заданным костям, '
            'нормализация весов, топология, единый материал `exo_mat`, относительные пути к картам, '
            'размер PNG 2048 × 2048, непрозрачность карт и монохромность карты глянца.',
        ]
    lines += [
        '',
        '## Пересечения в шести позах',
        '',
        'Считались пары пересекающихся треугольников после деформации ригом. В двух столбцах '
        '«Пластина с пластиной» первое число означает число пар объектов, в скобках указано '
        'число пар треугольников. На счётчик влияет плотность сетки. У одежды есть открытые края, '
        'поэтому подсчёт пересечений поверхностей не выявляет целиком погружённые детали. '
        'В `armor_qa.json` есть измерения по каждому объекту, включая локальные смещения '
        'от поверхности одежды по нормали. Для точек с отрицательным смещением проверены 10 лучей. '
        'Нечётное число пересечений минимум по 8 направлениям указывает на вероятное попадание '
        'внутрь одежды. Глубина контактов пластин оценена по вершинам и центрам пересекающихся '
        'треугольников, которые также прошли лучевую проверку.',
        '',
        '| Поза | LOD0 броня / одежда | LOD0 рама / одежда | LOD0 крепления / одежда | LOD0 пластина с пластиной | '
        'LOD1 броня / одежда | LOD1 рама / одежда | LOD1 крепления / одежда | LOD1 пластина с пластиной |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |',
    ]
    pose_labels = {
        'rest': 'Исходная', 'crouch': 'Присед (таз 60°, колени 95°)',
        'knee120': 'Колени 120°', 'elbow110': 'Локти 110°',
        'down60': 'Руки опущены на 60°', 'twist30': 'Поворот корпуса 30°',
    }
    for name, pose in data['poses'].items():
        columns = []
        for lod in (0, 1):
            counts = Counter()
            for obj, part in pose['parts'].items():
                if parts[obj]['lod'] != lod:
                    continue
                counts[parts[obj]['role']] += crossing_total(part)
            contacts = [contact for contact in pose['plate_contacts'] if contact['lod'] == lod]
            total = sum(contact['surface_crossings'] for contact in contacts)
            columns.extend([str(counts[name]) for name in ('armor', 'frame', 'carrier')])
            columns.append(f'{len(contacts)} ({total})')
        lines.append(f"| {pose_labels[name]} | {' | '.join(columns)} |")
    lines += [
        '',
        f"Дополнительно шея повёрнута от −75° до +75° с шагом 5°. Суммарное число пересечений "
        f"горжета и его подложки с воротом куртки для обоих LOD — "
        f"{sum(item['crossings'] for angle in data['neck_yaw'].values() for item in angle)}. "
        'Для проверки зазора до подбородка потребуется игровая модель головы. '
        'В таблице измерено взаимодействие с `REF_top` и `REF_pants`. '
        'Подложки и крепления включены в проверку одежды. В столбцах контактов пластин '
        'учитываются пары жёстких защитных пластин.',
        '',
        '## Диапазон расстояний до одежды по позам',
        '',
        '| Поза | LOD0 минимум, мм | LOD0 макс. выборки, мм | LOD1 минимум, мм | LOD1 макс. выборки, мм |',
        '| --- | ---: | ---: | ---: | ---: |',
    ]
    for pose_name, pose in data['poses'].items():
        columns = []
        for lod in (0, 1):
            armor = [
                (name, part) for name, part in pose['parts'].items()
                if parts[name]['role'] == 'armor' and parts[name]['lod'] == lod
            ]
            gaps = [(part['closest_gap_mm_within_31'], name) for name, part in armor
                    if part['closest_gap_mm_within_31'] is not None]
            defaults = (None, '')
            minimum, min_name = min(gaps, default=defaults)
            maximum, max_name = max(
                ((part['sample_distance_mm_min_median_p95_max'][3], name) for name, part in armor),
                default=defaults,
            )
            columns.append('>31' if minimum is None else f'{minimum:.2f} (`{min_name}`)')
            columns.append('—' if maximum is None else f'{maximum:.2f} (`{max_name}`)')
        lines.append(f"| {pose_labels[pose_name]} | {' | '.join(columns)} |")
    unresolved=sum(len(p.get('outside_30mm_or_unresolved',[]))
                   for pose in data['poses'].values() for p in pose['parts'].values())
    lines += [
        '',
        'Минимум берётся по ближайшим геометрическим элементам двух поверхностей в радиусе 31 мм, '
        'без учёта знака расстояния. Пересечение поверхностей даёт 0. Максимум — по конечной выборке '
        'точек на броне, поэтому он может быть ниже фактического максимума по всей поверхности.',
        '',
        'Верхняя граница 30 мм дополнительно проверена по всей площади каждой грани. '
        'Если три вершины входят в выпуклую 30-миллиметровую окрестность одного треугольника одежды, '
        'туда входит и вся грань. Иначе проверка ограничивает расстояние через радиус грани '
        'или повторяется на четырёх меньших треугольниках. '
        f'Граней с превышением или неподтверждённой границей во всех позах обоих LOD — {unresolved}.',
        '',
        '## Зазор между бронёй и одеждой в исходной позе',
        '',
        'Целевой зазор — 5–30 мм. Для минимального расстояния проверены пары «вершина — грань» '
        'и «ребро — ребро» в радиусе 31 мм. Ноль означает пересечение поверхностей. '
        'Статистика выборки рассчитана по вершинам, серединам рёбер и центрам треугольников всей детали, '
        'включая наружную поверхность пластин, окантовку и крепления. '
        'Доля выше 30 мм включает наружные поверхности и не определяет толщину зазора под пластиной.',
        '',
        '| LOD | Деталь | Мин. зазор, мм | Медиана, мм | 95-й процентиль, мм | Макс. выборки, мм | <5 мм | 5–30 мм | >30 мм |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |',
    ]
    for name, info in data['poses']['rest']['parts'].items():
        if not parts[name]['armor']:
            continue
        gap = info['closest_gap_mm_within_31']
        _, median, p95, maximum = info['sample_distance_mm_min_median_p95_max']
        gap_text = '>31' if gap is None else f'{gap:.2f}'
        lines.append(
            f"| {parts[name]['lod']} | `{name}` | {gap_text} | {median:.2f} | {p95:.2f} | {maximum:.2f} | "
            f"{info['sample_percent_below_5_mm']:.1f}% | {info['sample_percent_5_to_30_mm']:.1f}% | "
            f"{info['sample_percent_above_30_mm']:.1f}% |"
        )
    lines += ['', '## Замечания по посадке', '']
    lines.extend(compare_frame(data))
    fit_findings = []
    for pose_name, pose in data['poses'].items():
        for lod in (0, 1):
            for role, label in (('armor', 'пластин'), ('carrier', 'креплений')):
                hits = [
                    (name, crossing_total(info))
                    for name, info in pose['parts'].items()
                    if parts[name]['role'] == role and parts[name]['lod'] == lod and crossing_total(info)
                ]
                if hits:
                    labels = ', '.join(f'`{part}` ({count})' for part, count in hits)
                    fit_findings.append(
                        f'- {pose_labels[pose_name]}, LOD{lod}. Пересечения {label} с одеждой — {labels}.'
                    )
            for name, info in pose['parts'].items():
                if parts[name]['lod'] != lod or not info.get('enclosure_suspect_samples'):
                    continue
                suspect = info['enclosure_suspect_samples']
                samples = info['surface_samples']
                offset = info['lowest_local_normal_offset_mm']
                fit_findings.append(
                    f'- {pose_labels[pose_name]}, LOD{lod}. У `{name}` '
                    f'{suspect} из {samples} точек вероятно попадают внутрь одежды по лучевой проверке. '
                    f'Минимальная проекция на локальную нормаль одежды — {offset:.2f} мм.'
                )
            for contact in pose['plate_contacts']:
                if contact['lod'] != lod:
                    continue
                a, b = contact['parts']
                depths = [d for d in contact['sampled_depth_mm_by_part'] if d is not None]
                depth_text = (f' Наибольшая глубина среди точек, прошедших лучевую проверку, — {max(depths):.2f} мм.'
                              if depths else ' В выборке нет внутренних точек, прошедших лучевую проверку.')
                fit_findings.append(
                    f"- {pose_labels[pose_name]}, LOD{lod}. Между `{a}` и `{b}` пересеклись "
                    f"{contact['surface_crossings']} пар треугольников.{depth_text}"
                )
    lines.extend(fit_findings or ['- В шести позах пересечений между бронёй и одеждой или между пластинами не обнаружено.'])
    fit_outliers = [
        name for name, part in data['poses']['rest']['parts'].items()
        if parts[name]['armor'] and (
            part['closest_gap_mm_within_31'] is None
            or not 5 <= part['closest_gap_mm_within_31'] <= 30
        )
    ]
    if fit_outliers:
        lines.append('- Минимальный зазор в исходной позе выходит за пределы 5–30 мм у деталей '
                     + ', '.join(f'`{name}`' for name in fit_outliers) + '.')
    lines += [
        '',
        '## Треугольники и кости по объектам',
        '',
        '| Объект | LOD | Треугольники | Влияний на вершину, максимум | Кости |',
        '| --- | --- | ---: | ---: | --- |',
    ]
    order = {'armor': 0, 'carrier': 1, 'frame': 2}
    for name, info in sorted(parts.items(), key=lambda row: (order[row[1]['role']], row[1]['lod'], row[0])):
        bones = ', '.join(f"`{b.removeprefix('Base Human')}`" for b in info['bones'])
        lines.append(
            f"| `{name}` | {info['lod']} | {info['triangles']:,} | {info['max_influences']} | {bones} |"
        )
    lines += [
        '', 'В таблице опущен общий префикс имён костей `Base Human`.',
        '',
        '## Сборка, проверка и рендер',
        '',
        '```powershell',
        r"$blender = 'C:\Program Files\Blender Foundation\Blender 5.3\blender.exe'",
        r'& $blender --factory-startup -b .\exo_t3.blend --python-exit-code 1 --python .\build_t3a.py',
        r'& $blender --factory-startup -b .\exo_t3.blend --python-exit-code 1 --python .\armor_check.py -- --baseline',
        r'& $blender --factory-startup -b .\exo_t3a.blend --python-exit-code 1 --python .\armor_check.py',
        r'& $blender --factory-startup -b .\exo_t3a.blend --python-exit-code 1 --python .\armor_previews.py -- all',
        r'& $blender --factory-startup -b --python-exit-code 1 --python .\armor_previews.py -- compare',
        '```',
        '',
    ]
    return '\n'.join(lines)


def make_visible(collection):
    collection.hide_viewport = False
    def visit(layer):
        if layer.collection == collection:
            layer.exclude = False
            layer.hide_viewport = False
        for child in layer.children:
            visit(child)
    visit(bpy.context.view_layer.layer_collection)
    for obj in list(collection.all_objects):
        obj.hide_viewport = False
        obj.hide_set(False)


def main():
    expected = 'exo_t3.blend' if LEGACY else 'exo_t3a.blend'
    if Path(bpy.data.filepath).resolve() != ROOT / expected:
        raise SystemExit(f'Run against {expected} inside {ROOT}.')
    objects = {}
    for lod in (0, 1):
        collection = bpy.data.collections.get(f'EXO_LOD{lod}')
        if collection is None:
            raise RuntimeError(f'Missing EXO_LOD{lod} collection')
        make_visible(collection)
        objects[lod] = sorted(collection.all_objects, key=lambda obj: obj.name)
    for name in (*REFS, 'EFT_Bind'):
        obj = bpy.data.objects[name]
        obj.hide_viewport = False
        obj.hide_set(False)
    bpy.context.view_layer.update()
    data = structural(objects)
    data['poses'] = {}
    try:
        for pose in review.POSES:
            data['poses'][pose] = evaluated_pose(objects, pose)
            p = data['poses'][pose]
            totals = Counter()
            suspects = Counter()
            for name, part in p['parts'].items():
                role = data['parts'][name]['role']
                lod = data['parts'][name]['lod']
                totals[role, lod] += crossing_total(part)
                suspects[role, lod] += part.get('enclosure_suspect_samples', 0)
            print(
                f'QA {pose}: armor/clothing LOD0={totals["armor", 0]} LOD1={totals["armor", 1]}, '
                f'carrier/clothing LOD0={totals["carrier", 0]} LOD1={totals["carrier", 1]}, '
                f'plate pairs={len(p["plate_contacts"])}, suspect samples={sum(suspects.values())}', flush=True,
            )
        if not LEGACY:
            data['neck_yaw']=neck_turns(objects)
    finally:
        review.restore_pose()
    output = ROOT / ('armor_qa_baseline.json' if LEGACY else 'armor_qa.json')
    output.write_text(json.dumps(data, indent=2), encoding='utf-8')
    if not LEGACY:
        (ROOT / 'REPORT_T3A.md').write_text(summarize(data), encoding='utf-8')
    print('STRUCTURAL ERRORS', data['errors'], flush=True)
    if not LEGACY:
        failures=list(data['errors'])
        for pose,info in data['poses'].items():
            if info['plate_contacts']:
                failures.append(f'{pose}: plate contact')
            for name,part in info['parts'].items():
                if crossing_total(part) or part.get('enclosure_suspect_samples'):
                    failures.append(f'{pose}: garment contact on {name}')
                if data['parts'][name]['armor']:
                    lower=part['closest_gap_mm_within_31']
                    if lower is None or lower<5 or part['outside_30mm_or_unresolved']:
                        failures.append(f'{pose}: clearance on {name}')
        if any(t['crossings'] for by_lod in data['neck_yaw'].values() for t in by_lod):
            failures.append('Gorget contacts the jacket in neck rotation')
        if failures:
            raise RuntimeError('; '.join(failures))


if __name__ == '__main__':
    main()
