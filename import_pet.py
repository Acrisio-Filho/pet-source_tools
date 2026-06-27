# Copyright 2016 John Chadwick <john@jchw.io>
# Copyright 2023-2026 Acrisio Filho

from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

import os, pathlib, time, re, bpy, bmesh, numpy as np # pyright: ignore[reportMissingImports]

from math import radians
from collections import namedtuple, defaultdict
from mathutils import Matrix, Vector, Quaternion # pyright: ignore[reportMissingImports]

from .pet import Puppet, eSPECULAR_MATERIAL_TYPE
from .texture_util import import_material_v280, replaceFace, makeSpecularMaterials
from .util import (
    makeMatrixFrom4x3,
    mat4_to_length_mat4,
    mat4_to_ebone,
    calc_ebonemat,
    calc_deform_vert_by_mpet_and_bpet_arm,
    calc_original_vert_by_old_arm,
    make_bbox,
    KeyFrame,
    ifnull,
    make_unique_name,
    remove_and_make_unique_name,
    is_valid_object,
    average_normals_and_merge_and_smooth,
    value_to_attr_string_value,
    make_mesh_attribute,
    get_bone_weights_and_main_bone_weight,
    get_vertice_main_bone_name,
    get_vertice_mpet_weight_global_name,
    get_face_material_espacular_index_name,
    getCurrentClipEnd,
    updateScreenClipEnd
)

def load_pet(context, file, matrix, setting):
    print('importing pangya model: %r' % (file.name))

    time1 = time.process_time()

    load_pet_obj(
        context,
        file,
        matrix,
        setting.collisionBox_enable,
        setting.collisionBox_show,
        setting.anim_enable,
        setting.specular_material_filter_enable
    )

    print('import done in %.4f sec.' % (time.process_time() - time1))

def load_pet_obj(context, file, matrix, collisionBox_enable, collisionBox_show, anim_enable, specular_material_filter_enable, collection=None):
    dirname = os.path.dirname(file.name)
    filename = os.path.basename(file.name)
    
    model = Puppet()
    model.load(file)

    # camera
    is_camera = False
    if model.is_apet:
        is_camera = len(list(filter(lambda b: re.search(r'camera', b.name, re.IGNORECASE), model.bones))) > 0

    materials = []

    # Make materials for each texture.
    for texture in sorted(model.textures, key=lambda e : 0 if e.fn[0] == '!' else -1):
        mat = import_material_v280(model.face_anims, materials, texture, file.name)

        if mat:
            materials.append(mat['material'])

    if len(context.selected_objects) > 0:
        # change to object mode, to deselect all objects in collection
        bpy.ops.object.mode_set(mode='OBJECT')

        # deselect all objects in collection
        bpy.ops.object.select_all(action='DESELECT')
    
    # make armature model
    def MakeArmature():
        # Armature
        arm_name = make_unique_name(filename + " Armature")
        armature = bpy.data.armatures.new(arm_name)
        armature.display_type = 'STICK' # Large bones otherwise make this a bit ridiculous.
        armature_obj = bpy.data.objects.new(arm_name, armature)
        collection.objects.link(armature_obj)
        armature_obj.show_in_front = True
        armature_obj.select_set(True)
        armature_obj["is_armature_model"] = True

        # Create bones.
        context.view_layer.objects.active = armature_obj
        bpy.ops.object.mode_set(mode='EDIT')
        bbonemap = {}
        
        # Pass 1: Create bones
        for id, bone in enumerate(model.bones):
            bbone = armature.edit_bones.new(bone.name)
            armature.edit_bones.active = bbone

            bbone.use_deform = True
            bbone.orientation_flag = bone.orientation_flag
            
            # matrix(local)
            mat4_to_ebone(bbone, makeMatrixFrom4x3(bone.matrix))

            bbonemap[id] = bbone

        # Pass 2: Assign parents
        for id, bone in enumerate(model.bones):
            bbone = bbonemap[id]
            armature.edit_bones.active = bbone

            if bone.parent != -1:
                bbone.parent = bbonemap[bone.parent]

            bbone.length, bbone.matrix = mat4_to_length_mat4(calc_ebonemat(bbone))
            
        bpy.ops.object.mode_set(mode='POSE')

        for bone in armature_obj.pose.bones:
            bone.orientation_flag = -1

        bpy.ops.object.mode_set(mode='OBJECT')
        
        # upAxis
        armature_obj.matrix_world @= matrix

        # make extras
        if len(model.extras) > 0:
            extras_obj = bpy.data.objects.new(make_unique_name("Extras"), None)
            collection.objects.link(extras_obj)
            extras_obj.parent = armature_obj

            for extra in model.extras:
                extra_obj = bpy.data.objects.new(make_unique_name("bone_id: %d" % extra.bone_id), None)
                collection.objects.link(extra_obj)
                extra_obj.parent = extras_obj
                if extra.bone_id == -1:
                    extra_obj["bone_name"] = "Unknown"
                else:
                    extra_obj["bone_name"] = ifnull(model.bones[extra.bone_id].name, "Unknown")
                    extra_obj.name = make_unique_name("bone: %d, %s" % (extra.bone_id, extra_obj["bone_name"]))

        print("Carregou %d bones de %d." % (len(armature_obj.data.bones), len(model.bones)))
        
        return armature_obj, armature
    
    # make armature camera
    def MakeArmatureCamera(_parent=None):
        # Armature
        arm_name = make_unique_name(filename + " Armature")
        armature = bpy.data.armatures.new(arm_name)
        armature.display_type = 'STICK' # Large bones otherwise make this a bit ridiculous.
        armature_obj = bpy.data.objects.new(arm_name, armature)
        collection.objects.link(armature_obj)
        armature_obj.show_in_front = True
        armature_obj.select_set(True)
        armature_obj["is_armature_model"] = False # Camera

        # Create bones.
        context.view_layer.objects.active = armature_obj
        bpy.ops.object.mode_set(mode='EDIT')
        bbonemap = {}

        # Pass 1: Create bones
        for id, bone in enumerate(model.bones):
            bbone = armature.edit_bones.new(bone.name)
            armature.edit_bones.active = bbone

            bbone.use_deform = True
            bbone.orientation_flag = bone.orientation_flag

            # matrix(local)
            mat4_to_ebone(bbone, Matrix.Identity(4))

            bbonemap[id] = bbone

        # Pass 2: Assign parents
        for id, bone in enumerate(model.bones):
            bbone = bbonemap[id]
            armature.edit_bones.active = bbone

            if bone.parent != -1:
                bbone.parent = bbonemap[bone.parent]

            bbone.length, bbone.matrix = mat4_to_length_mat4(calc_ebonemat(bbone))
            
        bpy.ops.object.mode_set(mode='POSE')

        for bone in armature_obj.pose.bones:
            bone.orientation_flag = -1

        bpy.ops.object.mode_set(mode='OBJECT')
        
        # upAxis
        armature_obj.matrix_world @= matrix

        if _parent and _parent["is_armature_model"]:
            armature_obj["armature_parent_name"] = _parent.name

        print("(Camera) Carregou %d bones de %d." % (len(armature_obj.data.bones), len(model.bones)))
        
        return armature_obj, armature

    armature = None
    armature_obj = None
    bpet_armature = None
    bpet_armature_obj = None

    # verifica se já tem o bone padrão carregado
    if model.is_mpet or model.is_apet:
        char_letter = filename.find('_')
        if char_letter != -1:
            for obj_arm in [obj for obj in context.view_layer.objects if ".bpet Armature" in obj.name]:
                char_letter_obj = obj_arm.name.find('_')
                if char_letter_obj != -1 and filename[:char_letter] == obj_arm.name[:char_letter_obj]:
                    if obj_arm.get("is_armature_model"):
                        bpet_armature_obj = obj_arm
                        bpet_armature = bpet_armature_obj.data
                        
                        # apet não tem sua própria armature
                        if model.is_apet:
                            armature_obj = obj_arm
                            armature = armature_obj.data

                        bpet_armature_obj.select_set(True)
                        context.view_layer.objects.active = bpet_armature_obj
                        bpy.ops.object.mode_set(mode='OBJECT')

                        # collection
                        if not collection:
                            collections = tuple()
                            if bpet_armature_obj.parent:
                                collections = bpet_armature_obj.parent.users_collection
                            else:
                                collections = bpet_armature_obj.users_collection

                            # make
                            if len(collections) > 0:
                                collection = collections[0]
                            else:
                                # Collection
                                collection = bpy.data.collections.new(make_unique_name(filename))

                                context.scene.collection.children.link(collection)
                        break

    if not armature_obj:
        if model.is_apet and not is_camera:
            raise Exception('bpet not loaded')
        elif not collection:
            # Collection
            collection = bpy.data.collections.new(make_unique_name(filename))

            context.scene.collection.children.link(collection)
        
        if is_camera:
            armature_obj, armature = MakeArmatureCamera()
        else:
            armature_obj, armature = MakeArmature()
        print('Criou uma nova armação: ', armature_obj.name)
    elif is_camera:
        armature_obj, armature = MakeArmatureCamera(armature_obj)

    # make camera
    if is_camera:
        cam_name = make_unique_name(filename + " Camera")
        camera = bpy.data.cameras.new(cam_name)
        camera.lens = 20

        # atualiza limite de visualização da câmera para o maior limite atual
        camera.clip_end = max(camera.clip_end, getCurrentClipEnd())

        camera_obj = bpy.data.objects.new(cam_name, camera)
        collection.objects.link(camera_obj)

        # upAxis
        camera_obj.matrix_world @= matrix @ Matrix.Scale(-1, 4, (0, 0, 1))

        camera_obj.location = (0, 0, 0)
        camera_obj.rotation_mode = 'XYZ'
        camera_obj.rotation_euler = (0, 0, radians(90))

        # constraint
        constraint = camera_obj.constraints.new('CHILD_OF')
        constraint.target = armature_obj
        constraint.subtarget = next((bone.name for bone in armature_obj.data.bones if re.search(r'camera', bone.name, re.IGNORECASE)), '')

    mesh_obj = None

    # Geometry!
    mesh = model.mesh
    if mesh:
        dmesh_name = make_unique_name(filename)
        dmesh = bpy.data.meshes.new(dmesh_name)
        obj = bpy.data.objects.new(dmesh_name, dmesh)
        obj["directory"] = dirname
        obj["version"] = "{}.{}".format(model.version.major, model.version.minor)

        # link to collection
        collection.objects.link(obj)

        # Flatten vertices down to [x,y,z,x,y,z...] array.
        verts = []
        for vert in mesh.vertices:
            vector = calc_deform_vert_by_mpet_and_bpet_arm(
                vert,
                [(
                    model.bones[w.id].name,
                    (1.0 / 255 * w.weight)
                ) for w in vert.bone_weights],
                armature_obj,
                bpet_armature_obj
            )

            verts.extend((vector.x, vector.y, vector.z))

        dmesh.vertices.add(len(mesh.vertices))
        dmesh.vertices.foreach_set("co", verts)

        # set MPET_WEIGHT and MAIN_BONE_VERTICE to pangya
        for idx, vert in enumerate(mesh.vertices):
            # mpet weight global value
            attr_weight_global = make_mesh_attribute(obj, get_vertice_mpet_weight_global_name())
            attr_weight_global.data[idx].value = vert.weight_global

            # blend weights first bone
            weight = next(iter(vert.bone_weights), None)
            if weight:
                attr_main_bone = make_mesh_attribute(obj, get_vertice_main_bone_name(), "STRING")
                attr_main_bone.data[idx].value = value_to_attr_string_value(model.bones[weight.id].name)

        # set handler de modificador mpet mesh object
        if model.is_mpet:
            dmesh.current_draw_armature = armature_obj

            if bpet_armature_obj:
                dmesh.current_draw_armature = bpet_armature_obj

            def on_depsgraph_update(scene, depsgraph):
                if not is_valid_object(obj):
                    bpy.app.handlers.depsgraph_update_post.remove(on_depsgraph_update)
                    return

                for update in [upt for upt in depsgraph.updates if isinstance(upt.id, bpy.types.Object) and upt.id.name == obj.name]:
                    for mod in [mod for mod in obj.modifiers if mod.type == "ARMATURE" and mod.object and is_valid_object(obj.data.current_draw_armature) and obj.data.current_draw_armature != mod.object]:

                        old_arm = obj.data.current_draw_armature
                        mpet_arm = next((x for x in obj.children if x.type == "ARMATURE"), None)

                        if not old_arm or not mpet_arm:
                            continue

                        obj.data.current_draw_armature = mod.object
                        new_arm = mod.object

                        new_is_bpet = ".bpet" in new_arm.name

                        verts = []
                        for vert in obj.data.vertices:
                            vector = Vector((0, 0, 0))
                            vertpos = vert.co

                            main_bone_weight, bone_weights = get_bone_weights_and_main_bone_weight(obj, vert)

                            if not main_bone_weight:
                                verts.extend((vertpos.x, vertpos.y, vertpos.z))
                                continue

                            # old arm
                            vertpos = calc_original_vert_by_old_arm(vert.co, bone_weights, old_arm, mpet_arm)

                            vector = calc_deform_vert_by_mpet_and_bpet_arm(
                                vertpos,
                                bone_weights,
                                mpet_arm if new_is_bpet else new_arm,
                                new_arm if new_is_bpet else None
                            )

                            verts.extend((vector.x, vector.y, vector.z))

                        obj.data.vertices.foreach_set("co", verts)

                        obj.data.update()

            if on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
                bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_update)

        # Polygons
        num_faces = len(mesh.polygons)
        dmesh.polygons.add(num_faces)
        dmesh.loops.add(num_faces * 3)
        faces = []
        for p in mesh.polygons:
            faces.extend((
                p.indices[0].index,
                p.indices[1].index,
                p.indices[2].index
            ))
        dmesh.polygons.foreach_set("loop_start", range(0, num_faces * 3, 3))
        dmesh.polygons.foreach_set("loop_total", (3,) * num_faces)
        dmesh.polygons.foreach_set("use_smooth", (True,) * num_faces)
        dmesh.loops.foreach_set("vertex_index", faces)

        # UV maps
        uvtexs = []
        uvtexs.append(dmesh.uv_layers.new(name="UVMap"))
        for index, bpolygon in enumerate(dmesh.polygons):
            polygon = mesh.polygons[index]

            i = bpolygon.loop_start
            for index2 in polygon.indices:
                uvmp_num = len(index2.uvMapping)
                if uvmp_num > len(uvtexs):
                    for h in range(uvmp_num - len(uvtexs)):
                        uvtexs.append(dmesh.uv_layers.new(name="UVMap{}".format(len(uvtexs))))
                for i_uvmp in range(uvmp_num):
                    uvtexs[i_uvmp].data[i].uv = index2.uvMapping[i_uvmp].u, 1.0 - index2.uvMapping[i_uvmp].v
                i += 1

        # Materials
        for material in materials:
            dmesh.materials.append(material)

        for index, material in enumerate(mesh.texmap):
            dmesh.polygons[index].material_index = material

        # texture map specular material
        material_specular_index_attr = make_mesh_attribute(obj, get_face_material_espacular_index_name(), "INT", "FACE")
        values = [-1] * len(mesh.texmap)
        material_specular_index_attr.data.foreach_set("value", values)

        for index, material_specular in enumerate(mesh.texmap_specular):
            material_specular_index_attr.data[index].value = int(material_specular)

        # Normals
        dmesh.update()

        bm = bmesh.new()
        bm.from_mesh(dmesh)

        bm.faces.ensure_lookup_table()

        for face in bm.faces:
            face.smooth = True
            for idx,loop in enumerate(face.loops):
                index = mesh.polygons[face.index].indices[idx]
                loop.vert.normal = (index.nx, index.ny, index.nz)
        
        bm.to_mesh(dmesh)
        bm.free()

        if hasattr(dmesh, "use_auto_smooth"):
            dmesh.use_auto_smooth = True

        dmesh.validate(clean_customdata=False) # *Very* important to not remove lnors here!
        dmesh.update()

        # fixing normals
        average_normals_and_merge_and_smooth(dmesh)

        # Vertex groups
        VertexWeight = namedtuple('VertexWeight', ['vertex', 'weight'])
        groups = {}

        # Translate weights into structure of groups.
        for id, vertex in enumerate(mesh.vertices):
            for idx, weight in enumerate(vertex.bone_weights):
                group = groups.get(weight.id, [])
                group.append(VertexWeight(id, (1.0 / 255 * weight.weight)))
                groups[weight.id] = group

        # Load groups into Blender
        for id, weights in groups.items():
            group_name = model.bones[id].name
            bgroup = obj.vertex_groups.new(name=group_name)
            # blend weights
            for weight in weights:
                bgroup.add([weight.vertex], weight.weight, 'ADD')

        # upAxis
        obj.matrix_world @= matrix

        # mpet(Mesh Pet)
        if model.is_mpet:
            mpetexs_len = len(mesh.mpetexs)
            if mpetexs_len > 1:
                print("Mais de um Mpet Extra Value: (%s)" % repr(mesh.mpetexs))
            
            if mpetexs_len > 0:
                mpet_bone = model.bones[mesh.mpetexs[0].bone_id] if mesh.mpetexs[0].bone_id >= 0 and mesh.mpetexs[0].bone_id < len(model.bones) else None
                if mpet_bone:
                    obj["mpet_bone_name"] = mpet_bone.name
                else:
                    obj["mpet_bone_name"] = os.path.splitext(filename)[0].upper()

        # Armature modifier
        bmodifier = obj.modifiers.new(armature.name, type='ARMATURE')
        bmodifier.show_expanded = False
        bmodifier.use_vertex_groups = True
        bmodifier.use_bone_envelopes = False
        bmodifier.object = bpet_armature_obj if bpet_armature_obj else armature_obj

        # set parent armature to obj
        armature_obj.matrix_world = obj.matrix_world.inverted() @ armature_obj.matrix_world
        armature_obj.parent = obj

        mesh_obj = obj

    # Collision Box
    if collisionBox_enable and len(model.collisions) > 0:
        coll_obj = bpy.data.objects.new(make_unique_name('Collisions'), None)
        collection.objects.link(coll_obj)
        coll_obj.parent = armature_obj
        for coll in model.collisions:
            bone_name = coll.scripts[1] # scripts[1] = Bone name
            bone = armature_obj.data.bones.get(bone_name)
            if bone:
                bb = make_bbox(collection, bone_name, coll.scripts[0], coll.area, bone.matrix_local, coll_obj, not collisionBox_show)
                bb['shape'] = coll.shape
                bb['show'] = coll.show
                for i in range(4):
                    try:
                        script = coll.scripts[i]
                    except IndexError:
                        script = ''
                    bb["script0%d" % i] = script
            else:
                print("Dont have bone({}) in list of bones".format(bone_name))
        if len(coll_obj.children) == 0:
            collection.objects.unlink(coll_obj)

    # Specular Material
    if len(model.smtls) > 0:
        smtls_obj = bpy.data.objects.new(make_unique_name('Specular Materials'), None)
        collection.objects.link(smtls_obj)
        smtls_obj.parent = mesh_obj
        for index,smtl in enumerate(model.smtls):
            smtl_obj = bpy.data.objects.new(make_unique_name(smtl.name), None)
            collection.objects.link(smtl_obj)
            smtl_obj.parent = smtls_obj
            smtl_obj["index"] = index
            for smtlv in smtl.smtlvs:
                smtlv_obj = bpy.data.objects.new(make_unique_name(smtlv.name), None)
                collection.objects.link(smtlv_obj)
                smtlv_obj.parent = smtl_obj
                smtlv_obj["type"] = smtlv.type

                if smtlv.type == eSPECULAR_MATERIAL_TYPE.SMTL_BOOL:
                    smtlv_obj["value"] = True if smtlv.value > 0 else False
                elif smtlv.type == eSPECULAR_MATERIAL_TYPE.SMTL_INT or smtlv.type == eSPECULAR_MATERIAL_TYPE.SMTL_FLOAT or smtlv.type == eSPECULAR_MATERIAL_TYPE.SMTL_TEXTURE:
                    smtlv_obj["value"] = smtlv.value
                elif smtlv.type == eSPECULAR_MATERIAL_TYPE.SMTL_VECTOR2:
                    smtlv_obj.location = Vector((smtlv.value[0], smtlv.value[1], 1))
                elif smtlv.type == eSPECULAR_MATERIAL_TYPE.SMTL_VECTOR3:
                    smtlv_obj.location = Vector((smtlv.value[0], smtlv.value[1], smtlv.value[2]))
                elif smtlv.type == eSPECULAR_MATERIAL_TYPE.SMTL_VECTOR4:
                    smtlv_obj.rotation_mode = 'QUATERNION'
                    smtlv_obj.rotation_quaternion = Quaternion((smtlv.value[3], smtlv.value[0], smtlv.value[1], smtlv.value[2]))
                elif smtlv.type == eSPECULAR_MATERIAL_TYPE.SMTL_MATRIX:
                    smtlv_obj.matrix_world = makeMatrixFrom4x3(smtlv.value)

            if specular_material_filter_enable:
                # make specular materials
                makeSpecularMaterials(mesh_obj, smtl, index)

    # Animations
    def InitAnimation():
        if len(model.animations) <= 0:
            return
        
        context.view_layer.objects.active = armature_obj
        bpy.ops.object.mode_set(mode='POSE')
        keyframes = defaultdict(dict)

        loc_dict = defaultdict(dict)
        rot_dict = defaultdict(dict)
        sca_dict = defaultdict(dict)
        ori_dict = defaultdict(dict)

        time1 = time.process_time()
        for anim in model.animations:
            bone = armature_obj.pose.bones.get(model.bones[anim.bone_id].name)
            if not bone:
                continue
            for pos in anim.positions:
                frame = round(pos.time * 30)
                vpos = Vector(pos.position[:3])
                keyframes[bone][frame] = KeyFrame(
                    _frame=frame,
                    _pos=True,
                    _matrix=Matrix.Translation(vpos),
                    _vpos=vpos
                )
                loc_dict[bone][frame] = vpos
            for rot in anim.rotations:
                frame = round(rot.time * 30)
                qrot = Quaternion((rot.rotation[3], *rot.rotation[:3])).inverted().normalized()
                mp = qrot.to_matrix().to_4x4()
                kf = keyframes[bone].get(frame)
                if kf:
                    kf.rot = True
                    kf.matrix = kf.matrix @ mp
                    kf.qrot = qrot
                else:
                    keyframes[bone][frame] = KeyFrame(
                        _frame=frame,
                        _rot=True,
                        _matrix=mp,
                        _qrot=qrot
                    )
                rot_dict[bone][frame] = qrot
            for sca in anim.scalings:
                frame = round(sca.time * 30)
                vsca = Vector(sca.scaling[:3])
                mp = Matrix.Diagonal((*vsca[:], 1))
                kf = keyframes[bone].get(frame)
                if kf:
                    kf.scale = True
                    kf.matrix = kf.matrix @ mp
                    kf.vscale = vsca
                else:
                    keyframes[bone][frame] = KeyFrame(
                        _frame=frame,
                        _scale=True,
                        _matrix=mp,
                        _vscale=vsca
                    )
                sca_dict[bone][frame] = vsca
            for ori in anim.orientation_flags:
                frame = round(ori.time * 30)
                kf = keyframes[bone].get(frame)
                if kf:
                    kf.ori = True
                    kf.orientation_flag = ori.orientation_flag
                else:
                    keyframes[bone][frame] = KeyFrame(
                        _frame=frame,
                        _ori=True,
                        _orientation_flag=ori.orientation_flag
                    )
                ori_dict[bone][frame] = ori.orientation_flag

        # remove empty keyframes
        for bone,frames in list(keyframes.items()):
            if len(frames.values()) == 0:
                del keyframes[bone]
        print('Terminou de carregar os frames para o keyframe default(dict) em %.04f sec' % (time.process_time() - time1))

        def makeAllkeyframeMatrix():

            def get_val(data_dict, target_f, is_quat=False, default=None):
                if not data_dict:
                    if default is not None:
                        return default
                    return Quaternion() if is_quat else Vector((1, 1, 1))

                if target_f in data_dict:
                    return data_dict[target_f]

                keys = sorted(data_dict.keys())

                if len(keys) == 1:
                    return data_dict[keys[0]]
                if target_f <= keys[0]:
                    return data_dict[keys[0]]
                if target_f >= keys[-1]:
                    return data_dict[keys[-1]]
                
                idx_right = np.searchsorted(keys, target_f)
                idx_right = np.clip(idx_right, 1, len(keys)-1)
                idx_left = idx_right - 1

                f1, f2 = keys[idx_left], keys[idx_right]
                v1, v2 = data_dict[f1], data_dict[f2]
                t = (target_f - f1) / (f2 - f1)

                if is_quat:
                    return v1.slerp(v2, t)
                else:
                    return v1.lerp(v2, t)
            
            kf_len = len(keyframes.keys())
            kf_10_percent = kf_len // 10 if kf_len >= 10 else 1
            for i,bone in enumerate(keyframes.keys()):
                all_frames = sorted(set(loc_dict[bone].keys()) | set(rot_dict[bone].keys()) | set(sca_dict[bone].keys()))

                default_loc, default_rot, default_sca = bone.bone.matrix_local.decompose()

                for f in all_frames:
                    keyframes[bone][f].matrix = Matrix.LocRotScale(
                        get_val(loc_dict[bone], f, default=default_loc),
                        get_val(rot_dict[bone], f, is_quat=True, default=default_rot),
                        get_val(sca_dict[bone], f, default=default_sca)
                    )

                if (i % kf_10_percent) == 0 or i == (kf_len - 1):
                    print(f"Gerando matrix dos keyframes dos ossos: {round((i / kf_len) * 100, 2)}%")

        time1 = time.process_time()
        makeAllkeyframeMatrix()
        print('Terminou de gerar todos os keyframes matrix de todos os ossos em %.04f sec' % (time.process_time() - time1))

        if not armature_obj.animation_data:
            armature_obj.animation_data_create()
    
        action = bpy.data.actions.new(remove_and_make_unique_name(armature_obj.name, '_act'))
        
        # principal action
        armature_obj.animation_data.action = action

        if bpy.app.version >= (4, 4, 0):
            armature_obj.animation_data.action_slot = action.slots.new(id_type="OBJECT", name=remove_and_make_unique_name(action.name, "_slot"))

        action_bag = action
        if bpy.app.version >= (5, 0, 0):
            layer = action.layers[0] if action.layers else action.layers.new('Base')
            strip = layer.strips[0] if layer.strips else layer.strips.new(type='KEYFRAME')
            action_bag = strip.channelbags[0] if strip.channelbags else strip.channelbags.new(action.slots[0])

        if is_camera:
            armature_obj.animation_data.action_influence = 0

        if 'fps' in dir(action):
            action.fps = 30
            context.scene.render.fps = 60
            context.scene.render.fps_base = 1
        else:
            context.scene.render.fps = 30
            context.scene.render.fps_base = 1

        context.scene.frame_start = 0
        context.scene.frame_end = max(model.getTotalAnimationTime(), context.scene.frame_end)

        for bone in armature_obj.pose.bones:
            bone.rotation_mode = 'QUATERNION'

        armature_obj.select_set(True)
        context.view_layer.objects.active = armature_obj

        bpy.ops.object.mode_set(mode='POSE')

        # injeta dados irregulares no f-curve
        def injetar_dados_irregulares(bone):

            def calc_and_decompose(_rest_inv_np, f):
                m_delta_np = _rest_inv_np @ np.array(keyframes[bone][f].matrix)

                return Matrix(m_delta_np.tolist()).decompose()

            m_rest = bone.bone.matrix_local
            if bone.bone.parent:
                m_rest = bone.bone.parent.matrix_local.inverted() @ bone.bone.matrix_local

            m_rest_blender_inv_np = np.array(m_rest.inverted())

            final_locs = np.zeros((len(loc_dict[bone]), 3))
            final_quats = np.zeros((len(rot_dict[bone]), 4))
            final_scales = np.zeros((len(sca_dict[bone]), 3))
            final_oris = np.zeros((len(ori_dict[bone]), 1))
            idx_loc, idx_rot, idx_sca, idx_ori = 0, 0, 0, 0

            all_frames = sorted(set(loc_dict[bone].keys()) | set(rot_dict[bone].keys()) | set(sca_dict[bone].keys()) | set(ori_dict[bone].keys()))
            for f in all_frames:
                l, r, s = calc_and_decompose(m_rest_blender_inv_np, f)

                if keyframes[bone][f].pos:
                    final_locs[idx_loc] = l
                    idx_loc += 1
                if keyframes[bone][f].rot:
                    final_quats[idx_rot] = r
                    idx_rot += 1
                if keyframes[bone][f].scale:
                    final_scales[idx_sca] = s
                    idx_sca += 1
                if keyframes[bone][f].ori:
                    final_oris[idx_ori] = keyframes[bone][f].orientation_flag
                    idx_ori += 1

            payload = {
                "location": (list(loc_dict[bone].keys()), final_locs, 3, 0),
                "rotation_quaternion": (list(rot_dict[bone].keys()), final_quats, 4, 0),
                "scale": (list(sca_dict[bone].keys()), final_scales, 3, 0),
                "orientation_flag": (list(ori_dict[bone].keys()), final_oris, 1, 0)
            }

            for prop, (f_list, v_list, array_size, type) in payload.items():
                if type == 1:
                    data_path = f'pose.bones["{bone.name}"]["{prop}"]'
                else:
                    data_path = f'pose.bones["{bone.name}"].{prop}'

                for i in range(array_size):
                    fc = action_bag.fcurves.find(data_path, index=i) or action_bag.fcurves.new(data_path, index=i)
                    fc.group = action_bag.groups.get(bone.name) or action_bag.groups.new(name=bone.name)

                    # Criar o array flat [f1, v1, f2, v2...] apenas com os frames existentes para este canal
                    # v_list[:, i] pega apenas a coluna do eixo atual
                    count = len(f_list)
                    flat_data = np.empty(count * 2, dtype=np.float32)
                    flat_data[0::2] = f_list              # Frames nas posições pares
                    flat_data[1::2] = v_list[:, i]        # Valores nas posições ímpares

                    fc.keyframe_points.add(count=count)
                    fc.keyframe_points.foreach_set("co", flat_data)
                    fc.update()

        # insert keyframes in fcurves
        time2 = time.process_time()
        kf_len = len(keyframes.keys())
        kf_10_percent = kf_len // 10 if kf_len >= 10 else 1
        for i,bone in enumerate(keyframes.keys()):
            time1 = time.process_time()
            injetar_dados_irregulares(bone)

            if (i % kf_10_percent) == 0 or i == (kf_len - 1):
                print(f"Inserindo keyframes dos ossos no fcurve: {round((i / kf_len) * 100, 2)}%")
        print('Inseriu todos os keyframes dos ossos no fcurve em %.04f' % (time.process_time() - time2))

        for bone in armature_obj.pose.bones:
            bone.matrix_basis.identity()
        scn = context.scene

        if scn.frame_current == 1:
            scn.frame_set(0)
        else:
            scn.frame_set(scn.frame_current)

        # make motions
        for nla in armature_obj.animation_data.nla_tracks:
            armature_obj.animation_data.nla_tracks.remove(nla)

        tracks = []
        tracks.append(armature_obj.animation_data.nla_tracks.new())
        tracks[-1].name = remove_and_make_unique_name(armature_obj.name, ".nla")
        tracks.append(armature_obj.animation_data.nla_tracks.new())
        tracks[-1].name = remove_and_make_unique_name(armature_obj.name, ".nla")

        def createStrip(_name, _action, _motion, _frame_start, _index=0):
            
            if len(tracks) == _index:
                tracks.append(armature_obj.animation_data.nla_tracks.new(prev=tracks[0]))
                tracks[-1].name = remove_and_make_unique_name(armature_obj.name, ".nla")

            strip = None
            try:
                strip = tracks[_index].strips.new(_name, int(_frame_start), _action)
            except:
                strip = createStrip(_name, _action, _motion, _frame_start, _index + 1)
            strip.extrapolation = 'NOTHING'
            strip.action_frame_start = _motion["frame_start"]
            strip.action_frame_end = _motion["frame_end"]

            return strip
        
        def camera_motion_name_to_motion_name(_name):
            last_underscore_idx = _name.rfind('_')
            if last_underscore_idx == -1:
                return _name
            return _name[:last_underscore_idx]

        motions_obj = bpy.data.objects.new(make_unique_name("Motions"), None)
        collection.objects.link(motions_obj)
        motions_obj.parent = armature_obj

        viewed_motions = []
        action_motions = []
        # Error de deep recursion, tive que fazer com loop mesmo
        def next_move_recursive(next_move):
            
            while True:
                motion = next((m for m in model.motions if m.name == next_move), None)
                if motion:
                    if motion.name not in viewed_motions:
                        viewed_motions.append(motion.name)
                        action_motions[-1]["frame_end"] = motion.frame_end
                    if motion.name != motion.next_move and camera_motion_name_to_motion_name(motion.name) in motion.next_move:
                        next_move = motion.next_move
                        continue
                break
        
        for motion in model.motions:
            motion_obj = bpy.data.objects.new(make_unique_name(motion.name), None)
            collection.objects.link(motion_obj)
            motion_obj.parent = motions_obj

            motion_obj["name"] = motion.name
            motion_obj["frame_start"] = motion.frame_start
            motion_obj["frame_end"] = motion.frame_end
            motion_obj["next_move"] = motion.next_move
            motion_obj["connection_method"] = motion.connection_method
            motion_obj["connection_time"] = motion.connection_time
            motion_obj["root_bone"] = motion.root_bone

            if motion.name in viewed_motions:
                continue
            viewed_motions.append(motion.name)
            action_motions.append({"name": motion.name, "frame_start": motion.frame_start, "frame_end": motion.frame_end})

            if motion.name != motion.next_move:
                next_move_recursive(motion.next_move)

        def get_motions_from_parent_armature_name(parent_name, name):
                if not parent_name:
                    return None

                arm_parent = bpy.data.objects.get(parent_name)

                if not arm_parent:
                    return None
                
                arm_motions_obj = next((m for m in arm_parent.children if "Motions" in m.name), None)

                if not arm_motions_obj:
                    return None
                
                return next((m for m in arm_motions_obj.children if name in m.name), None)

        for motion in action_motions:
            frame_start = motion["frame_start"]
            if is_camera:
                act_motion = get_motions_from_parent_armature_name(armature_obj.get("armature_parent_name"), camera_motion_name_to_motion_name(motion["name"]))
                if act_motion:
                    frame_start = ifnull(act_motion.get("frame_start"), frame_start)
            createStrip(remove_and_make_unique_name(action.name, "_" + motion["name"]), action, motion, frame_start, 1)
        armature_obj.animation_data.nla_tracks.remove(tracks[0])

        # make frames scripts
        if len(model.frames) > 0:
            frames_obj = bpy.data.objects.new(make_unique_name("Frames"), None)
            collection.objects.link(frames_obj)
            frames_obj.parent = armature_obj

            for frame in model.frames:
                frame_obj = bpy.data.objects.new(make_unique_name("index: %d" % frame.index), None)
                collection.objects.link(frame_obj)
                frame_obj.parent = frames_obj

                frame_obj["index"] = frame.index
                frame_obj["check"] = frame.check
                frame_obj["script"] = frame.script

            def frame_script(scene):
                if not is_valid_object(armature_obj):
                    bpy.app.handlers.frame_change_pre.remove(frame_script)
                    return
                frames_obj = next((obj for obj in armature_obj.children if "Frames" in obj.name), None)
                if not frames_obj:
                    return
                frame_obj = next((obj for obj in frames_obj.children if obj.get("index") == scene.frame_current), None)
                if not frame_obj:
                    return
                script = frame_obj.get("script")
                cmds = script.split("*")
                cmds = list(map(lambda x: x.strip().lower(), cmds))

                def toggleclub(hide):
                    for obj in context.view_layer.objects:
                        if obj.type == "MESH" and "club" in obj.name and ".pet" in obj.name:
                            child_constraint = next((cc for cc in obj.constraints if cc.type == "CHILD_OF" and cc.target and cc.target.name == armature_obj.name), None)
                            if not child_constraint:
                                continue
                            bone = armature_obj.data.bones.get(child_constraint.subtarget)
                            if not bone or not bone.parent or bone.parent.name != "Bone01":
                                continue
                            obj.hide_set(hide)
                
                def ptex():
                    # __facetexture__ mpet(character), face pet(caddie, npc etc)
                    cmd_faces = [cmd for cmd in cmds if "ptex" in cmd and ("__facetexture__" in cmd or "face" in cmd)]
                    len_cmd_faces = len(cmd_faces)
                    if len_cmd_faces == 0:
                        return
                    for i in range(len_cmd_faces):
                        face_material_name = re.sub(r'[")]', "", cmd_faces[i].split(" ")[1])
                        replaceFace(armature_obj, dirname, face_material_name, "__facetexture__" in cmd_faces[i], i != 0)
                
                def hidebone():
                    cmd_hidebone = next((cmd for cmd in cmds if "hidebone" in cmd), None)
                    if not cmd_hidebone:
                        return
                    # mostra todos antes de ocultar
                    if len(armature_obj.users_collection) > 0:
                        for obj in armature_obj.users_collection[0].all_objects:
                            if obj.type == "MESH" and (not obj.parent or "Collisions" not in obj.parent.name):
                                obj.hide_set(False)
                    toggleclub(False)
                    # ocultar os bones especificos
                    for obj_name in map(lambda x: re.sub(r'hidebone|["()]', "", x), cmd_hidebone.split(" ")):
                        bone_obj = next((obj for obj in context.view_layer.objects if (obj_name + ".mpet") in obj.name), None)
                        if not bone_obj:
                            continue
                        bone_obj.hide_set(True)
                
                def showbone():
                    cmd_showbone = next((cmd for cmd in cmds if "showbone" in cmd), None)
                    if not cmd_showbone:
                        return
                    for obj_name in map(lambda x: re.sub(r'showbone|["()]', "", x), cmd_showbone.split(" ")):
                        bone_obj = next((obj for obj in context.view_layer.objects if (obj_name + ".mpet") in obj.name), None)
                        if not bone_obj:
                            continue
                        bone_obj.hide_set(False)

                def hideclub():
                    cmd_hideclub = next((cmd for cmd in cmds if "hideclub" in cmd), None)
                    if not cmd_hideclub:
                        return
                    toggleclub(True)

                def showclub():
                    cmd_showclub = next((cmd for cmd in cmds if "showclub" in cmd), None)
                    if not cmd_showclub:
                        return
                    toggleclub(False)
                
                ptex()
                hidebone()
                showbone()
                hideclub()
                showclub()

            if frame_script not in bpy.app.handlers.frame_change_pre:
                bpy.app.handlers.frame_change_pre.append(frame_script)

            # update current frame after set handler
            context.scene.frame_set(context.scene.frame_current)

        bpy.ops.object.mode_set(mode='OBJECT')

    if anim_enable:
        InitAnimation()

    # set matrix world of mesh object and armature object to bpet armature object matrix world after animation
    if model.is_mpet and bpet_armature_obj:
        armature_obj.matrix_world = bpet_armature_obj.matrix_world
        mesh_obj.matrix_world = bpet_armature_obj.matrix_world

    # set matrix world of camera after animation
    if is_camera and 'armature_parent_name' in armature_obj and bpy.data.objects.get(armature_obj['armature_parent_name']):
        armature_obj.matrix_world = bpy.data.objects[armature_obj['armature_parent_name']].matrix_world

    armature_obj.hide_render = True
    armature_obj.hide_set(True)

    bpy.ops.object.select_all(action='DESELECT')

    # ajusta clip_end com o tamanho do objeto
    if mesh_obj:
        updateScreenClipEnd(max(mesh_obj.dimensions) * 10)

    return [mesh_obj, model]

def load(operator, context, matrix):

    folder = pathlib.Path(operator.filepath)
    for selection in sorted(operator.files.values(), key=lambda e : -1 if os.path.splitext(e.name)[1] == '.bpet' else 0):
        fp = pathlib.Path(folder.parent, selection.name)
        if fp.suffix in operator.filename_ext.split(';'):
            with open(str(fp), 'rb') as file:
                load_pet(context, file, matrix, operator)

    return {'FINISHED'}
