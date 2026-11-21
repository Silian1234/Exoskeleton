"""Generate separate tier-specific, non-overlapping exoskeleton UV atlases.

Call apply_atlas(lod0, lod1, tier) after modelling, with lists of mesh objects.
Polygon material_index selects the intended finish (0..7). The function replaces
all material slots and writes texture PNGs next to the eventual blend file.
"""
import os
import math
import bpy
import numpy as np

SIZE = 2048
# Albedo in display-referred colour: gunmetal, composite, olive, polished,
# tan, webbing, safety amber and dark stainless fasteners.
COLOURS = np.array([
    (0.25, 0.275, 0.27), (0.085, 0.095, 0.09),
    (0.225, 0.245, 0.17), (0.49, 0.51, 0.49),
    (0.40, 0.35, 0.26), (0.16, 0.155, 0.13),
    (0.71, 0.43, 0.09), (0.30, 0.32, 0.31),
], dtype=np.float32)
GLOSS = np.array([0.39, 0.20, 0.23, 0.78, 0.19, 0.13, 0.34, 0.57], dtype=np.float32)


# Geometry style slots: frame metal, composite, olive/charcoal shell,
# polished rod, tan/dark shell, webbing, accent, fasteners.
PALETTES = {
    2: np.array([(0.19,0.21,0.19), (0.075,0.085,0.073),
                 (0.27,0.30,0.19), (0.52,0.54,0.52),
                 (0.43,0.37,0.25), (0.16,0.15,0.11),
                 (0.72,0.43,0.09), (0.28,0.30,0.28)], dtype=np.float32),
    3: np.array([(0.13,0.15,0.16), (0.035,0.045,0.05),
                 (0.105,0.125,0.135), (0.49,0.53,0.55),
                 (0.18,0.21,0.22), (0.075,0.085,0.085),
                 (0.055,0.53,0.60), (0.26,0.29,0.30)], dtype=np.float32),
}
GLOSSES = {
    2: np.array([.40,.19,.24,.82,.20,.13,.35,.57],dtype=np.float32),
    3: np.array([.48,.23,.34,.82,.36,.15,.48,.62],dtype=np.float32),
}


_GLYPHS = {
    'E': (31,16,16,30,16,16,31),
    'X': (17,17,10,4,10,17,17),
    'O': (14,17,17,17,17,17,14),
    '2': (14,17,1,2,4,8,31),
    '0': (14,17,19,21,25,17,14),
    '3': (30,1,1,14,1,1,30),
}


def _type_mask(u, v, label):
    # Seven rows, five columns and a one-column gap, with no font dependency.
    cols = len(label)*6-1
    gx = np.floor(u*cols).astype(np.int32)
    gy = np.floor((1-v)*7).astype(np.int32)
    result = np.zeros(np.broadcast_shapes(gx.shape, gy.shape), dtype=bool)
    for k, char in enumerate(label):
        for row, bits in enumerate(_GLYPHS[char]):
            for col in range(5):
                if bits & (1 << (4-col)):
                    result |= (gx == k*6+col) & (gy == row)
    return result & (u >= 0) & (u < 1) & (v >= 0) & (v < 1)


def _fill_triangle(style, detail, markings, points, index, bounds, world=None, target=None):
    """Rasterize one UV triangle into the style map at pixel centres."""
    p = np.asarray(points, dtype=np.float64) * (SIZE - 1)
    x0 = max(0, int(np.floor(p[:, 0].min())))
    x1 = min(SIZE - 1, int(np.ceil(p[:, 0].max())))
    y0 = max(0, int(np.floor(p[:, 1].min())))
    y1 = min(SIZE - 1, int(np.ceil(p[:, 1].max())))
    if x1 < x0 or y1 < y0:
        return
    x = np.arange(x0, x1 + 1, dtype=np.float64)[None, :] + 0.5
    y = np.arange(y0, y1 + 1, dtype=np.float64)[:, None] + 0.5
    a, b, c = p
    e0 = (b[0]-a[0])*(y-a[1]) - (b[1]-a[1])*(x-a[0])
    e1 = (c[0]-b[0])*(y-b[1]) - (c[1]-b[1])*(x-b[0])
    e2 = (a[0]-c[0])*(y-c[1]) - (a[1]-c[1])*(x-c[0])
    inside = ((e0 >= -1e-7) & (e1 >= -1e-7) & (e2 >= -1e-7)) | \
             ((e0 <= 1e-7) & (e1 <= 1e-7) & (e2 <= 1e-7))
    view = style[y0:y1+1, x0:x1+1]
    view[inside] = index
    if target is not None:
        # UV barycentric coordinates interpolate the actual world position at
        # each texel, avoiding any assumption about island orientation.
        denom = ((b[1]-c[1])*(a[0]-c[0]) + (c[0]-b[0])*(a[1]-c[1]))
        if abs(denom) > 1e-8:
            wa = ((b[1]-c[1])*(x-c[0]) + (c[0]-b[0])*(y-c[1]))/denom
            wb = ((c[1]-a[1])*(x-c[0]) + (a[0]-c[0])*(y-c[1]))/denom
            wc = 1-wa-wb
            h = wa*world[0][0] + wb*world[1][0] + wc*world[2][0]
            z = wa*world[0][2] + wb*world[1][2] + wc*world[2][2]
            mv = markings[y0:y1+1,x0:x1+1]
            if target == 'cells':
                # Both removable lids face rearward. Register the print across
                # their UV seams, upright when looking at the rear of the rig.
                cx = .058 if world[0][0] > 0 else -.058
                u = (.022 + cx-h)/.044
                text = _type_mask(u, (z-1.323)/.017, '02' if cx > 0 else 'EXO')
                ticks = (u >= 0) & (u < .95) & (z > 1.226) & (z < 1.230)
                ticks &= np.mod(u + 13*(z-1.226), .23) < .145
                mv[inside & text] = 1
                mv[inside & ticks] = 2
            elif target == 'core':
                # The centre is occupied by the core window and the top and
                # bottom by fins. Reserve one clear service field to its left.
                u = (.070-h)/.040
                text = _type_mask(u, (z-1.307)/.014, '03')
                ticks = (u >= .04) & (u < .86) & (z > 1.297) & (z < 1.300)
                mv[inside & text] = 1
                mv[inside & ticks] = 2
    # Large plate faces receive a shallow inset panel line and four recessed
    # circular fasteners. Dimensions are measured in texture pixels so the
    # details remain visible after mipmapping. Small faces stay clean.
    bx0, by0, bx1, by1 = bounds
    width, height = bx1-bx0, by1-by0
    if index in (0, 1, 2, 4) and width >= 32 and height >= 32:
        u = (x-bx0)/width
        v = (y-by0)/height
        inset = max(3.0, min(8.0, min(width, height)*0.065))
        dx = np.minimum(np.abs(x-(bx0+inset)), np.abs(x-(bx1-inset)))
        dy = np.minimum(np.abs(y-(by0+inset)), np.abs(y-(by1-inset)))
        line = (((dx < 0.8) & (v > inset/height) & (v < 1-inset/height)) |
                ((dy < 0.8) & (u > inset/width) & (u < 1-inset/width)))
        dv = detail[y0:y1+1, x0:x1+1]
        dv[inside & line] = -0.075
        if width >= 56 and height >= 56:
            radius = max(2.5, min(4.0, min(width, height)*0.035))
            for fx, fy in ((0.14,0.14),(0.86,0.14),(0.14,0.86),(0.86,0.86)):
                distance = np.sqrt((x-(bx0+fx*width))**2 + (y-(by0+fy*height))**2)
                rim = inside & (distance < radius+1.0) & (distance >= radius-0.5)
                recess = inside & (distance < radius-0.5)
                dv[rim] = 0.065
                dv[recess] = -0.14
                slot = recess & (np.abs(y-(by0+fy*height)) < 0.6)
                dv[slot] = -0.22


def _expand_styles(style, steps):
    """Extrude island colours into padding to reduce mipmap seams."""
    result = style.copy()
    for _ in range(steps):
        empty = result < 0
        previous = result.copy()
        for axis, shift in ((0, 1), (0, -1), (1, 1), (1, -1)):
            neighbour = np.roll(previous, shift, axis=axis)
            if axis == 0:
                neighbour[0 if shift == 1 else -1, :] = -1
            else:
                neighbour[:, 0 if shift == 1 else -1] = -1
            use = empty & (neighbour >= 0)
            result[use] = neighbour[use]
            empty[use] = False
    return result


def _save_rgba(name, pixels, directory, non_color=False):
    image = bpy.data.images.get(name)
    if image:
        bpy.data.images.remove(image)
    image = bpy.data.images.new(name, width=SIZE, height=SIZE, alpha=True)
    if non_color:
        image.colorspace_settings.name = 'Non-Color'
    image.pixels.foreach_set(np.ascontiguousarray(pixels, dtype=np.float32).ravel())
    image.file_format = 'PNG'
    image.filepath_raw = os.path.join(directory, name + '.png')
    image.save()
    image.filepath = '//' + os.path.basename(directory) + '/' + name + '.png'
    return image


def _split_folded_faces(objects):
    """Isolate the few local folds that a single smart-projection chart can contain."""
    from validate import uv_stats
    owners=[]; triangles=[]
    for obj in objects:
        mesh=obj.data
        mesh.calc_loop_triangles()
        layer=mesh.uv_layers.active.data
        for tri in mesh.loop_triangles:
            owners.append((obj,tri.polygon_index))
            triangles.append([tuple(layer[i].uv) for i in tri.loops])
    pairs=[]
    uv_stats(triangles,pairs)
    if not pairs:
        return
    # One isolated chart per involved polygon. A narrow reserved strip gives
    # these small facets independent padding and preserves every other island.
    faces=sorted({owners[i] for pair in pairs for i in pair}, key=lambda p:(p[0].name,p[1]))
    strip=.042
    gap=2.0/SIZE
    for obj in objects:
        layer=obj.data.uv_layers.active.data
        for loop in layer:
            loop.uv.y*=1-strip
    slot=1/len(faces)
    for k,(obj,index) in enumerate(faces):
        mesh=obj.data;face=mesh.polygons[index]; layer=mesh.uv_layers.active.data
        pts=[mesh.vertices[j].co for j in face.vertices]
        width=(pts[1]-pts[0]).length
        height=face.area/max(1e-9,width)
        u=min(slot-2*gap,(strip-2*gap)*width/max(height,1e-9))
        v=min(strip-2*gap,(slot-2*gap)*height/max(width,1e-9))
        x=k*slot+gap; y=1-strip+gap
        canonical=((0,0),(1,0),(1,1),(0,1))
        for loop_id,(a,b) in zip(face.loop_indices,canonical):
            layer[loop_id].uv=(x+a*u,y+b*v)
    print('Separated projected folds into',len(faces),'independent facet charts.')


def apply_atlas(lod0, lod1, tier):
    global COLOURS, GLOSS
    if tier not in (2, 3):
        raise ValueError("tier must be 2 or 3")
    COLOURS = PALETTES[tier]
    GLOSS = GLOSSES[tier]
    objects = list(lod0) + list(lod1)
    if not objects or any(o.type != 'MESH' for o in objects):
        raise ValueError('apply_atlas requires nonempty lists of mesh objects')
    # Smart project in multi-object edit mode packs all islands, including both
    # LODs, together. Original material indices survive until rasterization.
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.hide_set(False)
        obj.select_set(True)
        if not obj.data.uv_layers:
            obj.data.uv_layers.new(name='EXO_Atlas')
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.00045,
                             area_weight=0.0, correct_aspect=True, scale_to_bounds=True)
    bpy.ops.object.mode_set(mode='OBJECT')

    _split_folded_faces(objects)
    style = np.full((SIZE, SIZE), -1, dtype=np.int8)
    detail = np.zeros((SIZE, SIZE), dtype=np.float32)
    markings = np.zeros((SIZE, SIZE), dtype=np.uint8)
    for obj in objects:
        mesh = obj.data
        uv = mesh.uv_layers.active.data
        mesh.calc_loop_triangles()
        for tri in mesh.loop_triangles:
            material = int(mesh.polygons[tri.polygon_index].material_index)
            material = max(0, min(7, material))
            face_uv = [uv[i].uv[:] for i in mesh.polygons[tri.polygon_index].loop_indices]
            coords = np.asarray(face_uv) * (SIZE - 1)
            bounds = (coords[:,0].min(), coords[:,1].min(), coords[:,0].max(), coords[:,1].max())
            poly = mesh.polygons[tri.polygon_index]
            world = [obj.matrix_world @ mesh.vertices[mesh.loops[i].vertex_index].co for i in tri.loops]
            center = obj.matrix_world @ poly.center
            normal = (obj.matrix_world.to_3x3() @ poly.normal).normalized()
            target = None
            if 'powerModules' in obj.name and normal.y > .88:
                if tier == 2 and material == 2 and abs(center.y-.235) < .002:
                    target = 'cells'
                elif tier == 3 and material == 0 and abs(center.y-.236) < .002:
                    target = 'core'
            _fill_triangle(style, detail, markings, [uv[i].uv[:] for i in tri.loops], material, bounds, world, target)
    mask = style >= 0
    if not mask.any():
        raise RuntimeError('No UV pixels were rasterized')
    # A narrow, restrained perimeter abrasion reads as worn manufactured edges.
    eroded = mask.copy()
    for axis, shift in ((0,1),(0,-1),(1,1),(1,-1)):
        eroded &= np.roll(mask, shift, axis=axis)
    edge = mask & ~eroded
    expanded = _expand_styles(style, 1)
    indices = np.maximum(expanded, 0)
    rng = np.random.default_rng(71003)
    noise = rng.normal(0.0, 0.009, (SIZE, SIZE)).astype(np.float32)
    fine = rng.normal(0.0, 0.003, (SIZE, SIZE)).astype(np.float32)
    rgba = np.empty((SIZE, SIZE, 4), dtype=np.float32)
    rgba[:, :, :3] = np.clip(COLOURS[indices] + noise[:, :, None] + edge[:, :, None]*0.045 + detail[:, :, None], 0, 1)
    # Webbing has a low-contrast woven grid; exposed metal gets fine parallel
    # machining grain. These are restrained at full resolution.
    rows = np.arange(SIZE, dtype=np.float32)[:, None]
    cols = np.arange(SIZE, dtype=np.float32)[None, :]
    weave = (np.sin(cols*math.pi/2)*np.sin(rows*math.pi/2))*0.012
    grain = np.sin(cols*math.pi*0.8)*0.008
    rgba[:, :, :3] = np.clip(rgba[:, :, :3] + ((indices == 5)*weave + (indices == 3)*grain)[:, :, None], 0, 1)
    rgba[markings == 1, :3] = (0.65, 0.63, 0.52)
    rgba[markings == 2, :3] = (0.72, 0.36, 0.055) if tier == 2 else (0.08, 0.72, 0.78)
    rgba[:, :, 3] = 1.0
    directory = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'textures_t' + str(tier))
    os.makedirs(directory, exist_ok=True)
    dif = _save_rgba('exo_dif', rgba, directory)
    # Tangent-space OpenGL (+Y) normals from the baked height relief.
    dx = (np.roll(detail, -1, axis=1) - np.roll(detail, 1, axis=1))*0.85
    dy = (np.roll(detail, -1, axis=0) - np.roll(detail, 1, axis=0))*0.85
    rgba[:, :, 0] = np.clip(0.5 - dx + fine, 0, 1)
    rgba[:, :, 1] = np.clip(0.5 - dy + np.roll(fine, 1, axis=0), 0, 1)
    rgba[:, :, 2] = np.sqrt(np.maximum(0, 1-(2*dx)**2-(2*dy)**2))*0.5 + 0.5
    nrm = _save_rgba('exo_nrm', rgba, directory, non_color=True)
    gloss = np.clip(GLOSS[indices] + noise*0.5 + edge*0.05, 0, 1)
    rgba[:, :, 0] = gloss
    rgba[:, :, 1] = gloss
    rgba[:, :, 2] = gloss
    spec = _save_rgba('exo_gloss', rgba, directory, non_color=True)
    nrm.colorspace_settings.name = 'Non-Color'
    spec.colorspace_settings.name = 'Non-Color'

    material = bpy.data.materials.get('exo_mat') or bpy.data.materials.new('exo_mat')
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()
    output = tree.nodes.new('ShaderNodeOutputMaterial')
    output.location = (600, 0)
    shader = tree.nodes.new('ShaderNodeBsdfPrincipled')
    shader.location = (300, 0)
    shader.inputs['Metallic'].default_value = 0.48
    tree.links.new(shader.outputs['BSDF'], output.inputs['Surface'])
    tex = tree.nodes.new('ShaderNodeTexImage'); tex.image = dif; tex.location = (-700, 300)
    tree.links.new(tex.outputs['Color'], shader.inputs['Base Color'])
    texn = tree.nodes.new('ShaderNodeTexImage'); texn.image = nrm; texn.location = (-700, 0)
    normal = tree.nodes.new('ShaderNodeNormalMap'); normal.location = (-350, 0)
    tree.links.new(texn.outputs['Color'], normal.inputs['Color'])
    tree.links.new(normal.outputs['Normal'], shader.inputs['Normal'])
    texg = tree.nodes.new('ShaderNodeTexImage'); texg.image = spec; texg.location = (-700, -300)
    invert = tree.nodes.new('ShaderNodeMath'); invert.operation = 'SUBTRACT'; invert.inputs[0].default_value = 1.0; invert.location = (-350, -250)
    tree.links.new(texg.outputs['Color'], invert.inputs[1])
    tree.links.new(invert.outputs[0], shader.inputs['Roughness'])
    tree.nodes.active = tex
    for obj in objects:
        obj.data.materials.clear()
        obj.data.materials.append(material)
        for poly in obj.data.polygons:
            poly.material_index = 0
    print('EXO atlas: %d objects, %.1f%% occupied, %d detail pixels' % (len(objects), 100.0*mask.mean(), np.count_nonzero(detail)))
    print('EXO atlas marking pixels: pale=%d amber=%d' % (np.count_nonzero(markings == 1), np.count_nonzero(markings == 2)))
    return material



