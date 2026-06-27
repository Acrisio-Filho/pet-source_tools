# Copyright 2023-2026 Acrisio Filho

from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

import os
import time

from collections import defaultdict, OrderedDict
from mathutils import Matrix, Vector # pyright: ignore[reportMissingImports]

from .gbin import GBin
from . import export_sbin
from .texture_util import isBaseTexture
from .util import (
    make4x3FromMatrix,
    ifnull,
    remove_unique_name,
    calcule_bound_box,
    calcule_bound_box_fit_base_model,
    get_face_all_index_of_vertex_pangya_by_material_same_bone_from_model,
    get_face_index_of_vertex_pangya_by_material_same_bone_from_model,
    get_mesh_material_list_by_bone_from_model,
    vertex_color_blender_to_pangya,
    getNewGUID,
    load_saved_model,
    is_valid_object
)

from .gbin import (
    BaseElement,
    Element,
    Camera,
    Light,
    SoundBox,
    Node,
    Texture,
    AABB,
    MapCheck,
    NewElementV72,
    ExtraValueV72,
    VERSION_72,
    ElementOptionFlag,
    ElementOptionAnimateFlag,
    ElementOptionCollisionFlag
)

def save_gbin(context, file, setting, matrix):
    # Save PangYa GBIN

    # str to int
    version = int(setting.version)

    is_gbin = True if setting.filename_ext == '.gbin' else False
    is_sgbin = True if setting.filename_ext == '.sgbin' else False
    is_aibin = True if setting.filename_ext == '.aibin' else False
    is_sbin = True if setting.filename_ext == '.sbin' else False

    if not is_gbin and not is_sgbin and not is_aibin and not is_sbin:
        raise Exception("Formato de arquivo inválido")

    if (is_sgbin or is_aibin) and version != VERSION_72:
        raise Exception("Versão selecionada é inválida para .sgbin e .aibin")

    collection = context.collection

    if not collection:
        raise Exception("Collection gbin don't selected")

    # set element object option
    def getElementObjectOption(obj):
        option = ElementOptionFlag(
            ElementOptionAnimateFlag.from_value(0),
            ElementOptionCollisionFlag.from_value(0)
        )

        if not obj or not is_valid_object(obj):
            return option
        
        # flag to animate object and etc
        option.anim_flag.anim1 = 1 if ifnull(obj.get("opt_anim1"), False) else 0
        option.anim_flag.anim2 = 1 if ifnull(obj.get("opt_anim2"), False) else 0
        option.anim_flag.anim3 = 1 if ifnull(obj.get("opt_anim3"), False) else 0

        # flag to collision object and etc
        option.coll_flag.coll1 = 1 if ifnull(obj.get("opt_coll1"), False) else 0
        option.coll_flag.coll2 = 1 if ifnull(obj.get("opt_coll2"), False) else 0
        option.coll_flag.coll3 = 1 if ifnull(obj.get("opt_coll3"), False) else 0
        option.coll_flag.coll4 = 1 if ifnull(obj.get("opt_coll4"), False) else 0
        option.coll_flag.coll5 = 1 if ifnull(obj.get("opt_coll5"), False) else 0

        return option

    def getMatrixLocalFromObj(obj):
        if not obj:
            return Matrix.Identity(4)
        parent_guid = obj.get("PARENT_GUID", -1)
        if parent_guid == -1:
            return matrix @ obj.matrix_world
        parent_obj = next((ob for ob in collection.all_objects if ob.get("GUID") == parent_guid), None)
        if not parent_obj:
            return matrix @ obj.matrix_world
        return parent_obj.matrix_world.inverted() @ obj.matrix_world

    obj_base_element = None
    base_element = None
    elements = []
    cameras = []
    lights = []
    sound_boxs = []
    textures = []
    nodes = []
    new_elements = []
    map_check = None

    if is_gbin or is_sbin:
        # Base Element
        obj_base_element = next((obj for obj in collection.objects if obj.get("par_hole")), None)

        if not obj_base_element:
            raise Exception("Não tem o objeto do modelo base")

        if obj_base_element.type != 'MESH':
            raise Exception("objeto do modelo base inválido não é do tipo MESH")

        face_num = len(obj_base_element.data.polygons)

        map_color_vtx_v70 = [[0xFFFFFFFF] * 3 for i in range(face_num)]
        map_color_vtx_v72 = defaultdict(list)

        if "Col" in obj_base_element.data.color_attributes:
            obj_base_element_filepath = "{}/{}".format(obj_base_element["directory"], remove_unique_name(obj_base_element.name))

            model = load_saved_model(obj_base_element_filepath)

            if not model:
                raise Exception("Não conseguiu abrir o modelo %s do objeto base element" % obj_base_element_filepath)

            if version < VERSION_72:
                mesh_indexes, face_num_from_model = get_face_all_index_of_vertex_pangya_by_material_same_bone_from_model(model, model.bones[0].name)
                if face_num_from_model == face_num:
                    seq = 0
                    for mesh_index in mesh_indexes:
                        for poly_idx in mesh_index[1]:
                            for loop_idx in range(poly_idx, poly_idx + 3):
                                map_color_vtx_v70[seq//3][seq%3] = vertex_color_blender_to_pangya(obj_base_element.data.color_attributes["Col"].data[obj_base_element.data.loops[loop_idx].vertex_index].color)
                                seq += 1
            else:
                armature_obj = next((x.object for x in obj_base_element.modifiers if x.type == 'ARMATURE'), None)

                if not armature_obj:
                    raise Exception("Objeto não tem uma armação")
                
                for bone in armature_obj.data.bones:
                    mesh_material_list = get_mesh_material_list_by_bone_from_model(model, bone.name)

                    for material in mesh_material_list:
                        vtxColors = []
                        vertex_indexes, _ = get_face_index_of_vertex_pangya_by_material_same_bone_from_model(model, bone.name, material)
                        for vertex_index in vertex_indexes:
                            vtxColors.append(vertex_color_blender_to_pangya(obj_base_element.data.color_attributes["Col"].data[vertex_index[1]].color))
                        map_color_vtx_v72[bone.name].append(vtxColors)

                # remove empty bone vtx colors
                for bone_name, faces in list(map_color_vtx_v72.items()):
                    if len(faces) == 0:
                        del map_color_vtx_v72[bone_name]
        
        base_element = BaseElement(
            Element(
                getElementObjectOption(obj_base_element),
                face_num,
                remove_unique_name(obj_base_element.name),
                AABB(*calcule_bound_box(obj_base_element, (matrix @ obj_base_element.matrix_world), True)), # min_max(bounding box)
                AABB(*([0]*6)), # fit_base_model, não precisa no base element
                make4x3FromMatrix(matrix @ obj_base_element.matrix_world),
                int(ifnull(obj_base_element.get("course_type"), 0)),
                ifnull(obj_base_element.get("script"), ""),
                make4x3FromMatrix(getMatrixLocalFromObj(obj_base_element)),
                ExtraValueV72(
                    int(ifnull(obj_base_element.get("GUID"), getNewGUID())),
                    int(ifnull(obj_base_element.get("PARENT_GUID"), -1))
                )
            ),
            map_color_vtx_v70,
            map_color_vtx_v72
        )

        # Map Check initialize
        map_check = MapCheck(
            int(ifnull(obj_base_element.get("par_hole"), 0)),
            [[0,0] for i in range(2)],
            [[[0,0], [0,0], [0,0]] for i in range(2)]
        )
        
    if is_gbin:
        # Elements
        coll_elements = next((coll for coll in collection.children if "Elements" in coll.name), None)

        if not coll_elements:
            raise Exception("Não tem o collection dos elementos")

        for element in [obj for obj in coll_elements.objects if obj.type == 'MESH' and '.pet' in obj.name]:
            elements.append(Element(
                getElementObjectOption(element),
                len(element.data.polygons), # face_num,
                remove_unique_name(element.name),
                AABB(*calcule_bound_box(element, (matrix @ element.matrix_world), True)), # min_max(bounding box)
                AABB(*calcule_bound_box_fit_base_model(element, (matrix @ element.matrix_world), True)), # fit_base_model
                make4x3FromMatrix(matrix @ element.matrix_world),
                int(ifnull(element.get("course_type"), 0)),
                ifnull(element.get("script"), ""),
                make4x3FromMatrix(getMatrixLocalFromObj(element)),
                ExtraValueV72(
                    int(ifnull(element.get("GUID"), getNewGUID())),
                    int(ifnull(element.get("PARENT_GUID"), -1))
                )
            ))

        # Textures
        objs = [obj_base_element]
        objs.extend([obj for obj in coll_elements.objects if obj.type == 'MESH' and '.pet' in obj.name])
        text_names = []
        for obj in objs:
            for material in obj.data.materials:
                # excluí especular material
                image_path = next((os.path.basename(x.image.filepath) for x in material.node_tree.nodes if x.type == 'TEX_IMAGE' and x.image and x.image.filepath and isBaseTexture(x) and os.path.basename(x.image.filepath)[0] != '!'), None)

                text_names.append(image_path if image_path else remove_unique_name(material.name))

        # remove duplicates
        for txname in list(OrderedDict.fromkeys(text_names)):
            textures.append(Texture(txname))

        # Cameras
        coll_cameras = next((coll for coll in collection.children if "Cameras" in coll.name), None)

        if coll_cameras:
            for cam in coll_cameras.objects:
                if cam.type == "CAMERA":
                    pangya_matrix_world = (matrix @ cam.matrix_world)
                    pangya_matrix_local = getMatrixLocalFromObj(cam)
                    vpos_world = pangya_matrix_world.to_translation()
                    vpos_local = pangya_matrix_local.to_translation()
                    vdest_world = vpos_world + pangya_matrix_world.to_quaternion() @ Vector((0, 0, (cam.data.sensor_width / cam.data.lens) * 100))
                    vdest_local = vpos_local + pangya_matrix_local.to_quaternion() @ Vector((0, 0, (cam.data.sensor_width / cam.data.lens) * 100))

                    cameras.append(Camera(
                        ifnull(cam.get("name"), remove_unique_name(cam.name)),
                        (vpos_world[0], vpos_world[1], vpos_world[2]),
                        (vdest_world[0], vdest_world[1], vdest_world[2]),
                        cam.data.sensor_width,
                        cam.data.shift_y,
                        (vpos_local[0], vpos_local[1], vpos_local[2]),
                        (vdest_local[0], vdest_local[1], vdest_local[2]),
                        ExtraValueV72(
                            int(ifnull(cam.get("GUID"), getNewGUID())),
                            int(ifnull(cam.get("PARENT_GUID"), -1))
                        )
                    ))

        # Lights
        coll_lights = next((coll for coll in collection.children if "Lights" in coll.name), None)

        if coll_lights:
            for light in coll_lights.objects:
                if light.type == "LIGHT":
                    vpos_world = (matrix @ light.matrix_world).to_translation()
                    vpos_local = getMatrixLocalFromObj(light).to_translation()

                    lights.append(Light(
                        int(ifnull(light.get("type"), 0)),
                        ifnull(light.get("name"), remove_unique_name(light.name)),
                        (vpos_world[0], vpos_world[1], vpos_world[2]),
                        ifnull(light.get("data"), ""),
                        (vpos_local[0], vpos_local[1], vpos_local[2]),
                        ExtraValueV72(
                            int(ifnull(light.get("GUID"), getNewGUID())),
                            int(ifnull(light.get("PARENT_GUID"), -1))
                        )
                    ))
        
        # New Elements V72
        coll_new_elements = next((coll for coll in collection.children if "New Elements" in coll.name), None)

        if coll_new_elements:
            for new_element in coll_new_elements.objects:
                if new_element.type == "LIGHT":
                    new_elements.append(NewElementV72(
                        ExtraValueV72(
                            int(ifnull(new_element.get("GUID"), getNewGUID())),
                            int(ifnull(new_element.get("PARENT_GUID"), -1))
                        ),
                        ifnull(new_element.get("name"), remove_unique_name(new_element.name)),
                        int(ifnull(new_element.get("type"), 0)),
                        make4x3FromMatrix(matrix @ new_element.matrix_world),
                        make4x3FromMatrix(getMatrixLocalFromObj(new_element))
                    ))

    if is_gbin or is_sgbin:
        # Sound Boxs
        coll_sound_boxs = next((coll for coll in collection.children if "Sound Boxs" in coll.name), None)

        if coll_sound_boxs:
            for sound_box in coll_sound_boxs.objects:
                if sound_box.type == "MESH":
                    sound_boxs.append(SoundBox(
                        int(ifnull(sound_box.get("type"), 0)),
                        ifnull(sound_box.get("name"), remove_unique_name(sound_box.name)),
                        AABB(*calcule_bound_box(sound_box)), # min_max_world
                        AABB(*calcule_bound_box(sound_box, getMatrixLocalFromObj(sound_box), True)), # min_max_local
                        ExtraValueV72(
                            int(ifnull(sound_box.get("GUID"), getNewGUID())),
                            int(ifnull(sound_box.get("PARENT_GUID"), -1))
                        )
                    ))

    if is_gbin or is_aibin:
        # Nodes
        coll_nodes = next((coll for coll in collection.children if "Nodes" in coll.name), None)

        if coll_nodes:
            for node in coll_nodes.objects:
                if node.type == 'EMPTY' and node.empty_display_type == 'PLAIN_AXES':
                    vects = []
                    for point in sorted(node.children, key=lambda x: int(ifnull(x.get("index"), 0))):
                        if point.type == 'EMPTY' and point.empty_display_type == 'SINGLE_ARROW':
                            vpos = (matrix @ point.matrix_world).to_translation()
                            vects.append([
                                vpos[0],
                                vpos[1],
                                vpos[2]
                            ])
                    nodes.append(Node(
                        ifnull(node.get("name"), remove_unique_name(node.name)),
                        int(ifnull(node.get("type"), 0)),
                        vects
                    ))

    # MapCheck tee and pin
    if is_gbin and version < VERSION_72 and len(lights) > 0:
        tee = [[0,0] for i in range(2)]
        pin = [[[0,0], [0,0], [0,0]] for i in range(2)]
        for light in lights:
            if light.type == 0: # point
                light_name = remove_unique_name(light.name)
                if "시작점" in light_name:
                    if light_name == "시작점":
                        tee[0] = [light.vpos_world[0], light.vpos_world[2]]
                    elif light_name == "시작점2":
                        tee[1] = [light.vpos_world[0], light.vpos_world[2]]
                if "끝점" in light_name:
                    if "끝점1_" in light_name:
                        if light_name == "끝점1_1":
                            pin[0][0] = [light.vpos_world[0], light.vpos_world[2]]
                        elif light_name == "끝점1_2":
                            pin[0][1] = [light.vpos_world[0], light.vpos_world[2]]
                        elif light_name == "끝점1_3":
                            pin[0][2] = [light.vpos_world[0], light.vpos_world[2]]
                    elif "끝점2_" in light_name:
                        if light_name == "끝점2_1":
                            pin[1][0] = [light.vpos_world[0], light.vpos_world[2]]
                        elif light_name == "끝점2_2":
                            pin[1][1] = [light.vpos_world[0], light.vpos_world[2]]
                        elif light_name == "끝점2_3":
                            pin[1][2] = [light.vpos_world[0], light.vpos_world[2]]

        if not map_check:
            map_check = MapCheck(0, tee, pin)
        else:
            map_check.tee_type = tee
            map_check.pin_type = pin
    
    # cria o objeto do GBin
    gbin = GBin(
        version,
        base_element,
        elements,
        cameras,
        lights,
        sound_boxs,
        textures,
        nodes,
        new_elements,
        map_check,
    )

    # save gbin
    if not is_sbin:
        gbin.save(file)

    # save sbin
    if setting.save_sbin or is_sbin:
        export_sbin.save(
            "{}.sbin".format(os.path.splitext(file.name)[0]) if not is_sbin else file.name,
            obj_base_element,
            setting.sbin_version,
            collection
        )

def save(operator, context, matrix):

    print('export pangya GBIN: %r' % (operator.filepath))

    time1 = time.process_time()

    with open(operator.filepath, 'wb') as file:
        save_gbin(context, file, operator, matrix)

    print('export pangya GBIN done in %.4f sec.' % (time.process_time() - time1))
    
    return {'FINISHED'}