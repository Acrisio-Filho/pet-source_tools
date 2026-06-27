# Copyright 2023-2026 Acrisio Filho

from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

import bpy, time, bmesh, io # pyright: ignore[reportMissingImports]

from mathutils import Vector # pyright: ignore[reportMissingImports]
from collections import namedtuple, defaultdict
import numpy as np
from PIL import Image

from .gbin import ElementOptionAnimateFlag
from .sbin import (
    SBinCtx,
    SBinBone,
    SBin,
    Vector2d,
    Vector3d,
    MeshInfo,
    IndexVertex,
    MapDDSValue,
    TextureDDS,
    InFragMesh,
    OutFragMesh,
    Version,
)
from .util import (
    get_face_index_of_vertex_pangya_by_material_same_bone_from_model,
    get_mesh_material_list_by_bone_from_model,
    get_face_all_index_of_vertex_pangya_by_material_same_bone_from_model,
    remove_unique_name,
    is_valid_object,
    load_saved_model,
    findIndexList,
    ifnull
)

SBinBoneData = namedtuple('SBinBoneData', ['mesh_info', 'textures'])

def getDDSData(image):
    # Preparar a imagem do Blender
    width, height = image.size
    pixels = np.array(image.pixels).reshape((width, height, 4))

    # Converter pixels do Blender para escala de cinza (Luminância)
    # pixels_rgba é o array (H, W, 4) vindo do Blender
    gray_pixels = 0.299 * pixels[:,:,0] + 0.587 * pixels[:,:,1] + 0.114 * pixels[:,:,2]

    # Identificar onde NÃO é branco (tolerância de 0.98)
    not_white_mask = gray_pixels < 0.98

    # Clarear apenas os pixels selecionados
    # Fórmula: (cor * 0.4) + 0.6 
    # Isso transforma o intervalo [0.0, 1.0] no intervalo [0.6, 1.0]
    # Onde 0.6 é um cinza bem claro.
    gray_pixels[not_white_mask] = (gray_pixels[not_white_mask] * 0.4) + 0.6

    # Converter para bytes 0-255 e preparar para o Pillow
    gray_bytes = (gray_pixels * 255).astype(np.uint8)
    img_gray = Image.fromarray(gray_bytes, mode='L')
    img_gray = img_gray.transpose(Image.FLIP_TOP_BOTTOM)

    # Salvar para Buffer DXT1 com Pillow
    buffer = io.BytesIO()
    img_gray.save(buffer, format='DDS', pixel_format='DXT1')

    # Extrair apenas o payload (dados)
    return buffer.getvalue()[128:]

def collect_shadowmap_data(proxy, model, arm_obj, _vertexes_map, _uvs_map):
    bm = bmesh.new()
    bm.from_mesh(proxy.data)
    bm.faces.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    
    deform_layer = bm.verts.layers.deform.verify()
    uv_layer = bm.loops.layers.uv.verify()

    sbin_bones = {}
    for bone in arm_obj.data.bones:
        mesh_info = []
        textures = []

        vertexes_map = _vertexes_map[bone.name]
        uvs_map = _uvs_map[bone.name]
        
        mesh_vertexes = {}
        
        mesh_material_list = get_mesh_material_list_by_bone_from_model(model, bone.name)
        all_faces_indexes, _ = get_face_all_index_of_vertex_pangya_by_material_same_bone_from_model(model, bone.name)
        
        if len(all_faces_indexes) != len(mesh_material_list):
            raise Exception("========== Face num diferente: %d != %d ==============" % (len(all_faces_indexes), len(mesh_material_list)))

        for material in mesh_material_list:
            vertex_indexes, idxNum = get_face_index_of_vertex_pangya_by_material_same_bone_from_model(model, bone.name, material)
            
            mesh_info.append(MeshInfo(len(vertex_indexes), idxNum))
            
            mesh_vertexes[material] = list(zip(*vertex_indexes))
            
        for i in range(1, len(proxy.data.materials)):
            mat = proxy.data.materials[i]
            image = next((n.image for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image and "toSave" in n.image and n.image["toSave"]), None)
            if not image:
                continue
            
            vg_idx = proxy.vertex_groups.get(bone.name).index
            faces = [f for f in bm.faces if f.material_index == i and any(vg_idx in v[deform_layer] for v in f.verts)]
            
            mapDDSValues = []
            for face in faces:
                mesh_vertexes_indexes, mesh_index = next(
                    (
                        (mesh_vertexes[mesh_material], mesh_idx)
                        for mesh_idx, mesh_material in enumerate(mesh_material_list)
                            if all(v.index in mesh_vertexes[mesh_material][1] for v in face.verts)
                    ),
                    (None, -1)
                )
                
                if not mesh_vertexes_indexes:
                    raise Exception("Invalid face don't have verticies no one mesh_material")
                
                vtx_idxs = []
                if not mesh_vertexes_indexes:
                    for v in face.verts:
                        vtx_key = v.co[:]
                        vtx = vertexes_map.get(vtx_key)
                        if not vtx:
                            vertexes_map[vtx_key] = Vector3d(*(bone.matrix_local.inverted() @ Vector(v.co))[:])
                        vtx_idxs.append(IndexVertex(
                            0,
                            findIndexList(list(vertexes_map.keys()), vtx_key)
                        ))
                else:
                    for v in face.verts:
                        idx = findIndexList(mesh_vertexes_indexes[1], v.index)
                        if idx == -1:
                            vtx_key = v.co[:]
                            vtx = vertexes_map.get(vtx_key)
                            if not vtx:
                                vertexes_map[vtx_key] = Vector3d(*(bone.matrix_local.inverted() @ Vector(v.co))[:])
                            vtx_idxs.append(IndexVertex(
                                0,
                                findIndexList(list(vertexes_map.keys()), vtx_key)
                            ))
                        else:
                            vtx_idxs.append(IndexVertex(
                                1,
                                idx
                            ))
                
                poly_index = -1 if all(vtxi.flag == 1 for vtxi in vtx_idxs) else face.index
                if poly_index != -1:
                    poly_index = findIndexList(all_faces_indexes[mesh_index][1], face.index * 3)
                        
                uv_idxs = []
                for loop in face.loops:
                    uv = loop[uv_layer].uv
                    uv_key = (uv.x, uv.y)
                    uv_data = uvs_map.get(uv_key)
                    if not uv_data:
                        uvs_map[uv_key] = Vector2d(uv.x, 1.0 - uv.y)
                    uv_idxs.append(findIndexList(list(uvs_map.keys()), uv_key))
                
                mapDDSValues.append(MapDDSValue(
                    mesh_index,
                    poly_index,
                    vtx_idxs,
                    uv_idxs
                ))
            
            # só adiciona a textura se tiver triângulos
            if len(mapDDSValues) > 0:
                textures.append(TextureDDS(
                    image.size[0],
                    image.size[1],
                    tuple(getDDSData(image)),
                    mapDDSValues
                ))
            
        print("Bone: %s, new Vtx: %d, new UV: %d" % (bone.name, len(vertexes_map), len(uvs_map)))
            
        sbin_bones[bone.name] = SBinBoneData(mesh_info, textures)
    
    bm.free()
    
    return sbin_bones

def GetFacesWithShadow(obj, image, type):
    ATTRIBUTE_FACE_HAS_SHADOW_NAME = "HAS_SHADOW"

    # make geometry node
    def makeGeometryNode():
        group = bpy.data.node_groups.new(name=f"{obj.name}_GN_group", type="GeometryNodeTree")

        if bpy.app.version < (4, 0, 0):
            group.inputs.new("NodeSocketGeometry", "Geometry")
            group.outputs.new("NodeSocketGeometry", "Geometry")
        else:
            group.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
            group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    
        nodes = group.nodes
        input_node = nodes.new("NodeGroupInput")
        output_node = nodes.new("NodeGroupOutput")

        # named attribute UVMap node
        named_attribute_uvmap_node = nodes.new("GeometryNodeInputNamedAttribute")
        named_attribute_uvmap_node.location[1] = output_node.location[1]
        named_attribute_uvmap_node.data_type = "FLOAT_VECTOR"
        named_attribute_uvmap_node.inputs[0].default_value = "UVMapTest"

        # image texture node
        image_texture_node = nodes.new("GeometryNodeImageTexture")
        image_texture_node.location[1] = output_node.location[1]
        image_texture_node.interpolation = "Closest"
        image_texture_node.inputs[0].default_value = image

        # clamp node
        clamp_node = nodes.new("ShaderNodeClamp")
        clamp_node.location[1] = output_node.location[1]
        clamp_node.clamp_type = "MINMAX"
        clamp_node.inputs[1].default_value = 0.0
        clamp_node.inputs[2].default_value = 1.0

        # luiz suave node
        luiz_suave_node = nodes.new("ShaderNodeMix")
        luiz_suave_node.location[1] = output_node.location[1]
        luiz_suave_node.data_type = "RGBA"
        luiz_suave_node.blend_type = "SOFT_LIGHT"
        luiz_suave_node.clamp_result = True
        luiz_suave_node.inputs[0].default_value = 1.0

        # menor que node
        menor_que_node = nodes.new("FunctionNodeCompare")
        menor_que_node.location[1] = output_node.location[1]
        menor_que_node.data_type = "VECTOR"
        menor_que_node.mode = "ELEMENT"
        menor_que_node.operation = "LESS_THAN"
        menor_que_node.inputs["B"].default_value = (0.999,) * 3

        # field average node
        field_average_node = nodes.new("GeometryNodeFieldAverage")
        field_average_node.location[1] = output_node.location[1]
        field_average_node.data_type = "FLOAT_VECTOR"
        field_average_node.domain = "CORNER"

        # index node
        index_node = nodes.new("GeometryNodeInputIndex")
        index_node.location[1] = output_node.location[1]

        # capture attribute index node
        capture_attribute_index_node = nodes.new("GeometryNodeCaptureAttribute")
        capture_attribute_index_node.location[1] = output_node.location[1]
        capture_attribute_index_node.domain = "FACE"
        capture_attribute_index_node.capture_items.new(socket_type="INT", name="Index")

        # subdivide mesh node
        subdivide_mesh_node = nodes.new("GeometryNodeSubdivideMesh")
        subdivide_mesh_node.location[1] = output_node.location[1]
        subdivide_mesh_node.inputs[1].default_value = 5

        # sample nearest node
        sample_nearest_node = nodes.new("GeometryNodeSampleNearest")
        sample_nearest_node.location[1] = output_node.location[1]
        sample_nearest_node.domain = "FACE"

        # sample index node
        sample_index_node = nodes.new("GeometryNodeSampleIndex")
        sample_index_node.location[1] = output_node.location[1]
        sample_index_node.data_type = "FLOAT_VECTOR"
        sample_index_node.domain = "FACE"

        # maior que node
        maior_que_node = nodes.new("FunctionNodeCompare")
        maior_que_node.location[1] = output_node.location[1]
        maior_que_node.data_type = "VECTOR"
        maior_que_node.mode = "ELEMENT"
        maior_que_node.operation = "GREATER_THAN"
        maior_que_node.inputs["B"].default_value = (0.0,) * 3

        # store named attribute node
        store_named_attribute_has_shadow_node = nodes.new("GeometryNodeStoreNamedAttribute")
        store_named_attribute_has_shadow_node.location[1] = output_node.location[1]
        store_named_attribute_has_shadow_node.data_type = "BOOLEAN"
        store_named_attribute_has_shadow_node.domain = "FACE"
        store_named_attribute_has_shadow_node.inputs[2].default_value = ATTRIBUTE_FACE_HAS_SHADOW_NAME

        group.links.new(image_texture_node.inputs[1], named_attribute_uvmap_node.outputs[0])

        if type == 0:
            # color curve node
            color_curve_node = nodes.new("ShaderNodeRGBCurve")
            color_curve_node.location[1] = output_node.location[1]

            def setCurvePoint(curve, x, y):
                if not curve:
                    return
                curve.points[1].location.xy = x, y
                curve.points.new(1, 1)

            setCurvePoint(color_curve_node.mapping.curves[0], 1, 0)
            setCurvePoint(color_curve_node.mapping.curves[1], 1, 0)
            setCurvePoint(color_curve_node.mapping.curves[2], 1, 0)
            setCurvePoint(color_curve_node.mapping.curves[3], 0.1, 0.85)
            color_curve_node.mapping.initialize()
            color_curve_node.mapping.update()

            group.links.new(color_curve_node.inputs["Color"], image_texture_node.outputs["Color"])
            group.links.new(clamp_node.inputs[0], color_curve_node.outputs["Color"])
        else:
            group.links.new(clamp_node.inputs[0], image_texture_node.outputs["Color"])

        group.links.new(luiz_suave_node.inputs["A"], clamp_node.outputs["Result"])
        group.links.new(luiz_suave_node.inputs["B"], clamp_node.outputs["Result"])
        group.links.new(menor_que_node.inputs["A"], luiz_suave_node.outputs["Result"])
        group.links.new(field_average_node.inputs[0], menor_que_node.outputs["Result"])
        group.links.new(field_average_node.inputs[1], capture_attribute_index_node.outputs[1])
        group.links.new(capture_attribute_index_node.inputs[0], input_node.outputs["Geometry"])
        group.links.new(capture_attribute_index_node.inputs["Index"], index_node.outputs[0])
        group.links.new(subdivide_mesh_node.inputs[0], capture_attribute_index_node.outputs[0])
        group.links.new(sample_nearest_node.inputs[0], subdivide_mesh_node.outputs[0])
        group.links.new(sample_index_node.inputs[0], subdivide_mesh_node.outputs[0])
        group.links.new(sample_index_node.inputs[1], field_average_node.outputs[0])
        group.links.new(sample_index_node.inputs[2], sample_nearest_node.outputs[0])
        group.links.new(maior_que_node.inputs["A"], sample_index_node.outputs[0])
        group.links.new(store_named_attribute_has_shadow_node.inputs[0], input_node.outputs["Geometry"])
        group.links.new(store_named_attribute_has_shadow_node.inputs[3], maior_que_node.outputs["Result"])
        group.links.new(output_node.inputs["Geometry"], store_named_attribute_has_shadow_node.outputs[0])

        return group

    bpy.ops.object.mode_set(mode='OBJECT')

    # modifier node
    node_group = makeGeometryNode()
    modifier = obj.modifiers.new(name=f"{obj.name}_GN_modifier", type="NODES")
    modifier.node_group = node_group

    obj_eval = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())

    faces = [(face.index, obj_eval.data.attributes[ATTRIBUTE_FACE_HAS_SHADOW_NAME].data[face.index].value) for face in obj_eval.data.polygons]

    # clean
    modifier.node_group = None

    obj.modifiers.remove(modifier)

    if node_group.users == 0:
        bpy.data.node_groups.remove(node_group)

    bpy.ops.object.mode_set(mode='EDIT')

    return faces

def group_connected_faces(bm, face_indices):
    bm.faces.ensure_lookup_table()

    input_indices = set(face_indices)
    visited = set()
    groups = []

    for f_idx in face_indices:
        if f_idx not in visited:
            current_group = []
            queue = [bm.faces[f_idx]]
            visited.add(f_idx)

            while queue:
                face = queue.pop(0)
                current_group.append(face.index)

                for edge in face.edges:
                    for linked_face in edge.link_faces:
                        if linked_face.index in input_indices and linked_face.index not in visited:
                            visited.add(linked_face.index)
                            queue.append(linked_face)
            
            groups.append(current_group)
    
    return groups

def generate_shadowmap(proxy, elements, type, model, arm_obj, vertexes_map, uvs_map):
    RES = 256
    UNITS_PER_PIXEL = 32 
    MAX_AREA = (RES * UNITS_PER_PIXEL) ** 2 / 1000
    RES_TEMP = 2048

    proxy.visible_camera = True

    if type > 0:
        proxy.visible_diffuse = False
        proxy.visible_glossy = False
        proxy.visible_transmission = False
        proxy.visible_volume_scatter = False

    # Esse é ultilizado nos tipos 1 e 2, o 0 global tem que pegar a sombra do próprio objeto
    if type == 0:
        proxy.is_shadow_catcher = False
        proxy.visible_shadow = True
    elif type in (1, 2):
        proxy.is_shadow_catcher = True
        proxy.visible_shadow = False

    # deixa só os elementos por tipo e os elementos que tenha sombra na opção (Ex: elemento parado sem animação etc)
    anim_flag = ElementOptionAnimateFlag.from_value(0)
    for el in elements:
        # esconde por padrão
        el.hide_set(True)
        el.hide_render = True

        if el.get("course_type") == type:

            # aqui verifica a opção de sombra do elemento
            anim_flag.anim1 = int(ifnull(el.get("opt_anim1"), 0))
            anim_flag.anim2 = int(ifnull(el.get("opt_anim2"), 0))
            anim_flag.anim3 = int(ifnull(el.get("opt_anim3"), 0))

            # exibe se tem sombra
            if anim_flag.is_shadow():
                el.hide_set(False)
                el.hide_render = False

            # Nas collision do model em script tem a opção *no_shadow com o aabb para não desenhar a sombra
            # Vai ser difícil fazer no blender, mais fácil deixa o objeto oculto na hora de gerar a sombra, perde a sombra toda já que com o aabb era só uma região
            collisions_obj = next((x for x in next((arm.children for arm in el.children if arm.type == "ARMATURE"), []) if "Collisions" in x.name), None)
            if (collisions_obj and len(collisions_obj.children) > 0 and
                any(["no_shadow" in (ifnull(collision.get("script02"), '') + ifnull(collision.get("script03"), '')) for collision in collisions_obj.children])):
                el.hide_set(True)
                el.hide_render = True

    
    if type in (1, 2) and len([el for el in elements if not el.hide_render]) == 0:
        print(f"Não tem nenhum item para desenhar a sombra no tipo: {type}")

        # collected data empty
        return {}

    # limpa os materias
    proxy.data.materials.clear()
    
    for l in proxy.data.uv_layers:
        proxy.data.uv_layers.remove(l)
    
    proxy.data.uv_layers.new(name="UVMapTest")
    proxy.data.uv_layers.active_index = proxy.data.uv_layers.find("UVMapTest")
    proxy.data.uv_layers["UVMapTest"].active_render = True
    
    proxy.data.uv_layers.new(name="UVMap")
    proxy.data.uv_layers["UVMap"].active_render = False
    
    base_mat = bpy.data.materials.new(name="Full_Light_Mat")
    if bpy.app.version < (5, 0, 0):
        base_mat.use_nodes = True
    proxy.data.materials.append(base_mat)
    
    # Sombra global (Mapeamento Rápido)
    print("Mapeando áreas de sombra...")
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')

    def makeUnwrap(temp=False):
        bpy.context.view_layer.update()

        mo = proxy.matrix_world.copy()

        for i in range(3):
            proxy.scale[i] = abs(proxy.scale[i])

        window = bpy.context.window
        screen = window.screen
        area = next(a for a in screen.areas if a.type == 'VIEW_3D')
        region = next(r for r in area.regions if r.type == 'WINDOW')

        with bpy.context.temp_override(window=window, area=area, region=region):
            bpy.ops.uv.unwrap(
                method="ANGLE_BASED" if not temp else "MINIMUM_STRETCH",
                fill_holes=True,
                margin=0.05 if not temp else 0.15,
            )
        
        proxy.matrix_world = mo
    
    # Imagem temporária para o teste
    temp_img = bpy.data.images.new("Temp_Light_Map", width=RES_TEMP, height=RES_TEMP, alpha=True)
    temp_img.colorspace_settings.name = "Non-Color"
    temp_img.seam_margin = 16
    temp_img.pixels = [1.0] * (RES_TEMP * RES_TEMP * 4)
    bpy.ops.mesh.select_all(action='SELECT')
    makeUnwrap(True)
    
    # Nó temporário para o bake de teste
    for mat in proxy.data.materials:
        node = mat.node_tree.nodes.new('ShaderNodeTexImage')
        node.image = temp_img
        node.interpolation = 'Linear'
        mat.node_tree.nodes.active = node
        mat.node_tree.nodes[0].inputs["Base Color"].default_value = (1, 1, 1, 1)

    def makeBake(uvmap, clean=False):
        btype = "SHADOW"
        if clean:
            btype = "DIFFUSE"
        elif type == 0:
            btype = "COMBINED"

        bfilter = {"NONE"}
        if clean:
            bfilter = {"COLOR"}
        elif type == 0:
            bfilter = {"DIRECT", "DIFFUSE", "GLOSSY", "TRANSMISSION", "EMIT"}

        bpy.ops.object.bake(
            type=btype,
            pass_filter=bfilter,
            margin=32,
            margin_type="EXTEND",
            target="IMAGE_TEXTURES",
            save_mode="INTERNAL",
            use_clear=True,
            uv_layer=uvmap
        )

    makeBake("UVMapTest")

    img_tmp = temp_img

    temp_img2 = None
    if type == 0:
        def makeNodeGroupCleanGrayImage():
            group_name = "CLEAN_GRAY_COLOR_FILTER_NODE_GROUP_NAME"

            if group_name in bpy.data.node_groups:
                return bpy.data.node_groups[group_name]
    
            group = bpy.data.node_groups.new(group_name, "ShaderNodeTree")

            if bpy.app.version < (4, 0, 0):
                group.inputs.new("NodeSocketColor", "Color")
                group.outputs.new("NodeSocketColor", "Color")
            else:
                group.interface.new_socket(name="Color", in_out="INPUT", socket_type="NodeSocketColor")
                group.interface.new_socket(name="Color", in_out="OUTPUT", socket_type="NodeSocketColor")

            nodes = group.nodes
            input_node = nodes.new("NodeGroupInput")
            output_node = nodes.new("NodeGroupOutput")

            # gray node
            gray_node = nodes.new("ShaderNodeRGBToBW")
            gray_node.location[1] = output_node.location[1]

            # gamma node
            gamma_node = nodes.new("ShaderNodeGamma")
            gamma_node.location[1] = output_node.location[1]
            gamma_node.inputs[1].default_value = 50.0

            group.links.new(gray_node.inputs["Color"], input_node.outputs["Color"])
            group.links.new(gamma_node.inputs["Color"], gray_node.outputs[0])

            group.links.new(output_node.inputs["Color"], gamma_node.outputs["Color"])

            return group

        node_group = None
        for mat in proxy.data.materials:
            node = mat.node_tree.nodes.active
            if not node or node.type != "TEX_IMAGE" and not node.image and node.image != temp_img:
                node = next((n for n in mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image and n.image == temp_img), None)
                if not node:
                    continue

            node_group = makeNodeGroupCleanGrayImage()
            group_node = mat.node_tree.nodes.new("ShaderNodeGroup")
            group_node.node_tree = node_group

            mat.node_tree.links.new(group_node.inputs["Color"], node.outputs["Color"])
            mat.node_tree.links.new(mat.node_tree.nodes[0].inputs["Base Color"], group_node.outputs["Color"])

            temp_img2 = bpy.data.images.new("Temp_Light_Map_Clean", width=RES_TEMP, height=RES_TEMP, alpha=True)
            temp_img2.colorspace_settings.name = "Non-Color"
            temp_img2.seam_margin = 16
            temp_img2.pixels = [1.0] * (RES_TEMP * RES_TEMP * 4)
            node = mat.node_tree.nodes.new('ShaderNodeTexImage')
            node.image = temp_img2
            node.interpolation = 'Linear'
            mat.node_tree.nodes.active = node
            img_tmp = temp_img2
        if temp_img2:
            makeBake("UVMapTest", True)
        if node_group:
            bpy.data.node_groups.remove(node_group)

    faces = GetFacesWithShadow(proxy, img_tmp, type)

    shadow_faces = []
    bm = bmesh.from_edit_mesh(proxy.data)
    for face in bm.faces:
        if next((v for (f_idx, v) in faces if f_idx == face.index and v), False):
            shadow_faces.append(face)
        else:
            face.material_index = 0

    # Limpar nós temporários
    for mat in proxy.data.materials:
        for node in [n for n in mat.node_tree.nodes if n.type == "GROUP" or (n.type == "TEX_IMAGE" and n.image and n.image in (temp_img, temp_img2))]:
            mat.node_tree.nodes.remove(node)
        mat.node_tree.nodes.active = None

    if temp_img2:
        bpy.data.images.remove(temp_img2)

    # Agrupamento Denso por Área
    accumulated_area = 0
    mat_count = 0
    
    def add_shadow_mat(idx):
        mat = bpy.data.materials.new(name=f"Shadow_Atlas_{idx}")
        if bpy.app.version < (5, 0, 0):
            mat.use_nodes = True
        img = bpy.data.images.new(f"T_Shadow_Atlas_{idx}", width=RES, height=RES, alpha=True)
        img.colorspace_settings.name = "Non-Color"
        img.seam_margin = 16
        img.pixels = [1.0] * (RES * RES * 4)
        img["toSave"] = True
        node = mat.node_tree.nodes.new('ShaderNodeTexImage')
        node.image = img
        node.interpolation = 'Linear'
        mat.node_tree.nodes.active = node
        mat.node_tree.nodes[0].inputs["Base Color"].default_value = (1, 1, 1, 1)
        proxy.data.materials.append(mat)
        return len(proxy.data.materials) - 1

    current_mat_idx = add_shadow_mat(mat_count)

    group_faces = group_connected_faces(bm, [f.index for f in shadow_faces])
    for g in group_faces:
        for f_idx in g:
            face = next((sf for sf in shadow_faces if sf.index == f_idx), None)
            if not face:
                continue
            f_area = face.calc_area()
            if (accumulated_area + f_area) > MAX_AREA:
                mat_count += 1
                accumulated_area = 0
                current_mat_idx = add_shadow_mat(mat_count)
        
            face.material_index = current_mat_idx
            accumulated_area += f_area

    bmesh.update_edit_mesh(proxy.data)
    
    proxy.data.uv_layers.active_index = proxy.data.uv_layers.find("UVMap")
    proxy.data.uv_layers["UVMap"].active_render = True
    proxy.data.uv_layers["UVMapTest"].active_render = False

    # Unwrap Real e Bake Final
    for i in range(1, len(proxy.data.materials)):
        bpy.ops.mesh.select_all(action='DESELECT')
        for f in bm.faces:
            if f.material_index == i: f.select = True
        bmesh.update_edit_mesh(proxy.data)
        makeUnwrap()

    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    print(f"Bake Final: {mat_count + 1} atlas densos.")

    makeBake("UVMap")

    # link textures
    for mat in proxy.data.materials:
        node = mat.node_tree.nodes.active
        if not node or node.type != "TEX_IMAGE":
            node = next((n for n in mat.node_tree.nodes if n.type == "TEX_IMAGE"), None)
            if not node:
                continue
        mat.node_tree.links.new(mat.node_tree.nodes[0].inputs["Base Color"], node.outputs["Color"])

    # remove as imagens que não tem sombra
    mats_to_remove = []

    for i in range(1, len(proxy.data.materials)):
        mat = proxy.data.materials[i]
        img = next((n.image for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image), None)
        if not img:
            continue

        pxls = np.array(img.pixels)

        if np.min(pxls.reshape(-1, 4)[:, :3]) > 0.95:
            for poly in proxy.data.polygons:
                if poly.material_index == i:
                    poly.material_index = 0
                
            print("removendo material que a imagem está toda branca, sem sombra: %s" % mat.name)

            mats_to_remove.append(mat)

    # Limpeza de dados órfãos
    for mat in mats_to_remove:
        img_to_del = next((n.image for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image), None)
        
        idx = proxy.data.materials.find(mat.name)
        if idx != -1:
            proxy.data.materials.pop(index=idx)
        
        if img_to_del:
            bpy.data.images.remove(img_to_del)
        
        bpy.data.materials.remove(mat)
    
    # bake with texture images clean
    if type == 0:
        def makeNodeGroupCleanImage():
            group_name = "CLEAN_COLOR_FILTER_NODE_GROUP_NAME"

            if group_name in bpy.data.node_groups:
                return bpy.data.node_groups[group_name]
    
            group = bpy.data.node_groups.new(group_name, "ShaderNodeTree")

            if bpy.app.version < (4, 0, 0):
                group.inputs.new("NodeSocketColor", "Color")
                group.outputs.new("NodeSocketColor", "Color")
            else:
                group.interface.new_socket(name="Color", in_out="INPUT", socket_type="NodeSocketColor")
                group.interface.new_socket(name="Color", in_out="OUTPUT", socket_type="NodeSocketColor")

            nodes = group.nodes
            input_node = nodes.new("NodeGroupInput")
            output_node = nodes.new("NodeGroupOutput")

            # gray node
            gray_node = nodes.new("ShaderNodeRGBToBW")
            gray_node.location[1] = output_node.location[1]

            # brightness contrast node
            #brightness_contrast_node = nodes.new("ShaderNodeBrightContrast")
            #brightness_contrast_node.location[1] = output_node.location[1]
            #brightness_contrast_node.inputs[1].default_value = 0.15
            #brightness_contrast_node.inputs[2].default_value = 0.25

            group.links.new(gray_node.inputs["Color"], input_node.outputs["Color"])
            #group.links.new(brightness_contrast_node.inputs["Color"], gray_node.outputs[0])

            group.links.new(output_node.inputs["Color"], gray_node.outputs[0])

            return group

        node_group = None
        for idx,mat in enumerate(proxy.data.materials):
            node = mat.node_tree.nodes.active
            if not node or node.type != "TEX_IMAGE":
                node = next((n for n in mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image), None)
                if not node:
                    continue

            node_group = makeNodeGroupCleanImage()
            group_node = mat.node_tree.nodes.new("ShaderNodeGroup")
            group_node.node_tree = node_group

            mat.node_tree.links.new(group_node.inputs["Color"], node.outputs["Color"])
            mat.node_tree.links.new(mat.node_tree.nodes[0].inputs["Base Color"], group_node.outputs["Color"])

            node.image["toSave"] = False

            img = bpy.data.images.new(f"T_Shadow_Atlas_Clean_{idx}", width=RES, height=RES, alpha=True)
            img.colorspace_settings.name = "Non-Color"
            img.seam_margin = 16
            img.pixels = [1.0] * (RES * RES * 4)
            img["toSave"] = True
            node = mat.node_tree.nodes.new('ShaderNodeTexImage')
            node.image = img
            node.interpolation = 'Linear'
            mat.node_tree.nodes.active = node
        makeBake("UVMap", True)
        if node_group:
            bpy.data.node_groups.remove(node_group)

    collected_data = collect_shadowmap_data(proxy, model, arm_obj, vertexes_map, uvs_map)

    # clean temp image
    bpy.data.images.remove(temp_img)
    
    # clean materials
    for mat in proxy.data.materials:
        for n in mat.node_tree.nodes:
            if n.type == 'TEX_IMAGE' and n.image:
                bpy.data.images.remove(n.image)
            mat.node_tree.nodes.remove(n)
        bpy.data.materials.remove(mat)
    proxy.data.materials.clear()

    return collected_data

def generate_data_and_make_sbin(obj_original, version, model, arm_obj, elements, global_light):
    COLL_NAME = 'baked shadowmap'

    if not obj_original or obj_original.type != 'MESH': return

    # monta ambiente
    bpy.context.view_layer.objects.active = obj_original
    obj_original.select_set(True)

    bpy.ops.object.mode_set(mode='OBJECT')
    
    # Cria uma nova sena
    curr_scene = bpy.context.scene
    bpy.ops.scene.new(type='EMPTY')
    bpy.context.scene.name = 'scene-baked'
    scene = bpy.context.scene
    
    bpy.context.scene.collection.children.link(obj_original.users_collection[0])
    
    # Preparação
    curr_engine = scene.render.engine
    scene.render.engine = 'CYCLES'
    scene.cycles.use_denoising = True
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.01
    scene.cycles.samples = 2048
    
    # Criar Coleção e Cópia
    coll = bpy.data.collections.new(COLL_NAME)
    scene.collection.children.link(coll)

    # Criar cópia do global light
    global_light_cpy = global_light.copy()
    global_light_cpy.data = global_light.data.copy()
    coll.objects.link(global_light_cpy)

    global_light_cpy.data.color = (1.0, 1.0, 1.0)
    global_light_cpy.data.diffuse_factor = 1.0

    emit_node = next((n for n in global_light_cpy.data.node_tree.nodes if n.type == "EMISSION"), None)
    if emit_node:
        emit_node.inputs[0].default_value = (1, 1, 1, 1)
        emit_node.inputs[1].default_value = 3.0

    global_light_cpy.hide_set(False)
    global_light_cpy.hide_render = False

    # hide original global light
    global_light.hide_render = True

    proxy = obj_original.copy()
    proxy.data = obj_original.data.copy()
    proxy.name = f"Atlas_{obj_original.name}"
    coll.objects.link(proxy)
    bpy.context.view_layer.objects.active = proxy
    proxy.select_set(True)
    proxy.hide_set(False)
    proxy.hide_render = False
    
    # hide original object
    obj_original.hide_set(True)
    obj_original.hide_render = True

    vertexes_map = defaultdict(dict)
    uvs_map = defaultdict(dict)
    collected_datas = []
    
    for type in range(3):
        collected_datas.append([
            type,
            generate_shadowmap(
                proxy,
                elements,
                type,
                model,
                arm_obj,
                vertexes_map,
                uvs_map
            )
        ])
    
    # make sbin
    sbin_bones = {}

    for type, sbin_bones_data in collected_datas:
        for (bone_name, data) in sbin_bones_data.items():
            sbin_bone = sbin_bones.get(bone_name)
            if not sbin_bone:
                sbin_bones[bone_name] = SBinBone(bone_name, SBin(
                    InFragMesh(
                        data.mesh_info,
                        list(vertexes_map[bone_name].values()),
                        list(uvs_map[bone_name].values()),
                        -1,         # -1 para o save calcular o size do global
                        [-1] * 2,   # -1 para o save calcular o size do type[1..2]
                        data.textures[:] if type == 0 else [],
                        ([data.textures[:] if type == i else [] for i in (1, 2)]) if type in (1, 2) else [[] for _ in range(2)]
                    ),
                    # Aqui é o que tirar quando tem triângulos(faces) novos no meio dos triângulos antigos.
                    # Como eu uso os triângulos do original então o outfrag é vazio já que não tem triângulos novos.
                    OutFragMesh(
                        [],
                        [[] for _ in range(2)],
                        [],
                        [[] for _ in range(2)]
                    )
                ))
            else:
                if type == 0:
                    sbin_bone.sbin.in_frag_mesh.texture_globals.extend(data.textures[:])
                elif type in (1, 2):
                    sbin_bone.sbin.in_frag_mesh.texture_types[type - 1].extend(data.textures[:])
    
    sbin = SBinCtx(version, list(sbin_bones.values()))

    # show original object
    obj_original.hide_set(False)
    obj_original.hide_render = False

    # show original global light
    global_light.hide_render = False
    
    scene.render.engine = curr_engine
    
    # clean new scene and collections with your children
    for ob in coll.all_objects:
        if ob.type == 'MESH':
            for mat in ob.data.materials:
                for n in mat.node_tree.nodes:
                    if n.type == 'TEX_IMAGE' and n.image:
                        bpy.data.images.remove(n.image)
                    mat.node_tree.nodes.remove(n)
                bpy.data.materials.remove(mat)
            ob.data.materials.clear()
            bpy.data.meshes.remove(ob.data)
        elif ob.type == 'LIGHT':
            bpy.data.lights.remove(ob.data)
        if is_valid_object(ob):
            bpy.data.objects.remove(ob)
    bpy.data.collections.remove(coll) 

    # show curr scene
    bpy.context.window.scene = curr_scene

    # scene
    bpy.data.scenes.remove(scene)

    return sbin

def save_sbin(file, obj_base_element, version, collection):
    # Save PangYa SBIN

    if not obj_base_element:
        raise Exception("Invalid gbin base elemenet object")

    obj_filepath = "{}/{}".format(obj_base_element["directory"], remove_unique_name(obj_base_element.name))
    
    model = load_saved_model(obj_filepath)

    if not model:
        raise Exception("Não conseguiu abrir o modelo %s do objeto base element" % obj_filepath)

    armature_obj = next((x.object for x in obj_base_element.modifiers if x.type == 'ARMATURE'), None)

    if not armature_obj:
        raise Exception("Objeto não tem uma armação")

    # Elements
    coll_elements = next((coll for coll in collection.children if "Elements" in coll.name), None)

    if not coll_elements:
        raise Exception("Não tem o collection dos elementos")

    elements = [obj for obj in coll_elements.objects if obj.type == 'MESH' and '.pet' in obj.name]

    # Global Light
    # Lights
    coll_lights = next((coll for coll in collection.children if "Lights" in coll.name), None)

    if not coll_lights:
        raise Exception("Não tem o collection dos lights")
    
    global_light = next((light for light in coll_lights.objects if light.type == "LIGHT" and "type" in light and light.get("type") == 1), None)

    if not global_light:
        raise Exception("Não tem global light")

    # Version
    major, minor = zip(version.split(','))
    version = Version(int(major[0]), int(minor[0]))

    # generate data and make sbin
    sbin = generate_data_and_make_sbin(obj_base_element, version, model, armature_obj, elements, global_light)

    # save sbin
    sbin.save(file)

def save(filepath, obj_base_element, version, collection):

    print('export pangya SBIN: %r' % (filepath))

    time1 = time.process_time()

    with open(filepath, 'wb') as file:
        save_sbin(file, obj_base_element, version, collection)

    print('export pangya SBIN done in %.4f sec.' % (time.process_time() - time1))