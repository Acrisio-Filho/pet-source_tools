# Copyright 2023-2026 Acrisio Filho

from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

import pathlib, bpy, time # pyright: ignore[reportMissingImports]

from math import floor
from collections import namedtuple, defaultdict, OrderedDict
from mathutils import Vector # pyright: ignore[reportMissingImports]

from .sbin import SBinCtx
from .texture_util import makeGBinShadowmapMaterial
from .util import (
    get_face_index_of_vertex_pangya_by_material_same_bone_from_model,
    get_mesh_material_list_by_bone_from_model,
    load_dds_to_blender,
    make_unique_name,
    remove_unique_name,
    remove_and_make_unique_name,
)

def load_sbin(file, main_model, main_model_obj, main_model_arm_obj, matrix):

    if len(main_model_arm_obj.data.bones) == 0:
        print("===== WARNING ======, Principal modelo do gbin não tem uma armação válida")
        return None, None

    if len(main_model_obj.data.materials) != len(main_model.textures):
        print("===== WARNING ======, Quantidade de material(textura) no principal modelo do gbin não bate: %d != %d" % (len(main_model_obj.data.Materials), len(main_model.textures)))
        return None, None
        
    sbin = SBinCtx()
    sbin.load(file, main_model_arm_obj.data.bones[0].name)

    materials = []
    vertices = []
    mesh_vertice_indices = defaultdict(list)
    for bone in sbin.bones:
        mesh_material_list = get_mesh_material_list_by_bone_from_model(main_model, bone.name)

        mesh_mtrls = []
        all_textures = [*bone.sbin.in_frag_mesh.texture_globals]
        for texture_type in bone.sbin.in_frag_mesh.texture_types:
            all_textures.extend(texture_type)
        for mesh_index, info_mesh in enumerate(bone.sbin.in_frag_mesh.info_meshes):
            mtrl = mesh_material_list[mesh_index]
            mesh_mtrls.append(mtrl)
            vert_indexes, idxNum = get_face_index_of_vertex_pangya_by_material_same_bone_from_model(main_model, bone.name, mtrl)
            mesh_vertice_indices[bone.name].append(vert_indexes)
            if len(vert_indexes) != info_mesh.vtxNum or idxNum != info_mesh.idxNum:
                print("================= WARNING ============", "material[%s]: %d/%d != %d/%d" % (mtrl.fn, len(vert_indexes), idxNum, info_mesh.vtxNum, info_mesh.idxNum), sep="\n")
        for idx, tex in enumerate(all_textures):
            mtrl_idx = len(materials)
            materials.append(makeGBinShadowmapMaterial(load_dds_to_blender(make_unique_name("%s-%d-%d" % (remove_unique_name(main_model_obj.name), 0, idx)), tex.width, tex.height, tex.dataDDS)))
            for poly in tex.mapDDSValues:
                vertex_indices = mesh_vertice_indices[bone.name][poly.mesh_index]
                for i in range(3):
                    bone_name = bone.name
                    if poly.indexes_vertex[i].flag:
                        vert = main_model.mesh.vertices[vertex_indices[poly.indexes_vertex[i].index][1]]
                        bone_name = main_model.bones[vert.bone_weights[0].id].name
                    else:
                        vert = bone.sbin.in_frag_mesh.vertexes[poly.indexes_vertex[i].index]
                    uv = bone.sbin.in_frag_mesh.uvs[poly.indexes_uv[i]]
                    vertices.append(((vert.x, vert.y, vert.z), (uv.x, uv.y), mtrl_idx, bone_name))

    vertices_nodup = OrderedDict.fromkeys(vertices)
    for idx, (vertex, uv, mtrl_idx, bone_name) in enumerate(vertices_nodup.keys()):
        vertices_nodup[(vertex, uv, mtrl_idx, bone_name)] = idx

    # Shadowmap mesh object
    dmesh = bpy.data.meshes.new(remove_and_make_unique_name(main_model_obj.name, "_shadowmap"))
    obj = bpy.data.objects.new(dmesh.name, dmesh)
    collection = main_model_obj.users_collection
    if len(collection) > 0:
        collection = collection[0]
    else:
        collection = bpy.data.collections[0]
    collection.objects.link(obj)

    # Vertices
    verts = []
    for p in vertices_nodup:
        verts.extend((main_model_arm_obj.data.bones.get(p[3]).matrix_local @ Vector(p[0]))[:])

    dmesh.vertices.add(len(vertices_nodup))
    dmesh.vertices.foreach_set("co", verts)

    # Polygons
    num_faces = floor(len(vertices) / 3)
    dmesh.polygons.add(num_faces)
    dmesh.loops.add(num_faces * 3)
    faces = []
    for p in vertices:
        faces.append(vertices_nodup[p])
    dmesh.polygons.foreach_set("loop_start", range(0, num_faces * 3, 3))
    dmesh.polygons.foreach_set("loop_total", (3,) * num_faces)
    dmesh.polygons.foreach_set("use_smooth", (True,) * num_faces)
    dmesh.loops.foreach_set("vertex_index", faces)

    # UV maps
    uvtexs = []
    uvtexs.append(dmesh.uv_layers.new())
    for i, p in enumerate(vertices):
        uv = p[1]
        uvtexs[-1].data[i].uv = uv[0], 1.0 - uv[1]

    # Materials
    for material in materials:
        dmesh.materials.append(material)

    i = 0
    while i < len(vertices):
        dmesh.polygons[floor(i / 3)].material_index = vertices[i][2]
        i += 3

    # finaliza
    dmesh.update()

    # Vertex groups
    VertexWeight = namedtuple('VertexWeight', ['vertex', 'weight'])
    groups = {}

    # Translate weights into structure of groups.
    for (vertex, uv, mtrl_idx, bone_name), idx in vertices_nodup.items():
            group = groups.get(bone_name, [])
            # Main bone weight
            group.append(VertexWeight(idx, 1.0))
            groups[bone_name] = group

    # Load groups into Blender
    for bone_name, weights in groups.items():
        bgroup = obj.vertex_groups.new(name=bone_name)
        for weight in weights:
            bgroup.add([weight.vertex], weight.weight, 'ADD')

    # Armature modifier
    bmodifier = obj.modifiers.new(main_model_arm_obj.data.name, type='ARMATURE')
    bmodifier.show_expanded = False
    bmodifier.show_in_editmode = True
    bmodifier.show_on_cage = True
    bmodifier.use_vertex_groups = True
    bmodifier.use_bone_envelopes = False
    bmodifier.object = main_model_arm_obj

    obj.parent = main_model_obj

    # para não colidir com o model base
    obj.location.y += 0.02

    obj.hide_render = True

    return obj, sbin

def load(filepath, main_model, main_model_obj, main_model_arm_obj, matrix):

    sbin_obj = None
    sbin = None

    print('importing pangya SBIN: %r' % (filepath))

    time1 = time.process_time()

    if pathlib.Path(filepath).exists():
        with open(filepath, "rb") as sbin_file:
            sbin_obj, sbin = load_sbin(sbin_file, main_model, main_model_obj, main_model_arm_obj, matrix)
    else:
        print("(SBIN) Not found %r" % filepath)

    print('import pangya SBIN done in %.4f sec.' % (time.process_time() - time1))

    return sbin_obj, sbin