# Copyright 2023-2026 Acrisio Filho

from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

import os
import time
import bpy # pyright: ignore[reportMissingImports]

from collections import defaultdict
from mathutils import Matrix # pyright: ignore[reportMissingImports]

from .pet import Puppet
from .texture_util import isBaseTexture, isNormalMaterial
from .util import (
    make4x3FromMatrix,
    mat4_to_length_mat4,
    mat4_to_ebone,
    calc_ebonemat,
    calc_original_vert_by_old_arm,
    ifnull,
    remove_unique_name,
    calcule_bound_box,
    is_valid_object,
    get_bone_weights_and_main_bone_weight,
    get_vertice_mpet_weight_global_value,
    get_face_material_espacular_index_name,
)

from .pet import (
    compareVersions,
    VERSION_1_2,
    VERSION_1_3,
    Puppet,
    Version,
    Bone,
    FaceAnimation,
    Texture,
    Extra,
    Collision,
    Mesh,
    Polygon,
    PolygonIndex,
    UVMapping,
    Vertex,
    BoneWeight,
    MpetExtraValue,
    Animation,
    Position,
    Rotation,
    Scaling,
    OrientationFlag,
    Frame,
    Motion,
    SpecularMaterial,
    SpecularValue,
    eSPECULAR_MATERIAL_TYPE
)

def save_pet(context, file, setting):
    # Save PangYa Model

    is_pet = True if setting.filename_ext == '.pet' else False
    is_apet = True if setting.filename_ext == '.apet' else False
    is_bpet = True if setting.filename_ext == '.bpet' else False
    is_mpet = True if setting.filename_ext == '.mpet' else False

    if not is_pet and not is_apet and not is_bpet and not is_mpet:
        raise Exception("Formato de arquivo inválido")
    
    arm_child = None
    arm_modifier = None
    obj = armature_obj = context.object

    if not obj or (obj.type != 'MESH' and obj.type != 'ARMATURE') or (obj.type == 'ARMATURE' and not is_apet and not is_bpet):
        raise Exception("Objeto selecionado inválido")

    if obj.type == 'MESH':
        arm_modifier = armature_obj = next((x.object for x in obj.modifiers if x.type == 'ARMATURE'), None)

        if not armature_obj:
            raise Exception("Objeto não tem uma armação")

        # usa a armação filho a do modifier pode ser a bpet armature
        arm_child = next((x for x in obj.children if x.type == 'ARMATURE'), None)

        if arm_child and arm_child.name != armature_obj.name:
            armature_obj = arm_child
    
    textures = []
    bones = []
    animations = []
    mesh = None
    face_anims = []
    frames = []
    motions = []
    extras = []
    collisions = []
    specular_materials = []
    mpet_arm_tmp = None
    arm_origin = None
    mpet_bone_name = None
    
    # Version
    major, minor = zip(setting.version.split(','))
    version = Version(int(major[0]), int(minor[0]))

    # select armature object
    armature_obj.select_set(True)
    context.view_layer.objects.active = armature_obj
    bpy.ops.object.mode_set(mode='OBJECT')

    # criar uma copia da armação
    if is_mpet and obj.type == "MESH":
        arm_origin = armature_obj
        mpet_arm_tmp = armature_obj.copy()
        mpet_arm_tmp.data = armature_obj.data.copy()
        armature_obj.users_collection[0].objects.link(mpet_arm_tmp)
        armature_obj = mpet_arm_tmp

        # select armature object copy
        armature_obj.select_set(True)
        context.view_layer.objects.active = armature_obj
        bpy.ops.object.mode_set(mode='EDIT')

        mpet_bone_name = ifnull(obj.get("mpet_bone_name"), os.path.splitext(os.path.basename(file.name))[0].upper())

        for eb in armature_obj.data.edit_bones[1:]:
            if eb.name != mpet_bone_name and eb.name not in obj.vertex_groups.keys():
                armature_obj.data.edit_bones.remove(eb)

        # cria o bone do mpet name se não tiver
        mpet_bone = next((bmpet for bmpet in armature_obj.data.edit_bones if bmpet.name == mpet_bone_name), None)
        if not mpet_bone:
            eb = armature_obj.data.edit_bones.new(mpet_bone_name)
            armature_obj.data.edit_bones.active = eb

            eb.use_deform = True
            eb.orientation_flag = -1.0

            # matrix(local)
            mat4_to_ebone(eb, Matrix.Identity(4))
            
            eb.length, eb.matrix = mat4_to_length_mat4(calc_ebonemat(eb))

        # force update
        bpy.ops.object.mode_set(mode='OBJECT')

        # recalcule matrix local pangya of bone after remove unnecessary bones
        for eb in armature_obj.data.bones:
            eb["matrix_local_pangya"] = (eb.parent.matrix_local.inverted() if eb.parent else Matrix.Identity(4)) @ eb.matrix_local

    # Bones
    for bone in armature_obj.data.bones:

        bones.append(Bone(
            remove_unique_name(bone.name),
            -1 if not bone.parent else armature_obj.data.bones.find(bone.parent.name),
            make4x3FromMatrix((bone.parent.matrix_local.inverted() if bone.parent else Matrix.Identity(4)) @ bone.matrix_local),
            float(ifnull(bone.orientation_flag, -1.0))
        ))

    # cria o bone do pet se não tiver ele
    if is_pet:
        pet_bone_name = os.path.splitext(os.path.basename(file.name))[0]
        pet_bone = next((bpet for bpet in armature_obj.data.bones if bpet.name == pet_bone_name), None)
        if not pet_bone:
            bones.append(Bone(
                pet_bone_name,
                -1,
                make4x3FromMatrix(Matrix.Identity(4)),
                -1.0
            ))
    
    # mesh, textures e face animations
    if obj.type == 'MESH' and (is_pet or is_mpet):
        
        # textures e face animations
        if len(obj.data.materials) > 0:
            for material in [mtrl for mtrl in obj.data.materials if isNormalMaterial(mtrl)]:
                # excluí especular material
                image_path = next((os.path.basename(x.image.filepath) for x in material.node_tree.nodes if x.type == 'TEX_IMAGE' and x.image and x.image.filepath and isBaseTexture(x) and os.path.basename(x.image.filepath)[0] != '!'), None)

                # excluí especular material
                if material.name[0] != '!':
                    face_anims.append(FaceAnimation(
                        int(ifnull(material.get("group"), 0)),
                        os.path.splitext(remove_unique_name(material.name))[0],
                        ifnull(image_path, "null")
                    ))

                textures.append(Texture(
                    image_path if image_path else remove_unique_name(material.name),
                    int(ifnull(material.get("flag"), 0)),
                    int(ifnull(material.get("group"), 0)),
                    int(ifnull(material.get("diffuse"), 0xFFFFFFFF), 16),
                    int(ifnull(material.get("handle"), 0))
                ))

        # mesh
        vertexes = []

        is_bpet_current_draw_armature = is_valid_object(obj.data.current_draw_armature) and obj.data.current_draw_armature != arm_child and obj.data.current_draw_armature == arm_modifier and ".bpet" in arm_modifier.name

        for vertice in obj.data.vertices:
            total_weight = 0
            weights = []

            main_bone_weight, bone_weights = get_bone_weights_and_main_bone_weight(obj, vertice)

            for bone_name, weight in bone_weights:
                bone_idx = armature_obj.data.bones.find(bone_name)
                if bone_idx >= 0:
                    weights.append(BoneWeight(weight, bone_idx))
                    total_weight += weight

            # normalize
            if total_weight not in [0,1]:
                for link in weights:
                    link.weight *= 1/total_weight

            # valids
            weights = [weight for weight in weights if weight.weight > 0]

            # to 255
            for link in weights:
                link.weight = int(round(link.weight * 255))

            co = calc_original_vert_by_old_arm(
                vertice.co,
                bone_weights,
                arm_modifier if is_bpet_current_draw_armature else armature_obj,
                armature_obj if is_bpet_current_draw_armature else None
            )
            
            vertexes.append(Vertex(
                co.x,
                co.y,
                co.z,
                get_vertice_mpet_weight_global_value(obj, vertice), # mpet weight global
                weights
            ))

        polygons = []
        texmap = []
        texmap_specular = []
        material_specular_index_attr = obj.data.attributes.get(get_face_material_espacular_index_name())
        for poly in obj.data.polygons:
            texmap.append(int(poly.material_index))

            if material_specular_index_attr:
                texmap_specular.append(material_specular_index_attr.data[poly.index].value)

            polygons_indexes = []
            for loop in [obj.data.loops[l] for l in poly.loop_indices]:
                polygons_indexes.append(PolygonIndex(
                    loop.vertex_index,
                    loop.normal.x,
                    loop.normal.y,
                    loop.normal.z,
                    [ UVMapping(uv_layer.data[loop.index].uv.x, 1 - uv_layer.data[loop.index].uv.y) for uv_layer in obj.data.uv_layers ]
                ))
            if len(polygons_indexes) > 0:
                polygons.append(Polygon(polygons_indexes))
        
        mpetexs = []
        if is_mpet:
            mpetexs.append(MpetExtraValue(
                int((lambda a, b: a if a >= 0 else b)(armature_obj.data.bones.find(mpet_bone_name), 0)),
                0,
                len(vertexes),
                0,
                len(polygons)
            ))
        
        mesh = Mesh(
            vertexes,
            polygons,
            texmap,
            mpetexs,
            texmap_specular
        )

    # extras e collision
    if is_pet or is_bpet:

        # extras
        extras_obj = next((x for x in armature_obj.children if 'Extras' in x.name), None)
        if extras_obj and len(extras_obj.children) > 0:
            for extra in extras_obj.children:
                extras.append(Extra(
                    int(armature_obj.data.bones.find(ifnull(extra.get("bone_name"), "Unknown")))
                ))
        
        # collision
        collisions_obj = next((x for x in armature_obj.children if "Collisions" in x.name), None)
        if collisions_obj and len(collisions_obj.children) > 0:
            for collision in collisions_obj.children:
                collisions.append(Collision(
                    int(ifnull(collision.get("shape"), 0)),
                    int(ifnull(collision.get("show"), 1)),
                    [
                        ifnull(collision.get("script00"), ''),
                        ifnull(collision.get("script01"), ''),
                        ifnull(collision.get("script02"), ''),
                        ifnull(collision.get("script03"), '')
                    ],
                    calcule_bound_box(collision)
                ))

    # specular materials
    if is_pet or is_mpet:
        specular_materials_obj = next((x for x in obj.children if "Specular Materials" in x.name), None)
        if specular_materials_obj and len(specular_materials_obj.children) > 0:
            for smtl in sorted(specular_materials_obj.children, key=lambda x: int(ifnull(x.get('index'), 0))):
                smtlvs = []
                for smtlv in smtl.children:
                    type = smtlv.get("type")
                    if not type or not isinstance(type, int):
                        continue
                    
                    value = smtlv.get("value")
                    if type == eSPECULAR_MATERIAL_TYPE.SMTL_BOOL:
                        value = 1 if value else 0
                    elif type == eSPECULAR_MATERIAL_TYPE.SMTL_VECTOR2:
                        value = [smtlv.location[0], smtlv.locatioin[1]]
                    elif type == eSPECULAR_MATERIAL_TYPE.SMTL_VECTOR3:
                        value = [smtlv.location[0], smtlv.location[1], smtlv.location[2]]
                    elif type == eSPECULAR_MATERIAL_TYPE.SMTL_VECTOR4:
                        smtlv.rotation_mode = 'QUATERNION'
                        value = [smtlv.rotation_quaternion[1], smtlv.rotation_quaternion[2], smtlv.rotation_quaternion[3], smtlv.rotation_quaternion[0]]
                    elif type == eSPECULAR_MATERIAL_TYPE.SMTL_MATRIX:
                        value = make4x3FromMatrix(smtlv.matrix_world)
                    
                    smtlvs.append(SpecularValue(
                        remove_unique_name(smtlv.name),
                        type,
                        value
                    ))

                specular_materials.append(SpecularMaterial(
                    remove_unique_name(smtl.name),
                    smtlvs
                ))

    # animations, frames e motions
    if is_pet or is_apet:
        
        def getActionAndActionBag(arm):

            if not arm or not arm.animation_data or not arm.animation_data.action:
                return None, None

            action = arm.animation_data.action

            action_bag = action
            if bpy.app.version >= (5, 0, 0):
                if not action.layers or not action.layers[0].strips or not action.layers[0].strips[0].channelbags:
                    return None, None

                action_bag = action.layers[0].strips[0].channelbags[0]

            return action, action_bag

        action, action_bag = getActionAndActionBag(armature_obj)

        # animations
        if action and action_bag and len(action_bag.fcurves) > 0:

            curr_action_influence = armature_obj.animation_data.action_influence
            armature_obj.animation_data.action_influence = 1.0

            def animationLength(ad):
                if ad.action:
                    return int(ad.action.frame_range[1])
                else:
                    strips = [strip.frame_end for track in ad.nla_tracks if not track.mute for strip in track.strips]
                    if strips:
                        return int(max(strips))
                    else:
                        return 0
        
            bpy.ops.object.mode_set(mode='POSE')

            anim_len = animationLength(armature_obj.animation_data) + 1

            curr_frame = bpy.context.scene.frame_current

            for pbone in armature_obj.pose.bones:
                pbone.matrix_basis.identity()

            keyframes = defaultdict(dict)
            for bone in armature_obj.pose.bones:
                positions = []
                rotations = []
                scalings = []
                orientation_flags = []

                bone_string_position = "pose.bones[\"{}\"].location".format(bone.name)
                bone_string_rotation = "pose.bones[\"{}\"].rotation_quaternion".format(bone.name)
                bone_string_scaling = "pose.bones[\"{}\"].scale".format(bone.name)
                bone_string_orientation_flag = "pose.bones[\"{}\"][\"orientation_flag\"]".format(bone.name)

                fcurve_positions = list(filter(lambda x: x.data_path == bone_string_position, action_bag.fcurves))
                fcurve_rotations = list(filter(lambda x: x.data_path == bone_string_rotation, action_bag.fcurves))
                fcurve_scalings = list(filter(lambda x: x.data_path == bone_string_scaling, action_bag.fcurves))
                fcurve_orientation_flags = list(filter(lambda x: x.data_path == bone_string_orientation_flag, action_bag.fcurves))

                # positions
                if len(fcurve_positions) > 0:
                    positions.extend([{"time": kpt.co[0] / 30} for kpt in fcurve_positions[0].keyframe_points])

                # rotations
                if len(fcurve_rotations) > 0:
                    rotations.extend([{"time": kpt.co[0] / 30} for kpt in fcurve_rotations[0].keyframe_points])

                # scalings
                if len(fcurve_scalings) > 0:
                    scalings.extend([{"time": kpt.co[0] / 30} for kpt in fcurve_scalings[0].keyframe_points])

                # orientation_flags
                if len(fcurve_orientation_flags) > 0:
                    orientation_flags.extend([{"time": kpt.co[0] / 30} for kpt in fcurve_orientation_flags[0].keyframe_points])

                for pos in positions:
                    f = round((pos["time"] * 30))
                    keyframes[bone][f] = {"pos": True, "rot": False, "scale": False, "ori": False}
                for rot in rotations:
                    f = round((rot["time"] * 30))
                    kf = keyframes[bone].get(f)
                    if kf:
                        kf["rot"] = True
                    else:
                        keyframes[bone][f] = {"pos": False, "rot": True, "scale": False, "ori": False}
                for sca in scalings:
                    f = round((sca["time"] * 30))
                    kf = keyframes[bone].get(f)
                    if kf:
                        kf["scale"] = True
                    else:
                        keyframes[bone][f] = {"pos": False, "rot": False, "scale": True, "ori": False}
                for ori in orientation_flags:
                    f = round((ori["time"] * 30))
                    kf = keyframes[bone].get(f)
                    if kf:
                        kf["ori"] = True
                    else:
                        keyframes[bone][f] = {"pos": False, "rot": False, "scale": False, "ori": True}

            # remove empty keyframes
            for bone,fs in list(keyframes.items()):
                if len(fs.values()) == 0:
                    del keyframes[bone]

            # print num animation frames
            print("export animation total frames: %d" % anim_len)

            kfs = defaultdict(dict)
            frame_10_percent = anim_len // 10 if anim_len >= 10 else 1
            for i in range(anim_len):
                bpy.context.scene.frame_set(i)

                # print % of exporting frames
                if (i % frame_10_percent) == 0 or i == (anim_len - 1):
                    print(f"exporting frames: {round((i / anim_len) * 100, 2)}%")

                for pbone in armature_obj.pose.bones:
        
                    if len(kfs[pbone]) == 0:
                        kfs[pbone] = {
                            "positions": [],
                            "rotations": [],
                            "scalings": [],
                            "orientation_flags": []
                        }

                    matrix = pbone.matrix

                    # Tirando a escala mas mantendo a mesma posição e rotação para as versões menores que 1.2 que não tem escala na animação
                    if compareVersions(version, VERSION_1_2) < 0:
                        matrix = Matrix.LocRotScale(*matrix.decompose()[:2], (1, 1, 1))
                        if pbone.parent:
                            matrix = Matrix.LocRotScale(*pbone.parent.matrix.decompose()[:2], (1, 1, 1)).inverted() @ matrix
                    else:
                        if pbone.parent:
                            matrix = pbone.parent.matrix.inverted() @ matrix

                    kf_keyed = keyframes[pbone].get(i)
        
                    location = matrix.to_translation()
                    if kf_keyed and kf_keyed["pos"]:
                        kfs[pbone]["positions"].append(Position(
                            i / 30.0,
                            [
                                location.x,
                                location.y,
                                location.z
                            ]
                        ))

                    rotation = matrix.to_quaternion()
                    # pangya rotation.w negative(x, y, z)
                    rotation = rotation.inverted().normalized()
                    if kf_keyed and kf_keyed["rot"]:
                        kfs[pbone]["rotations"].append(Rotation(
                            i / 30.0,
                            [
                                rotation.x,
                                rotation.y,
                                rotation.z,
                                rotation.w
                            ]
                        ))

                    scale = matrix.to_scale()
                    if kf_keyed and kf_keyed["scale"]:
                        kfs[pbone]["scalings"].append(Scaling(
                            i / 30.0,
                            [
                                scale.x,
                                scale.y,
                                scale.z
                            ]
                        ))
                    
                    if kf_keyed and kf_keyed["ori"]:
                        kfs[pbone]["orientation_flags"].append(OrientationFlag(
                            i / 30.0,
                            float(ifnull(pbone.orientation_flag, -1.0))
                        ))

            for pbone,kf in kfs.items():

                if len(kf["positions"]) == 0 and len(kf["rotations"]) == 0 and len(kf["scalings"]) == 0 and len(kf["orientation_flags"]) == 0:
                    continue

                # se não tiver o keyframe de escala na versão 1.2 ou maior, tem que adicionar o primeiro e ultimo keyframe com o valor padrão do osso
                if compareVersions(version, VERSION_1_2) >= 0 and len(kf["scalings"]) == 0:
                    for i in [0, anim_len - 1]:
                        kf["scalings"].append(Scaling(
                            i / 30.0,
                            [
                                *pbone.bone.matrix_local.to_scale()
                            ]
                        ))

                # se não tiver o keyframe de orientation_flag na versão 1.3 ou maior, tem que adicionar o primeiro e ultimo keyframe com o valor padrão do osso
                if compareVersions(version, VERSION_1_3) >= 0 and len(kf["orientation_flags"]) == 0:
                    for i in [0, anim_len - 1]:
                        kf["orientation_flags"].append(OrientationFlag(
                            i / 30.0,
                            float(ifnull(pbone.bone.orientation_flag, -1.0))
                        ))

                bone_id = armature_obj.data.bones.find(pbone.name)

                if bone_id >= 0:
                    animations.append(Animation(
                        bone_id,
                        kf["positions"],
                        kf["rotations"],
                        kf["scalings"],
                        kf["orientation_flags"]
                    ))

            armature_obj.animation_data.action_influence = curr_action_influence
            bpy.context.scene.frame_set(curr_frame)

        # frames
        frames_obj = next((x for x in armature_obj.children if "Frames" in x.name), None)
        if frames_obj and len(frames_obj.children) > 0:
            for frame in sorted(frames_obj.children, key=lambda x: int(ifnull(x.get('index'), 0))):
                frames.append(Frame(
                    int(ifnull(frame.get('index'), 0)),
                    ifnull(frame.get('script'), ''),
                    int(ifnull(frame.get('check'), 0))
                ))

        # motions
        motions_obj = next((x for x in armature_obj.children if "Motions" in x.name), None)
        if motions_obj and len(motions_obj.children) > 0:
            for motion in sorted(motions_obj.children, key=lambda x: int(ifnull(x.get('frame_start'), 0))):
                motions.append(Motion(
                    ifnull(motion.get("name"), remove_unique_name(motion.name)),
                    int(ifnull(motion.get('frame_start'), 0)),
                    int(ifnull(motion.get('frame_end'), 0)),
                    ifnull(motion.get('next_move'), ''),
                    ifnull(motion.get('connection_method'), ''),
                    float(ifnull(motion.get('connection_time'), 0.0)),
                    ifnull(motion.get('root_bone'), '')
                ))

    # clean
    if mpet_arm_tmp:
        bpy.data.armatures.remove(mpet_arm_tmp.data)
        mpet_arm_tmp = None

        # select origin armature
        arm_origin.select_set(True)
        context.view_layer.objects.active = arm_origin

    # Puppet
    model = Puppet(
        version,
        bones,
        extras,
        mesh,
        textures,
        animations,
        face_anims,
        frames,
        motions,
        collisions,
        specular_materials
    )

    # save to file
    model.save(file, setting.ignore_frame_limitation, setting.ignore_animation_bone_limitation)

    # select object
    bpy.ops.object.mode_set(mode='OBJECT')

    obj.select_set(True)
    context.view_layer.objects.active = obj

def save(operator, context):

    print('export pangya model: %r' % (operator.filepath))

    time1 = time.process_time()

    with open(operator.filepath, 'wb') as file:
        save_pet(context, file, operator)

    print('export done in %.4f sec.' % (time.process_time() - time1))
    
    return {'FINISHED'}