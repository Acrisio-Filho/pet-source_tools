# Copyright 2023-2026 Acrisio Filho

# utils
import bpy, os, pathlib, numpy, re, tempfile, struct, uuid, itertools # pyright: ignore[reportMissingImports]
from mathutils import Vector, Matrix, Quaternion # pyright: ignore[reportMissingImports]
from bpy_extras.io_utils import axis_conversion # pyright: ignore[reportMissingImports]
from collections import namedtuple, OrderedDict
from math import floor

from .pet import (
    VERSION_1_0,
    compareVersions,
    Puppet
)

__counter = itertools.count(start=1)

def getNewGUID():
    return next(__counter)

def findIndexList(list, value, default = -1):
    if value in list:
        return list.index(value)
    return default

def updateScreenClipEnd(limit):
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.clip_end = max(space.clip_end, limit)

def getCurrentClipEnd():
    limit = 0
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    limit = max(space.clip_end, limit)
    return limit

def loadImage(image_path):

    image = bpy.data.images.get(os.path.basename(image_path))

    if not image:
        image = bpy.data.images.load(image_path)
    
    return image

def load_dds_to_blender(image_name, width, height, data_dxt1):
    assert len(data_dxt1) == (width * height) // 2, "Tamanho dos dados incompatível com DXT1"

    # DDS header para DXT1 (128 bytes fixos)
    header = b'DDS '  # Magic number
    dwSize = 124
    dwFlags = 0x0002100F  # Caps | Height | Width | PixelFormat | MipMapCount | LinearSize
    dwPitchOrLinearSize = int((width * height) / 2)
    dwDepth = 0
    dwMipMapCount = 1
    dwReserved1 = b'\x00' * (4 * 11)

    # Pixel format (32 bytes)
    ddspf = struct.pack('<I I 4s I I I I I',
        32,             # size
        0x00000004,     # flags: DDPF_FOURCC
        b'DXT1',        # fourCC
        0, 0, 0, 0, 0   # RGBBitCount, R, G, B, A masks
    )

    # Caps (16 bytes)
    caps = struct.pack('<I I I I',
        0x00001000,     # DDSCAPS_TEXTURE
        0, 0, 0
    )

    header += struct.pack('<I I I I I I', dwSize, dwFlags, height, width, dwPitchOrLinearSize, dwDepth)
    header += struct.pack('<I', dwMipMapCount)
    header += dwReserved1
    header += ddspf
    header += caps

    # Reserved2
    header += struct.pack('<I', 0)

    dds_data = header + bytearray(data_dxt1)

    # Salva em arquivo temporário
    with tempfile.NamedTemporaryFile(delete=False, suffix=".dds") as tmp:
        tmp.write(dds_data)
        tmp_path = tmp.name

    try:
        # Carrega no Blender
        imagem = bpy.data.images.load(tmp_path)
        imagem.name = image_name
        # força a carrega os dados da imagem para remover o arquivo temporário
        imagem.pixels[:]
        imagem.pack()
    finally:
        os.remove(tmp_path)

    return imagem

def load_saved_model(filepath):
    model = None

    if pathlib.Path(filepath).exists():
        with open(filepath, "rb") as file:
            model = Puppet()
            model.load(file)
        
    return model

def PangyaToBlenderMatrix():
    matrix = axis_conversion(
        from_forward='-X',
        from_up='Y'
    ).to_4x4()

    # invert axis x
    return matrix @ Matrix.Scale(-1, 4, (1, 0, 0)).to_4x4()

def BlenderToPangyaMatrix():
    return PangyaToBlenderMatrix().inverted()

def makeMatrixFrom4x3(m):
    if m is None:
        return Matrix.Identity(4)
    m4 = Matrix([
            [m[0], m[3], m[6], m[9]],
            [m[1], m[4], m[7], m[10]],
            [m[2], m[5], m[8], m[11]],
            [0, 0, 0, 1],
        ])
    return m4

def make4x3FromMatrix(m):
    return[
        m[0].x, m[1].x, m[2].x,
        m[0].y, m[1].y, m[2].y,
        m[0].z, m[1].z, m[2].z,
        m[0].w, m[1].w, m[2].w
    ]

def vec3_divide(vec1, vec2):
    return Vector(el1 / el2 for el1, el2 in zip(vec1, vec2))

def mat4_shrink_scale(m):
    return Matrix.LocRotScale(*m.decompose()[:2], (1, 1, 1))

def mat4_to_length_mat4(m, bone_length=0.0001):
    return bone_length / m.to_scale().length, m

def ebone_to_mat4(bone):
    return bone.matrix_local_pangya

def mat4_to_ebone(bone, mat4):
    bone["matrix_local_pangya"] = mat4.copy()

def calc_ebonemat(bone):
    m = Matrix.Identity(4)
    while bone:
        m = bone.matrix_local_pangya @ m
        bone = bone.parent
    return m

def calc_deform_vert_by_mpet_and_bpet_arm(vert, bone_weights, mpet, bpet=None):
    vertpos = Vector((vert.x, vert.y, vert.z))
    vector = Vector((0, 0, 0))

    if not bpet:
        bpet = mpet
    
    vertpos = mpet.data.bones[bone_weights[0][0]].matrix_local @ vertpos

    for bone_name, weight in bone_weights:
        part = bpet.data.bones[bone_name].matrix_local @ mpet.data.bones[bone_name].matrix_local.inverted() @ vertpos
        vector += part * weight

    return vector
        
def calc_original_vert_by_old_arm(vert, bone_weights, old, mpet=None):
    vertpos = Vector((vert.x, vert.y, vert.z))

    # old arm is bpet
    if ".bpet" in old.name and mpet:
        A = numpy.zeros((4, 4))
        v_deformed = numpy.array([vertpos.x, vertpos.y, vertpos.z, 1.0])
        
        bone0_name = bone_weights[0][0]
        for bone_name, weight in bone_weights:
            M = old.data.bones[bone_name].matrix_local @ mpet.data.bones[bone_name].matrix_local.inverted() @ mpet.data.bones[bone0_name].matrix_local
            A += weight * numpy.array(M)
        v_original, residuals, rank, s = numpy.linalg.lstsq(A, v_deformed, rcond=None)
        vertpos = Vector(v_original[:3])
    else:
        vertpos = old.data.bones[bone_weights[0][0]].matrix_local.inverted() @ vertpos

    return vertpos

def ifnull(a, b):
    if a:
        return a
    return b

def make_unique_name(name):
    return f"{name}__§{str(uuid.uuid4())[:8]}"

def remove_unique_name(name):
    return re.sub(r"__§.*$", "", name)

def remove_and_make_unique_name(name, append="", pre=False):
    if pre:
        return make_unique_name(append + remove_unique_name(name))
    
    return make_unique_name(remove_unique_name(name) + append)

def is_valid_object(obj):
    if not obj:
        return False
    try:
        _ = obj.name
        return True
    except ReferenceError:
        return False

def average_normals_and_merge_and_smooth(mesh):
    # normals_average 'FACE_AREA' and merge
    pos_normal_map = {}
    for face in mesh.polygons:
        f_normal = face.normal * face.area
        for loop_idx in face.loop_indices:
            v_idx = mesh.loops[loop_idx].vertex_index
            co = tuple(round(c, 6) for c in mesh.vertices[v_idx].co)

            if co not in pos_normal_map:
                pos_normal_map[co] = Vector((0, 0, 0))
            pos_normal_map[co] += f_normal

    for co in pos_normal_map:
        if pos_normal_map[co].length > 0:
            pos_normal_map[co].normalize()

    loop_normals = [Vector((0, 0, 0))] * len(mesh.loops)
    for loop in mesh.loops:
        co = tuple(round(c, 6) for c in mesh.vertices[loop.vertex_index].co)
        loop_normals[loop.index] = pos_normal_map[co]
    mesh.normals_split_custom_set(loop_normals)

    mesh.validate(clean_customdata=False)
    mesh.update()

    # smooth_normals
    current_normals = [Vector(v.normal) for v in mesh.vertices]
    for _ in range(3):
        len_vertices = len(mesh.vertices)
        next_normals = [Vector((0, 0, 0)) for _ in range(len_vertices)]

        vert_neighbors = [[] for _ in range(len_vertices)]
        for edge in mesh.edges:
            v1, v2 = edge.vertices
            vert_neighbors[v1].append(v2)
            vert_neighbors[v2].append(v1)

        for i, neighbors in enumerate(vert_neighbors):
            if not neighbors:
                next_normals[i] = current_normals[i]
                continue
            
            neighbors_avg = sum((current_normals[n] for n in neighbors), Vector((0, 0, 0)))
            neighbors_avg /= len(neighbors)

            next_normals[i] = current_normals[i].lerp(neighbors_avg, 0.5).normalized()

        current_normals = next_normals

    loop_normals = [current_normals[l.vertex_index] for l in mesh.loops]
    mesh.normals_split_custom_set(loop_normals)
        
    mesh.validate(clean_customdata=False)
    mesh.update()

def value_to_attr_string_value(value):
    if bpy.app.version >= (3, 6, 0):
        return value.encode('utf-8')
    
    return value

def attr_string_value_to_value(attr_string_value):
    if bpy.app.version >= (3, 6, 0):
        return attr_string_value.decode('utf-8')

    return attr_string_value

def get_vertice_mpet_weight_global_name():
    return "MPET_WEIGHT_GLOBAL_VALUE"

def get_vertice_main_bone_name():
    return "VERTICE_MAIN_BONE_NAME"

def get_face_material_espacular_index_name():
    return "FACE_MATERIAL_SPECULAR_INDEX"

def make_mesh_attribute(obj, name, type="FLOAT", domain="POINT"):
    if not is_valid_object(obj) or obj.type != "MESH":
        return None
    attr = obj.data.attributes.get(name)
    if not attr:
        attr = obj.data.attributes.new(name=name, type=type, domain=domain)
    return attr

def get_vertice_mpet_weight_global_value(obj, vertice):
    if not is_valid_object(obj) or obj.type != "MESH":
        return 1.0

    attr_mpet_weight_global = obj.data.attributes.get(get_vertice_mpet_weight_global_name())
    if not attr_mpet_weight_global:
        return 1.0
    
    if vertice.index >= len(attr_mpet_weight_global.data):
        return 1.0

    return attr_mpet_weight_global.data[vertice.index].value

def get_bone_weights_and_main_bone_weight(obj, vertice):
    if not is_valid_object(obj):
        return None, None

    main_bone_weight = next((attr_string_value_to_value(attr.data[vertice.index].value) for attr in obj.data.attributes if (
        attr.data_type == "STRING" and attr.name == get_vertice_main_bone_name() and vertice.index < len(attr.data)
    )), None)

    if not main_bone_weight:
        return None, None

    bone_weights = sorted(
        [
            [obj.vertex_groups[g.group].name, g.weight] for g in vertice.groups if g.weight > 0
        ],
        key=lambda x: (x[0] != main_bone_weight, -x[1])
    )

    if len(bone_weights) == 0:
        return None, None

    return bone_weights[0], bone_weights

# linux case sensitive filename
def resolve_case_sensitive(filename, dirname = "."):
    path = pathlib.Path(filename)

    if path.is_absolute():
        resolved = pathlib.Path(path.anchor)
        parts_to_resolve = path.parts[1:]
    else:
        resolved = pathlib.Path(dirname).resolve()
        parts_to_resolve = path.parts
    
    full_path = resolved / path if not path.is_absolute() else path
    if full_path.exists():
        return full_path

    for part in parts_to_resolve:
        if not part or part == '.':
            continue

        part_lower = part.lower()
        matched = False

        if resolved.is_dir():
            for child in resolved.iterdir():
                if child.name.lower() == part_lower:
                    resolved = child
                    matched = True
                    break
                    
        if not matched:
            resolved = resolved / part
    
    return resolved

def find_parent_folder(dirname, folder):
    if os.name == 'nt': # Windows
        return find_parent_folder_(dirname, folder)
    else:
        return find_parent_folder_linux(dirname, folder)

def find_parent_folder_(dirname, folder):
    parent = os.path.dirname(dirname)
    texdir = os.path.join(dirname, folder)
    if os.path.exists(texdir):
        return texdir
    elif dirname != parent:
        return find_parent_folder_(parent, folder)
    else:
        return None

def find_parent_folder_linux(dirname, folder):
    parent = os.path.dirname(dirname)
    texdir = resolve_case_sensitive(folder, dirname)
    if texdir.exists():
        return texdir
    elif dirname != parent:
        return find_parent_folder_linux(parent, folder)
    else:
        return None

def find_file_in_children_folder(dirname, file, aggressive):
    if os.name == 'nt': # Windows
        return find_file_in_children_folder_(dirname, file, aggressive)
    else:
        return find_file_in_children_folder_linux(dirname, file, aggressive)

def find_file_in_children_folder_(dirname, file, aggressive):
    path = pathlib.Path(os.path.join(dirname, file))
    if path.exists():
        return path
    if not aggressive:
        return None
    try:
        children = next(os.walk(dirname))[1]
    except StopIteration:
        return None
    if len(children) == 0:
        return None
    child_path = None
    for child in children:
        child_path = find_file_in_children_folder_("{}/{}".format(dirname, child), file, aggressive)
        if child_path is not None:
            break
    return child_path

def find_file_in_children_folder_linux(dirname, file, aggressive):
    path = resolve_case_sensitive(file, dirname)
    if path.exists():
        return path
    if not aggressive:
        return None
    try:
        children = next(os.walk(dirname))[1]
    except StopIteration:
        return None
    if len(children) == 0:
        return None
    child_path = None
    for child in children:
        child_path = find_file_in_children_folder_linux("{}/{}".format(dirname, child), file, aggressive)
        if child_path is not None:
            break
    return child_path

def load_texture_path(dirname, filename):
    path = pathlib.Path(filename)
    if path.is_absolute():
        if os.name == 'nt': # Windows
            image_path = path
        else:
            image_path = resolve_case_sensitive(path)
    else:
        image_path = find_texture(dirname, filename)
        if not image_path.exists():
            image_path = find_texture_in_resources_diretories(filename)
            if not image_path.exists():
                print("(texture) {} file not found".format(image_path))
    
    return str(image_path)
    
def load_model_path(dirname, filename):
    path = pathlib.Path(filename)
    if path.is_absolute():
        if os.name == 'nt': # Windows
            model_path = path
        else:
            model_path = resolve_case_sensitive(path)
    else:
        model_path = find_model(dirname, filename)
        if not model_path.exists():
            model_path = find_model_in_resources_directories(filename)
            if not model_path.exists():
                print("(model) {} file not found".format(model_path))
    
    return str(model_path)

# Attempts to find PangYa's texture_dds folder, containing DDS textures.
def find_texture(dirname, texture, aggressive = False):
    image_path = find_file_in_children_folder(dirname, texture, aggressive)
    if image_path is not None:
        return image_path
    base, ext = os.path.splitext(texture)
    if ext == ".dds":
        image_path = find_parent_folder(dirname, 'texture_dds')
        if image_path is not None:
            image_path = find_file_in_children_folder(image_path, texture, aggressive)
    else:
        for folder in ('z_common', 'map_source', 'misc', 'effect', 'texture_dds', 'npc', 'ppl', 'skybox',):
            image_path = find_parent_folder(dirname, folder)
            if image_path is not None:
                image_path = find_file_in_children_folder(image_path, texture, aggressive)
                if image_path is not None:
                    break
                    
    return image_path if image_path is not None else pathlib.Path(texture)

# Attempts to find PangYa's map, ase, ani_object folder, containing Puppet models.
def find_model(dirname, model, aggressive = False):
    model_path = find_file_in_children_folder(dirname, model, aggressive)
    if model_path is not None:
        return model_path
    for folder in ('map', 'ase', 'ani_object', 'npc', 'rank', 'data_area', 'data_lobby', 'data_map', 'node', 'ppl',):
        model_path = find_parent_folder(dirname, folder)
        if model_path is not None:
            model_path = find_file_in_children_folder(model_path, model, aggressive)
            if model_path is not None:
                break
                    
    return model_path if model_path is not None else pathlib.Path(model)

# find texture in pangya resources directories
def find_texture_in_resources_diretories(texture, aggressive = True):
    image_path = pathlib.Path(texture)
    for pangya_resource in bpy.context.scene.pangya_resources:
        image_path = find_texture(pangya_resource.directory, texture, aggressive)
        if image_path.exists():
            return image_path
    # not found request select pangya resource directory
    bpy.ops.select_dir.pangya_resource("INVOKE_DEFAULT")
    return image_path

# find model in pangya resources directories
def find_model_in_resources_directories(model, aggressive = True):
    model_path = pathlib.Path(model)
    for pangya_resource in bpy.context.scene.pangya_resources:
        model_path = find_model(pangya_resource.directory, model, aggressive)
        if model_path.exists():
            return model_path
    # not found request select pangya resource directory
    bpy.ops.select_dir.pangya_resource("INVOKE_DEFAULT")
    return model_path

# compare vectors
def cmpVectors(v1, v2, cmp=1e-05):
    length = len(v1)

    if length != len(v2):
        return False
    if length >= 1 and abs(v1.x - v2.x) >= cmp:
        return False
    if length >= 2 and abs(v1.y - v2.y) >= cmp:
        return False
    if length >= 3 and abs(v1.z - v2.z) >= cmp:
        return False
    if length >= 4 and abs(v1.w - v2.w) >= cmp:
        return False

    return True

# compare vectors than equal
def cmpVectorsThanEqual(v1, v2, cmp=1e-05):
    length = len(v1)

    if length != len(v2):
        return False
    if length >= 1 and abs(v1.x - v2.x) > cmp:
        return False
    if length >= 2 and abs(v1.y - v2.y) > cmp:
        return False
    if length >= 3 and abs(v1.z - v2.z) > cmp:
        return False
    if length >= 4 and abs(v1.w - v2.w) > cmp:
        return False
    
    return True

MVTX = namedtuple('MVTX', ['face_index', 'vertex_index', 'vertex', 'weight', 'uvs', 'normal', 'bone_name'])

# compare mvtx
def compare_mvtx(mvtx, mvtx2):
    if not cmpVectors(mvtx.vertex, mvtx2.vertex):
        return False
    if mvtx.weight != mvtx2.weight:
        return False
    if len(mvtx.uvs) != len(mvtx2.uvs):
        return False
    for i in range(len(mvtx.uvs)):
        if mvtx.uvs[i].x != mvtx2.uvs[i].x or mvtx.uvs[i].y != mvtx2.uvs[i].y:
            return False
    if not cmpVectorsThanEqual(mvtx.normal, mvtx2.normal, 0.001):
        return False
    if mvtx.bone_name != mvtx2.bone_name:
        return False
    
    return True

# Vertex Num PangYa calculo
def getMainBoneBlender(_data, _bones, _vertex_idx):
    main_bone_name = next((attr_string_value_to_value(attr.data[_vertex_idx].value) for attr in _data.attributes if (
        attr.data_type == "STRING" and attr.name == get_vertice_main_bone_name() and _vertex_idx < len(attr.data)
    )), None)

    return _bones.get(main_bone_name)

def hasChildBlender(_parent, _child):
    while _child.parent:
        if _parent.name == _child.parent.name:
            return True
        _child = _child.parent
    return False

def noChildrenBlender(_bone):
    if _bone.children:
        return False
    return True

def isFakeBodyBlender(_bone):
    if "Bip" not in _bone.name and "Bone" not in _bone.name and "Jaw" not in _bone.name:
        return True
    return False

def findFakeBodyBoneBlender(_data, _bones, _numVertices):
    for bone in _bones:
        if "Bip" in bone.name or "Jaw" in bone.name:
            continue
        i = 0
        while i < _numVertices:
            b = getMainBoneBlender(_data, _bones, i)
            if bone.name == b.name:
                break
            i += 1
        if i == _numVertices and noChildrenBlender(bone):
            return bone
    return None

# get face index of vertex pangya by material same bone from blender
def get_face_index_of_vertex_pangya_by_material_same_bone_from_blender(obj, armature_obj, bone_name, material, version):
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='OBJECT')
    
    # find fake body bone
    fakeBodyBone = findFakeBodyBoneBlender(obj.data, armature_obj.data.bones, len(obj.data.vertices))

    if fakeBodyBone:
        print("======== Tem fakebonebone: %s" % (fakeBodyBone.name))

    # calcula os normais aqui. Os vertex já está baked(calculado)
    loop_normals = {}
    zero = Vector((0, 0, 0))
    for polys in obj.data.polygons:
        for loop in [obj.data.loops[l] for l in polys.loop_indices]:
            nor = loop.normal.xyz
            if not cmpVectors(nor, zero):
                if compareVersions(version, VERSION_1_0) <= 0:
                    if not fakeBodyBone or isFakeBodyBlender(getMainBoneBlender(obj.data, armature_obj.data.bones, loop.vertex_index)):
                        nor = getMainBoneBlender(obj.data, armature_obj.data.bones, loop.vertex_index).matrix_local.to_3x3() @ nor
                    else:
                        nor = fakeBodyBone.matrix_local.to_3x3() @ nor
            else:
                mat = getMainBoneBlender(obj.data, armature_obj.data.bones, obj.data.loops[polys.loop_indices[0]].vertex_index)
                points = [obj.data.vertices[loop2.vertex_index].co.xyz for loop2 in [obj.data.loops[l2] for l2 in polys.loop_indices]]
                points[0] = mat @ points[0]
                points[1] = mat @ points[1]
                points[2] = mat @ points[2]
                v1 = points[2] - points[1]
                v2 = points[0] - points[1]
                nor = v1 * v2
            if cmpVectors(nor, zero):
                nor = nor * 0
            else:
                nor.normalize()
            loop_normals[loop.index] = nor.xyz

    np_polys = []
    for poly in obj.data.polygons:
        bone = None
        for loop in [obj.data.loops[l] for l in poly.loop_indices]:
            b = getMainBoneBlender(obj.data, armature_obj.data.bones, loop.vertex_index)
            if not bone:
                bone = b
            elif bone.name != b.name and hasChildBlender(b, bone):
                bone = b
        if not bone or bone.name != bone_name:
            continue
        if obj.data.materials[poly.material_index]["group"] != material["group"] or obj.data.materials[poly.material_index]["handle"] != material["handle"]:
            continue
        np_polys.append(poly)
    
    new_polys = []
    for poly in np_polys:
        for loop in [obj.data.loops[l] for l in poly.loop_indices]:
            bone = getMainBoneBlender(obj.data, armature_obj.data.bones, loop.vertex_index)
            if not bone:
                continue
            mvtx = MVTX(
                loop.index, # face index
                loop.vertex_index, # vertex index
                obj.data.vertices[loop.vertex_index].co.xyz,
                get_vertice_mpet_weight_global_value(obj, obj.data.vertices[loop.vertex_index]), # weight_global
                [uv_layer.data[loop.index].uv for uv_layer in obj.data.uv_layers],
                loop_normals[loop.index].xyz,
                bone.name
            )
            if len(new_polys) == 0:
                new_polys.append(mvtx)
            else:
                i = 0
                for np in new_polys:
                    if compare_mvtx(np, mvtx):
                        break
                    i += 1
                if len(new_polys) == i:
                    new_polys.append(mvtx)
    
    return [(poly.face_index, poly.vertex_index) for poly in new_polys], len(np_polys * 3)

def get_mesh_material_list_by_bone_from_blender(obj, armature_obj, bone_name):
    if not is_valid_object(obj) and obj.type != "MESH":
        return []

    np_polys = []
    for poly in obj.data.polygons:
        bone = None
        for loop in [obj.data.loops[l] for l in poly.loop_indices]:
            b = getMainBoneBlender(obj.data, armature_obj.data.bones, loop.vertex_index)
            if not bone:
                bone = b
            elif bone.name != b.name and hasChildBlender(b, bone):
                bone = b
        if not bone or bone.name != bone_name:
            continue
        np_polys.append(poly.index)

    texmap_filtered = [poly.material_index for poly in obj.data.polygons if poly.index in np_polys]

    return [obj.data.materials[mtrl_idx] for mtrl_idx in reversed(OrderedDict.fromkeys(texmap_filtered).keys())]

def calc_bonematModel(_bones, id):
    m = Matrix.Identity(4)
    b = _bones[id]
    while b:
        m = makeMatrixFrom4x3(b.matrix) @ m
        if b.parent == -1:
            break
        b = _bones[b.parent]
    return m

def hasChildModel(_bones, _parent_id, _child_id):
    child = _bones[_child_id]
    parent = _bones[_parent_id]

    while child.parent != -1:
        child = _bones[child.parent]
        if parent.name == child.name:
            return True
    return False

def noChildrenModel(_bones, _bone_id):
    for bone in _bones:
        if bone.parent == _bone_id:
            return False
    return True
    
def isFakeBodyModel(_bones, _bone_id):
    b = _bones[_bone_id]
    if "Bip" not in b.name and "Bone" not in b.name and "Jaw" not in b.name:
        return True
    return False

def findFakeBodyBoneModel(_bones, _vertices):
    for id,bone in enumerate(_bones):
        if "Bip" in bone.name or "Jaw" in bone.name:
            continue
        i = 0
        numVertices = len(_vertices)
        while i < numVertices:
            if id == _vertices[i].bone_weights[0].id:
                break
            i += 1
        if i == numVertices and noChildrenModel(_bones, id):
            return id
    return -1

# get face index of vertex pangya by material index same bone from model
def get_face_index_of_vertex_pangya_by_material_same_bone_from_model(model, bone_name, material):

    # calcule vertice by main bone
    vertices = []
    for vert in model.mesh.vertices:
        point = calc_bonematModel(model.bones, vert.bone_weights[0].id) @ Vector((vert.x, vert.y, vert.z))
        vertices.append(point.xyz)
    
    # find fake body bone
    fakeBodyBoneId = findFakeBodyBoneModel(model.bones, model.mesh.vertices)

    if fakeBodyBoneId != -1:
        print("======== Tem fakebonebone: %s" % (model.bones[fakeBodyBoneId].name))

    # calcule normal by transformNormals
    loop_normals = {}
    zero = Vector((0, 0, 0))
    for poly_idx, polys in enumerate(model.mesh.polygons):
        for loop_idx, poly in enumerate(polys.indices):
            nor = Vector((poly.nx, poly.ny, poly.nz))
            if not cmpVectors(nor, zero):
                if compareVersions(model.version, VERSION_1_0) <= 0:
                    if fakeBodyBoneId == -1 or isFakeBodyModel(model.bones, model.mesh.vertices[poly.index].bone_weights[0].id):
                        nor = calc_bonematModel(model.bones, model.mesh.vertices[poly.index].bone_weights[0].id).to_3x3() @ nor
                    else:
                        nor = calc_bonematModel(model.bones, fakeBodyBoneId).to_3x3() @ nor
            else:
                mat = calc_bonematModel(model.bones, model.mesh.vertices[polys.indices[0].index].bone_weights[0].id)
                points = [vertices[ply.index].xyz for ply in polys.indices]
                points[0] = mat @ points[0]
                points[1] = mat @ points[1]
                points[2] = mat @ points[2]
                v1 = points[2] - points[1]
                v2 = points[0] - points[1]
                nor = v1 * v2
            if cmpVectors(nor, zero):
                nor = nor * 0
            else:
                nor.normalize()
            loop_normals[poly_idx * 3 + loop_idx] = nor.xyz

    np_polys = []
    for poly_idx, polys in enumerate(model.mesh.polygons):
        bone_id = -1
        for poly in polys.indices:
            vertex = model.mesh.vertices[poly.index]
            if bone_id == -1:
                bone_id = vertex.bone_weights[0].id
            elif bone_id != vertex.bone_weights[0].id and hasChildModel(model.bones, vertex.bone_weights[0].id, bone_id):
                bone_id = vertex.bone_weights[0].id
        if model.bones[bone_id].name != bone_name:
            continue
        mtrl = model.textures[model.mesh.texmap[poly_idx]]
        if mtrl.group != material.group or mtrl.handle != material.handle:
            continue
        np_polys.append((poly_idx, polys))

    np = []
    for (poly_idx, polys) in np_polys:
        for index,poly in enumerate(polys.indices):
            vertex = model.mesh.vertices[poly.index]
            poly_bone = model.bones[vertex.bone_weights[0].id]
            mvtx = MVTX(
                poly_idx * 3 + index, # face index
                poly.index, # vertex index
                vertices[poly.index].xyz,
                vertex.weight_global,
                [Vector((uv.u, uv.v)) for uv in poly.uvMapping],
                loop_normals[poly_idx * 3 + index].xyz,
                poly_bone.name
            )
            if not np:
                np.append(mvtx)
            else:
                i = 0
                for p1 in np:
                    if compare_mvtx(p1, mvtx):
                        break
                    i += 1
                if len(np) == i:
                    np.append(mvtx)
    
    return [(poly.face_index, poly.vertex_index) for poly in np], len(np_polys) * 3

def get_mesh_material_list_by_bone_from_model(model, bone_name):
    if not model:
        return []

    np_polys = []
    for poly_idx, polys in enumerate(model.mesh.polygons):
        bone_id = -1
        for poly in polys.indices:
            vertex = model.mesh.vertices[poly.index]
            if bone_id == -1:
                bone_id = vertex.bone_weights[0].id
            elif bone_id != vertex.bone_weights[0].id and hasChildModel(vertex.bone_weights[0].id, bone_id):
                bone_id = vertex.bone_weights[0].id
        if model.bones[bone_id].name != bone_name:
            continue
        np_polys.append(poly_idx)

    texmap_filtered = [txmp for idx,txmp in enumerate(model.mesh.texmap) if idx in np_polys]

    return [model.textures[mtrl_idx] for mtrl_idx in reversed(OrderedDict.fromkeys(list(texmap_filtered)).keys())]

# get face all index of vertex pangya by material index same bone from model
def get_face_all_index_of_vertex_pangya_by_material_same_bone_from_model(model, bone_name):

    np_polys = {}
    for poly_idx, polys in enumerate(model.mesh.polygons):
        bone_id = -1
        for poly in polys.indices:
            vertex = model.mesh.vertices[poly.index]
            if bone_id == -1:
                bone_id = vertex.bone_weights[0].id
            elif bone_id != vertex.bone_weights[0].id and hasChildModel(vertex.bone_weights[0].id, bone_id):
                bone_id = vertex.bone_weights[0].id
        if model.bones[bone_id].name != bone_name:
            continue
        idx = model.mesh.texmap[poly_idx]
        if idx in np_polys:
            np_polys[idx].append(poly_idx * 3)
        else:
            np_polys[idx] = [poly_idx * 3]

    return [poly_idxs for poly_idxs in reversed(np_polys.items())], sum(len(l) for l in np_polys.values())

# vertex color pangya to blender
def vertex_color_pangya_to_blender(vtxColor):

    # ARGB 0xAARRGGBB 0xFF959595
    return (((vtxColor >> 16) & 0xFF)/0xFF, ((vtxColor >> 8) & 0xFF)/0xFF, (vtxColor & 0xFF)/0xFF, ((vtxColor >> 24) & 0xFF)/0xFF)

# vertex color blender to pangya
def vertex_color_blender_to_pangya(vtxColor):

    # ARGB 0xAARRGGBB 0xFF959595
    return (floor(vtxColor[3] * 0xFF) << 24) | (floor(vtxColor[0] * 0xFF) << 16) | (floor(vtxColor[1] * 0xFF) << 8) | floor(vtxColor[2] * 0xFF)

def make_bbox(collection, bone_name, name, bbox, matrix, parent=None, hide=True):
    if type(bbox).__name__ == "AABB":
        bbox = bbox.tolist()

    # Definir os limites do bounding box
    minx, miny, minz = bbox[0], bbox[1], bbox[2]
    maxx, maxy, maxz = bbox[3], bbox[4], bbox[5]

    # Definir os 8 vértices do cubo
    # A ordem segue o padrão: (x, y, z)
    vertices = [
        (minx, miny, minz), (minx, miny, maxz),
        (minx, maxy, minz), (minx, maxy, maxz),
        (maxx, miny, minz), (maxx, miny, maxz),
        (maxx, maxy, minz), (maxx, maxy, maxz)
    ]

    # Definir as 6 faces (cada uma ligando 4 índices de vértices)
    # A ordem dos índices garante que as normais fiquem para fora
    faces = [
        (0, 4, 6, 2), # Base
        (3, 7, 5, 1), # Topo
        (0, 2, 3, 1), # Lateral Esquerda
        (4, 5, 7, 6), # Lateral Direita
        (0, 1, 5, 4), # Frente
        (2, 6, 7, 3)  # Trás
    ]

    # Criar o Mesh e o Objeto nos dados do Blender
    mesh = bpy.data.meshes.new(make_unique_name(name + ".mesh"))
    obj = bpy.data.objects.new(make_unique_name(name), mesh)

    # Construir a geometria a partir das listas (edges podem ser vazias [])
    mesh.from_pydata(vertices, [], faces)
    mesh.update()

    # Lincar na coleção desejada
    collection.objects.link(obj)

    obj.matrix_world @= matrix

    if parent:
        obj.parent = parent

        # make vertex group if have armature
        if parent.parent:
            bgroup = obj.vertex_groups.new(name=bone_name)

            # Load groups into Blender
            for id, _ in enumerate(vertices):
                bgroup.add([id], 1.0, 'ADD')

            # Armature modifier
            bmodifier = obj.modifiers.new(parent.parent.data.name, type='ARMATURE')
            bmodifier.show_expanded = False
            bmodifier.use_vertex_groups = True
            bmodifier.use_bone_envelopes = False
            bmodifier.object = parent.parent

    # Cria modificador de wire frame
    wire_mod = obj.modifiers.new(obj.name, type='WIREFRAME')
    wire_mod.thickness = 0.0002 
    wire_mod.use_replace = True
    wire_mod.use_even_offset = False

    obj.display_type = 'BOUNDS'
    
    obj.hide_render = True
    obj.hide_set(hide)

    return obj

def calcule_bound_box(mesh_obj, matrix=Matrix.Identity(4), with_evaluated=False):

    def aabb(vertices):
        x, y, z = zip(*(p for p in vertices))
        return [
            min(x), min(y), min(z),
            max(x), max(y), max(z)
        ]

    if with_evaluated:
        depsgraph = bpy.context.evaluated_depsgraph_get()

        obj_eval = mesh_obj.evaluated_get(depsgraph)

        vertices = [matrix @ vertex.co for vertex in obj_eval.data.vertices]
    else:
        vertices = [matrix @ vertex.co for vertex in mesh_obj.data.vertices]

    return aabb(vertices)

def calcule_bound_box_fit_base_model(mesh_obj, matrix=Matrix.Identity(4), with_evaluated=False):

    def aabb(vertices, maxy, real_maxy):
        if abs(real_maxy - maxy) < 10:
            maxy = real_maxy
        else:
            real_maxy = maxy + 10
            maxy += 1
        x, y, z = zip(*(p for p in vertices if p.y <= maxy))
        return [
            min(x), min(y), min(z),
            max(x), real_maxy, max(z)
        ]

    min_max = calcule_bound_box(mesh_obj, matrix, with_evaluated)

    if with_evaluated:
        depsgraph = bpy.context.evaluated_depsgraph_get()

        obj_eval = mesh_obj.evaluated_get(depsgraph)

        vertices = [matrix @ vertex.co for vertex in obj_eval.data.vertices]
    else:
        vertices = [matrix @ vertex.co for vertex in mesh_obj.data.vertices]

    return aabb(vertices, min_max[1], min_max[4])

class KeyFrame:
    def __init__(self, _frame=None, _pos=False, _rot=False, _scale=False, _ori=False, _matrix=Matrix(), _vpos=Vector.Fill(3), _qrot=Quaternion(), _vscale=Vector.Fill(3), _orientation_flag = -1.0):
        self.frame = _frame
        self.pos = _pos
        self.rot = _rot
        self.scale = _scale
        self.ori = _ori
        self.matrix = _matrix
        self.vpos = _vpos
        self.qrot = _qrot
        self.vscale = _vscale
        self.orientation_flag = _orientation_flag