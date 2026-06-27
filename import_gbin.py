# Copyright 2023-2026 Acrisio Filho

from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

import os, pathlib, time, re, bpy # pyright: ignore[reportMissingImports]
from os.path import splitext

from math import radians
from mathutils import Matrix, Vector # pyright: ignore[reportMissingImports]

from .gbin import GBin, VERSION_72
from . import import_sbin
from .import_pet import load_pet_obj
from .texture_util import makeVertexColorFilterToMaterial
from .util import (
    makeMatrixFrom4x3,
    load_model_path,
    get_face_all_index_of_vertex_pangya_by_material_same_bone_from_model,
    get_face_index_of_vertex_pangya_by_material_same_bone_from_model,
    get_mesh_material_list_by_bone_from_model,
    vertex_color_pangya_to_blender,
    make_bbox,
    make_unique_name,
    remove_and_make_unique_name,
    is_valid_object,
    getCurrentClipEnd
)

cached_model_objs = {}
collection_tmp = None

def duplicate_model(obj, collection=None, collisionBox_show=False):
    arm_cpy = None

    obj_cpy = obj.copy()
    obj_cpy.name = remove_and_make_unique_name(obj.name)
    collection.objects.link(obj_cpy)
    obj_cpy.data = obj_cpy.data.copy()
    obj_cpy.data.name = remove_and_make_unique_name(obj.data.name)

    for child in obj.children:
        if "Specular Materials" in child.name:
            smtls_cpy = child.copy()
            smtls_cpy.name = remove_and_make_unique_name(child.name)
            collection.objects.link(smtls_cpy)
            smtls_cpy.parent = obj_cpy
            for smtl in child.children:
                smtl_cpy = smtl.copy()
                smtl_cpy.name = remove_and_make_unique_name(smtl.name)
                collection.objects.link(smtl_cpy)
                smtl_cpy.parent = smtls_cpy
                for smtlv in smtl.children:
                    smtlv_cpy = smtlv.copy()
                    smtlv_cpy.name = remove_and_make_unique_name(smtlv.name)
                    collection.objects.link(smtlv_cpy)
                    smtlv_cpy.parent = smtl_cpy

    if obj.type == 'MESH':
        armature_obj = next((x.object for x in obj.modifiers if x.type == 'ARMATURE'), None)
        if armature_obj:
            arm_cpy = armature_obj.copy()
            arm_cpy.name = remove_and_make_unique_name(armature_obj.name)
            arm_cpy.data = arm_cpy.data.copy()
            arm_cpy.data.name = remove_and_make_unique_name(armature_obj.data.name)
            collection.objects.link(arm_cpy)
            arm_cpy.parent = obj_cpy
            arm_cpy.hide_set(True)
            mod_arm = next((x for x in obj_cpy.modifiers if x.type == 'ARMATURE'), None)
            if mod_arm:
                mod_arm.object = arm_cpy
            if arm_cpy.animation_data:
                arm_cpy.animation_data.action = arm_cpy.animation_data.action.copy()
                arm_cpy.animation_data.action.name = remove_and_make_unique_name(armature_obj.animation_data.action.name)
            for child in armature_obj.children:
                if "Extras" in child.name:
                    exts_cpy = child.copy()
                    exts_cpy.name = remove_and_make_unique_name(child.name)
                    collection.objects.link(exts_cpy)
                    exts_cpy.parent = arm_cpy
                    for extra in child.children:
                        ext_cpy = extra.copy()
                        ext_cpy.name = remove_and_make_unique_name(extra.name)
                        collection.objects.link(ext_cpy)
                        ext_cpy.parent = exts_cpy
                elif "Collisions" in child.name:
                    colls_cpy = child.copy()
                    colls_cpy.name = remove_and_make_unique_name(child.name)
                    collection.objects.link(colls_cpy)
                    colls_cpy.parent = arm_cpy
                    for collision in child.children:
                        coll_cpy = collision.copy()
                        coll_cpy.name = remove_and_make_unique_name(collision.name)
                        coll_cpy.data = coll_cpy.data.copy()
                        coll_cpy.data.name = remove_and_make_unique_name(collision.data.name)
                        collection.objects.link(coll_cpy)
                        coll_cpy.parent = colls_cpy
                        coll_cpy.hide_set(not collisionBox_show)
                        coll_mod_arm = next((x for x in coll_cpy.modifiers if x.type == 'ARMATURE'), None)
                        if coll_mod_arm:
                            coll_mod_arm.object = arm_cpy
                elif "Frames" in child.name:
                    frames_cpy = child.copy()
                    frames_cpy.name = remove_and_make_unique_name(child.name)
                    collection.objects.link(frames_cpy)
                    frames_cpy.parent = arm_cpy
                    for frame in child.children:
                        frame_cpy = frame.copy()
                        frame_cpy.name = remove_and_make_unique_name(frame.name)
                        collection.objects.link(frame_cpy)
                        frame_cpy.parent = frames_cpy
                elif "Motions" in child.name:
                    motions_cpy = child.copy()
                    motions_cpy.name = remove_and_make_unique_name(child.name)
                    collection.objects.link(motions_cpy)
                    motions_cpy.parent = arm_cpy
                    for motion in child.children:
                        motion_cpy = motion.copy()
                        motion_cpy.name = remove_and_make_unique_name(motion.name)
                        collection.objects.link(motion_cpy)
                        motion_cpy.parent = motions_cpy

    return obj_cpy, arm_cpy

def load_model(context, dirname, filename, matrix, matrix_model, setting, model_option, collection=None):

    model_obj = None
    model = None
    armature_obj = None

    cached_obj = cached_model_objs.get(filename)

    # cached
    if cached_obj:
        model_obj, model = cached_obj

        model_obj, armature_obj = duplicate_model(model_obj, collection, setting.collisionBox_show)
        
        model_obj.matrix_world @= matrix_model

        return model_obj, model, armature_obj

    # open model
    model_path = load_model_path(dirname, filename)
    if pathlib.Path(model_path).exists():
        print('importing pangya model: %r' % (model_path))

        time1 = time.process_time()

        anim_enable = setting.anim_enable

        # elemento tem sua própria animação carregar 1 frame pelo menos para a geração de sombra
        if model_option.anim_flag.is_animate():
            # carrega a animação pelo menos 1 frame
            anim_enable = True
        elif model_option.anim_flag.is_freeze():
            # desabilita a animação por que o objeto está congelado
            anim_enable = False

        with open(model_path, "rb") as file:
            model_obj, model = load_pet_obj(
                context,
                file,
                matrix,
                setting.collisionBox_enable,
                setting.collisionBox_show,
                anim_enable,
                setting.specular_material_filter_enable,
                collection_tmp
            )

        print('import pangya model done in %.4f sec.' % (time.process_time() - time1))

    if model_obj and model:
        cached_model_objs[filename] = [model_obj, model]

        model_obj, armature_obj = duplicate_model(model_obj, collection, setting.collisionBox_show)

        model_obj.matrix_world @= matrix_model

    return model_obj, model, armature_obj
    
def load_gbin(context, file, matrix, setting):
    dirname = os.path.dirname(file.name)
    filename = os.path.basename(file.name)
    
    gbin = GBin()
    gbin.load(file)

    # Collection
    collection = bpy.data.collections.new(make_unique_name(filename))
    if bpy.app.version >= (2, 9, 1):
        collection.color_tag = 'COLOR_08'

    context.scene.collection.children.link(collection)

    # collection temp to cached models
    global collection_tmp, cached_model_objs
    cached_model_objs = {}
    collection_tmp = bpy.data.collections.new(make_unique_name("tmp_" + filename))
    collection.children.link(collection_tmp)

    # set element object option
    def setElementObjectOption(obj, option):
        if not obj or not is_valid_object(obj):
            return
        
        # flag to animate object and etc
        obj["opt_anim1"] = True if option.anim_flag.anim1 > 0 else False
        obj["opt_anim2"] = True if option.anim_flag.anim2 > 0 else False
        obj["opt_anim3"] = True if option.anim_flag.anim3 > 0 else False

        # flag to collision object and etc
        obj["opt_coll1"] = True if option.coll_flag.coll1 > 0 else False
        obj["opt_coll2"] = True if option.coll_flag.coll2 > 0 else False
        obj["opt_coll3"] = True if option.coll_flag.coll3 > 0 else False
        obj["opt_coll4"] = True if option.coll_flag.coll4 > 0 else False
        obj["opt_coll5"] = True if option.coll_flag.coll5 > 0 else False

    # set parent by GUID and parent GUID from object
    def setParentByGUIDAndParentGUIDFromObj(obj):
        if not obj:
            return
        parent_guid = obj.get("PARENT_GUID", -1)
        if parent_guid == -1 or obj.get("PARENT_SETED"):
            return
        parent_obj = next((ob for ob in collection.all_objects if ob.get("GUID") == parent_guid), None)
        if parent_obj:
            # set parent of parent
            setParentByGUIDAndParentGUIDFromObj(parent_obj)

            obj.matrix_world = (parent_obj.matrix_world @ matrix.inverted()) @ (obj.matrix_world @ matrix.inverted())
            obj.matrix_world @= matrix

            constraint = obj.constraints.new(type="CHILD_OF")
            constraint.target = parent_obj
            constraint.subtarget = next((x.object.data.bones[0].name for x in parent_obj.modifiers if x.type == 'ARMATURE'), '')

            obj["PARENT_SETED"] = True

    # import base model
    if setting.load_base_element and gbin.base_element:
        base_model_obj, base_model, armature_obj = load_model(
            context,
            dirname,
            gbin.base_element.element.name,
            matrix,
            makeMatrixFrom4x3(gbin.base_element.element.matrix_local),
            setting,
            gbin.base_element.element.option,
            collection
        )
        if base_model_obj:
            base_model_obj["par_hole"] = gbin.map_check.par_hole
            base_model_obj["GUID"] = gbin.base_element.element.extra_value.guid
            base_model_obj["PARENT_GUID"] = gbin.base_element.element.extra_value.parent_guid
            setElementObjectOption(base_model_obj, gbin.base_element.element.option)
            base_model_obj["course_type"] = gbin.base_element.element.course_type # type[0], type[1] (1 - Blue Lagoon, 2 - Blue Water)
            base_model_obj["script"] = gbin.base_element.element.script # used in portals, values to warp ball trajectory

            # vertex color - Color Attributes
            for color_attr in list(base_model_obj.data.color_attributes):
                base_model_obj.data.color_attributes.remove(color_attr)

            base_model_obj.data.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="POINT")
            base_model_obj.data.color_attributes.active_index = 0
            base_model_obj.data.color_attributes.active_color_index = 0
            base_model_obj.data.color_attributes.render_color_index = 0

            base_model_obj.data.color_attributes["Col"].data.foreach_set("color", (1,1,1,1) * len(base_model_obj.data.vertices))
            
            if gbin.base_element.element.face_num == len(base_model_obj.data.polygons):
                if gbin.version < VERSION_72:
                    mesh_indexes, face_num = get_face_all_index_of_vertex_pangya_by_material_same_bone_from_model(base_model, base_model.bones[0].name)
                    if face_num == gbin.base_element.element.face_num:
                        seq = 0
                        for mesh_index in mesh_indexes:
                            for poly_idx in mesh_index[1]:
                                for loop_idx in range(poly_idx, poly_idx + 3):
                                    base_model_obj.data.color_attributes["Col"].data[base_model_obj.data.loops[loop_idx].vertex_index].color = vertex_color_pangya_to_blender(gbin.base_element.map_color_vtx_v70[seq//3][seq%3])
                                    seq += 1
                elif len(gbin.base_element.map_color_vtx_v72) > 0:

                    for bone_name, faces in gbin.base_element.map_color_vtx_v72.items():
                        mesh_material_list = get_mesh_material_list_by_bone_from_model(base_model, bone_name)

                        bone = armature_obj.data.bones.get(bone_name)
                        if not bone or len(faces) != len(mesh_material_list):
                            continue

                        # reverse
                        for idx, face in enumerate(faces):
                            vertex_indexes, _ = get_face_index_of_vertex_pangya_by_material_same_bone_from_model(base_model, bone_name, mesh_material_list[idx])
                            vtxNum = len(face)
                            if len(vertex_indexes) == vtxNum:
                                for i in range(vtxNum):
                                    base_model_obj.data.color_attributes["Col"].data[vertex_indexes[i][1]].color = vertex_color_pangya_to_blender(face[i])
            
            # apply vertex color filter shading
            if setting.vertex_color_filter_enable:
                for mat in base_model_obj.data.materials:
                    makeVertexColorFilterToMaterial(mat)

            # load sbin
            if setting.load_sbin:
                sbin_obj, sbin = import_sbin.load(
                    "{}.sbin".format(splitext(file.name)[0]),
                    base_model,
                    base_model_obj,
                    armature_obj,
                    matrix
                )

    # import models
    if setting.load_elements and len(gbin.elements) > 0:
        models_coll = bpy.data.collections.new(make_unique_name("Elements"))
        if bpy.app.version >= (2, 9, 1):
            models_coll.color_tag = 'COLOR_05'
        collection.children.link(models_coll)
        for i in range(len(gbin.elements)):
            model_obj, model, armature_obj = load_model(
                context,
                dirname, gbin.elements[i].name,
                matrix,
                makeMatrixFrom4x3(gbin.elements[i].matrix_local),
                setting,
                gbin.elements[i].option,
                models_coll
            )
            if model_obj:
                model_obj["GUID"] = gbin.elements[i].extra_value.guid
                model_obj["PARENT_GUID"] = gbin.elements[i].extra_value.parent_guid
                setElementObjectOption(model_obj, gbin.elements[i].option)
                model_obj["course_type"] = gbin.elements[i].course_type # type[0], type[1] (1 - Blue Lagoon, 2 - Blue Water)
                model_obj["script"] = gbin.elements[i].script # used in portals, values to warp ball trajectory
        
    # import cameras
    if setting.load_cameras and len(gbin.cameras) > 0:
        cameras_coll = bpy.data.collections.new(make_unique_name("Cameras"))
        if bpy.app.version >= (2, 9, 1):
            cameras_coll.color_tag = 'COLOR_03'
        collection.children.link(cameras_coll)
        for camera in gbin.cameras:
            cam = bpy.data.cameras.new(make_unique_name(camera.name))
            cam.lens = 50
            cam.sensor_width = camera.fov
            cam.shift_y = camera.bank

            # atualiza limite de visualização da câmera para o maior limite atual
            cam.clip_end = max(cam.clip_end, getCurrentClipEnd())

            cam_obj = bpy.data.objects.new(make_unique_name(camera.name), cam)
            cameras_coll.objects.link(cam_obj)

            cam_obj["name"] = camera.name
            cam_obj.location = (matrix @ Matrix.Translation(Vector((camera.vpos_local[0], camera.vpos_local[1], camera.vpos_local[2])))).to_translation()
            cam_obj.rotation_mode = 'XYZ'
            cam_obj.rotation_euler = (cam_obj.location - (matrix @ Matrix.Translation(Vector((camera.vdest_local[0], camera.vdest_local[1], camera.vdest_local[2])))).to_translation()).to_track_quat('Z', 'Y').to_euler()

            cam_obj["GUID"] = camera.extra_value.guid
            cam_obj["PARENT_GUID"] = camera.extra_value.parent_guid

            cam_obj.hide_render = True

    # import lights
    if setting.load_lights and len(gbin.lights) > 0:
        lights_coll = bpy.data.collections.new(make_unique_name("Lights"))
        if bpy.app.version >= (2, 9, 1):
            lights_coll.color_tag = 'COLOR_04'
        collection.children.link(lights_coll)
        for light in gbin.lights:
            luz = None
            light_name = "global_light" if light.name == "" else light.name
            if light.type == 0: # Point
                luz = bpy.data.lights.new(make_unique_name(light_name), type="SPOT")
                luz.spot_size = radians(7)
                luz.spot_blend = 1
                luz.show_cone = True
                luz.color = (0, 1, 0)
                luz.energy = 10000
            elif light.type == 1: # Global Light
                luz = bpy.data.lights.new(make_unique_name(light_name), type="SUN")
                luz.color = (1, 1, 1)
                luz.angle = 0
                if bpy.app.version < (4, 5, 0):
                    luz.energy = 5
                else:
                    luz.energy = 8
                    luz.exposure = -1
                luz.use_shadow = True
            elif light.type == 2: # Sun
                luz = bpy.data.lights.new(make_unique_name(light_name), type="SUN")
                luz.color = (1, 1, 1)
                luz.angle = 0
                luz.energy = 2
                luz.use_shadow = False
            elif light.type == 3: # Moon
                luz = bpy.data.lights.new(make_unique_name(light_name), type="SUN")
                luz.color = (0.7, 0.7, 1)
                luz.angle = 0
                luz.energy = 0.4
                luz.use_shadow = False
            
            luz_obj = bpy.data.objects.new(make_unique_name(light_name), luz)
            lights_coll.objects.link(luz_obj)

            luz_obj.location = (matrix @ Matrix.Translation(Vector((light.vpos_local[0], light.vpos_local[1], light.vpos_local[2])))).to_translation()
            luz_obj["data"] = light.data
            luz_obj["type"] = light.type
            luz_obj["name"] = light_name

            luz_obj["GUID"] = light.extra_value.guid
            luz_obj["PARENT_GUID"] = light.extra_value.parent_guid

            # aim to point (0, 0, 0)
            if light.type != 0:
                luz_obj.rotation_mode = 'XYZ'
                luz_obj.rotation_euler = (luz_obj.location - (matrix @ Matrix.Translation(Vector((0, 0, 0)))).to_translation()).to_track_quat('Z', 'Y').to_euler()

                if light.type == 1 and light.data != "":
                    # diffuse, ambient_type[0], ambient_type[1]
                    values = re.findall(r"[0-9A-f]+", light.data)
                    if len(values) != 3:
                        diffuse = 0xFFFFFF
                        ambient1 = 0xFFFFFF
                        ambient2 = 0xFFFFFF
                    else:
                        diffuse = int(values[0], 16)
                        ambient1 = int(values[1], 16)
                        ambient2 = int(values[2], 16)
                    luz.color = (((ambient1 >> 16) & 0xFF)/0xFF, ((ambient1 >> 8) & 0xFF)/0xFF, (ambient1 & 0xFF)/0xFF)
                    luz.diffuse_factor = (((diffuse >> 16) & 0xFF)/0xFF + ((diffuse >> 8) & 0xFF)/0xFF + (diffuse & 0xFF)/0xFF) / 3
            
            if light.type != 1:
                luz_obj.hide_render = True
    
    # import sound boxs
    if setting.load_sound_boxs and len(gbin.sound_boxs) > 0:
        sound_boxs_coll = bpy.data.collections.new(make_unique_name("Sound Boxs"))
        if bpy.app.version >= (2, 9, 1):
            sound_boxs_coll.color_tag = 'COLOR_02'
        collection.children.link(sound_boxs_coll)
        for sound_box in gbin.sound_boxs:
            sb = make_bbox(sound_boxs_coll, None, sound_box.name, sound_box.min_max_local, matrix, None, False)
            sb["name"] = sound_box.name
            sb["type"] = sound_box.type

            sb["GUID"] = sound_box.extra_value.guid
            sb["PARENT_GUID"] = sound_box.extra_value.parent_guid

    # import nodes
    if setting.load_nodes and len(gbin.nodes) > 0:
        nodes_coll = bpy.data.collections.new(make_unique_name("Nodes"))
        if bpy.app.version >= (2, 9, 1):
            nodes_coll.color_tag = 'COLOR_06'
        collection.children.link(nodes_coll)
        for node in gbin.nodes:
            node_obj = bpy.data.objects.new(make_unique_name(node.name), None)
            nodes_coll.objects.link(node_obj)
            node_obj["type"] = node.type
            node_obj["name"] = node.name

            for index, point in enumerate(node.vects):
                point_obj = bpy.data.objects.new(make_unique_name("point"), None)
                nodes_coll.objects.link(point_obj)
                point_obj.location = (matrix @ Matrix.Translation(Vector((point[0], point[1], point[2])))).to_translation()
                point_obj.empty_display_type = 'SINGLE_ARROW'
                point_obj.empty_display_size = 2
                point_obj.parent = node_obj
                point_obj["index"] = index

                point_obj.hide_render = True
            
            node_obj.hide_render = True

    # import New Element V72, Green type 1, Tee Shot type 2
    if setting.load_new_elements and len(gbin.new_elements_v72) > 0:
        new_elements_coll = bpy.data.collections.new(make_unique_name("New Elements"))
        if bpy.app.version >= (2, 9, 1):
            new_elements_coll.color_tag = 'COLOR_01'
        collection.children.link(new_elements_coll)
        for new_element in gbin.new_elements_v72:
            point = None
            if new_element.type == 1: # Point Green
                point = bpy.data.lights.new(make_unique_name(new_element.name), type="SPOT")
                point.spot_size = radians(7)
                point.spot_blend = 1
                point.show_cone = True
                point.color = (0, 1, 0)
                point.energy = 10000
            if new_element.type == 2: # Point Tee Shot
                point = bpy.data.lights.new(make_unique_name(new_element.name), type="SPOT")
                point.spot_size = radians(7)
                point.spot_blend = 1
                point.show_cone = True
                point.color = (0, 1, 0)
                point.energy = 10000
            
            point_obj = bpy.data.objects.new(make_unique_name(new_element.name), point)
            new_elements_coll.objects.link(point_obj)

            point_obj.matrix_world = matrix @ makeMatrixFrom4x3(new_element.matrix_local)
            point_obj["name"] = new_element.name
            point_obj["type"] = new_element.type

            point_obj["GUID"] = new_element.extra_value.guid
            point_obj["PARENT_GUID"] = new_element.extra_value.parent_guid

            point_obj.hide_render = True

    # Set All Objects Parent from ordered list low to high
    for obj in collection.all_objects:
        setParentByGUIDAndParentGUIDFromObj(obj)

    # clean PARENT_SETED
    for obj in collection.all_objects:
        try:
            del obj["PARENT_SETED"]
        except:
            pass

    # clean cached objects
    if cached_model_objs:
        for (ob, model) in cached_model_objs.values():
            del model
            if ob.type == 'MESH':
                bpy.data.meshes.remove(ob.data)
            elif ob.type == 'ARMATURE':
                if ob.animation_data and ob.animation_data.action:
                    bpy.data.actions.remove(ob.animation_data.action)
                bpy.data.armatures.remove(ob.data)
            if is_valid_object(ob):
                bpy.data.objects.remove(ob)

    # clean collection here
    if collection_tmp:
        for ob in collection_tmp.objects:
            if ob.type == 'MESH':
                bpy.data.meshes.remove(ob.data)
            elif ob.type == 'ARMATURE':
                if ob.animation_data and ob.animation_data.action:
                    bpy.data.actions.remove(ob.animation_data.action)
                bpy.data.armatures.remove(ob.data)
            if is_valid_object(ob):
                bpy.data.objects.remove(ob)
        bpy.data.collections.remove(collection_tmp)
        collection_tmp = None

def load(operator, context, matrix):

    print('importing pangya GBIN: %r' % (operator.filepath))

    time1 = time.process_time()

    with open(operator.filepath, 'rb') as file:
        load_gbin(context, file, matrix, operator)

    print('import pangya GBIN done in %.4f sec.' % (time.process_time() - time1))

    return {'FINISHED'}
