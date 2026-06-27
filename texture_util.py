# Copyright 2023-2026 Acrisio Filho

import bpy, os, pathlib, re # pyright: ignore[reportMissingImports]

from .pet import eSPECULAR_MATERIAL_TYPE
from .util import (
    load_texture_path,
    loadImage,
    make_unique_name,
    remove_and_make_unique_name,
    is_valid_object,
    get_face_material_espacular_index_name
)

def getMaterialTypeName():
    return "TYPE_MTRL"

def isNormalMaterial(material):
    if not material:
        return False
    t = material.get(getMaterialTypeName(), None)
    return t != None and t == "NORMAL"

def initMaterialType(material, type="NORMAL"):
    if not material:
        return
    material[getMaterialTypeName()] = type

def getBaseTextureName():
    return "BASE_TEX_FLAG_NAME"

def isBaseTexture(texNode):
    return texNode and texNode.get(getBaseTextureName())

def initBaseTextureFlag(texNode):
    if not texNode:
        return
    texNode[getBaseTextureName()] = True

def getMaterialFlagsByName(_name):
    flags_char = _name[:5]

    return {
        "mask1": "[" in flags_char,
        "mask2": "+" in flags_char,
        "mask3": "}" in flags_char,
        "mask4": "^" in flags_char,
        "blending": "]" in flags_char,
        "specular": "!" in flags_char,
        "chroma_key_blue": "{" in flags_char,
        "chroma_key_black": "~" in flags_char,
        "unknown_flag": "@" in flags_char
    }

def getMaterialIndex(mtrl_full_name, face_anims):
    return next((index for index,mtrl in enumerate(face_anims) if mtrl.material_name == mtrl_full_name), -1)

def setMaterialFlags(material, mtrl_full_name, mtrl_flags, mtrl_idx):

    if mtrl_flags["blending"] or (mtrl_flags["mask2"] and re.search(r"_\d+$", mtrl_full_name)) or ("ball" in material.name and mtrl_idx == 0):
        material.blend_method = 'BLEND'
    else:
        material.blend_method = 'CLIP'
    material.show_transparent_back = False
    material.alpha_threshold = 0.4

    if bpy.app.version < (4, 1, 0):
        material.shadow_method = 'CLIP'

# [ have mask or transparent dds
# + have mask or transparent dds
# } have mask or transparent dds
# ] blending alpha
# ! specular material
# { chroma key blue
# ~ chroma key black
# @ unknown
# ^ have mask
def import_material_v280(face_anims, materials, mtrl, filepath):
    
    dirname = os.path.dirname(filepath)

    # construct material
    material_name = next((fanim.name for fanim in face_anims if fanim.material_name == mtrl.fn), mtrl.fn)
    material_index = getMaterialIndex(mtrl.fn, face_anims)
    material_flags = getMaterialFlagsByName(mtrl.fn)

    new_mtrl = bpy.data.materials.new(make_unique_name(material_name))
    initMaterialType(new_mtrl, "NORMAL")
    if bpy.app.version < (5, 0, 0):
        new_mtrl.use_nodes = True
    output_node = next((out for out in new_mtrl.node_tree.nodes if out.__class__.__name__ == "ShaderNodeOutputMaterial"), None)
    if output_node is None:
        output_node = new_mtrl.node_tree.nodes.new("ShaderNodeOutputMaterial")

    # remove unused nodes
    nodes_to_remove = [n for n in new_mtrl.node_tree.nodes if n != output_node]
    for n in nodes_to_remove:
        new_mtrl.node_tree.nodes.remove(n)

    new_image = None
    # não tem textura
    if mtrl.fn is not None and mtrl.fn != 'null':
        # open image
        image_path = load_texture_path(dirname, mtrl.fn)
        if pathlib.Path(image_path).exists():
            base, ext = os.path.splitext(image_path)
            if material_flags["specular"] and len(materials) > 0:
                # specular material
                specular_img = loadImage(image_path)

                for mat in materials:
                    output_node_m = next((out for out in mat.node_tree.nodes if out.__class__.__name__ == "ShaderNodeOutputMaterial"), None)
                    if not output_node_m or len(output_node_m.inputs["Surface"].links) == 0:
                        continue
                    before_oupt_node = output_node_m.inputs["Surface"].links[0].from_node
                    if not before_oupt_node:
                        continue

                    # make texture node
                    specular_texnode = mat.node_tree.nodes.new("ShaderNodeTexImage")
                    specular_texnode.location[1] = output_node_m.location[1]
                    specular_texnode.image = specular_img
                    specular_texnode.projection = 'FLAT'

                    # make mixer specular node
                    mixer_specular_node = mat.node_tree.nodes.new("ShaderNodeMixShader")
                    mixer_specular_node.location[1] = output_node_m.location[1]

                    # make mixer node
                    mixer_node = mat.node_tree.nodes.new("ShaderNodeMixShader")
                    mixer_node.location[1] = output_node_m.location[1]
                
                    # make transparent node
                    trans_node = mat.node_tree.nodes.new("ShaderNodeBsdfTransparent")
                    trans_node.location[1] = output_node_m.location[1]

                    # make specular node
                    specular_node = mat.node_tree.nodes.new("ShaderNodeEeveeSpecular")
                    specular_node.location[1] = output_node_m.location[1]
                    specular_node.inputs["Base Color"].default_value = (1, 1, 1, 1)
                    specular_node.inputs["Roughness"].default_value = 0.35

                    mat.node_tree.links.new(specular_node.inputs["Base Color"], specular_texnode.outputs["Color"])
                    mat.node_tree.links.new(mixer_specular_node.inputs[0], specular_texnode.outputs["Alpha"])
                    mat.node_tree.links.new(mixer_specular_node.inputs[1], trans_node.outputs["BSDF"])
                    mat.node_tree.links.new(mixer_specular_node.inputs[2], specular_node.outputs["BSDF"])
                    mat.node_tree.links.new(mixer_node.inputs[1], before_oupt_node.outputs[0])
                    mat.node_tree.links.new(mixer_node.inputs[2], mixer_specular_node.outputs["Shader"])
                    mat.node_tree.links.new(output_node_m.inputs["Surface"], mixer_node.outputs["Shader"])

                    # apenas no primeiro
                    break

                # make texture node
                texture_node = new_mtrl.node_tree.nodes.new("ShaderNodeTexImage")
                texture_node.location[1] = output_node.location[1]
                texture_node.image = new_image
                texture_node.projection = 'FLAT'
                initBaseTextureFlag(texture_node)

                new_mtrl.node_tree.links.new(output_node.inputs["Surface"], texture_node.outputs["Color"])
                
            elif ext == '.dds' or ext == '.png': # Arquivos com transparência
                # mask texture
                new_image = loadImage(image_path)
                
                # make texture node
                texture_node = new_mtrl.node_tree.nodes.new("ShaderNodeTexImage")
                texture_node.location[1] = output_node.location[1]
                texture_node.image = new_image
                texture_node.projection = 'FLAT'
                initBaseTextureFlag(texture_node)

                # make BsdfPrincipled
                bsdfPre_node = new_mtrl.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
                bsdfPre_node.location[1] = output_node.location[1]
                bsdfPre_node.inputs["IOR"].default_value = 1.0

                # make mixer node
                mixer_node = new_mtrl.node_tree.nodes.new("ShaderNodeMixShader")
                mixer_node.location[1] = output_node.location[1]
                
                # make transparent node
                trans_node = new_mtrl.node_tree.nodes.new("ShaderNodeBsdfTransparent")
                trans_node.location[1] = output_node.location[1]

                new_mtrl.node_tree.links.new(mixer_node.inputs[0], texture_node.outputs["Alpha"])
                new_mtrl.node_tree.links.new(mixer_node.inputs[1], trans_node.outputs["BSDF"])
                new_mtrl.node_tree.links.new(mixer_node.inputs[2], bsdfPre_node.outputs["BSDF"])
                new_mtrl.node_tree.links.new(bsdfPre_node.inputs["Base Color"], texture_node.outputs["Color"])
                new_mtrl.node_tree.links.new(bsdfPre_node.inputs["Alpha"], texture_node.outputs["Alpha"])
                new_mtrl.node_tree.links.new(output_node.inputs["Surface"], mixer_node.outputs["Shader"])

                setMaterialFlags(new_mtrl, mtrl.fn, material_flags, material_index)

            elif (material_flags["mask1"] or material_flags["mask2"] or material_flags["mask3"] or material_flags["mask4"]) and pathlib.Path("{}_mask{}".format(base, ext)).exists(): # Arquivos sem transparência
                # mask texture
                new_image = loadImage(image_path)
                mask_image = loadImage("{}_mask{}".format(base, ext))

                # make texture node
                texture_node = new_mtrl.node_tree.nodes.new("ShaderNodeTexImage")
                texture_node.location[1] = output_node.location[1]
                texture_node.image = new_image
                texture_node.projection = 'FLAT'
                initBaseTextureFlag(texture_node)

                # make mask node
                mask_node = new_mtrl.node_tree.nodes.new("ShaderNodeTexImage")
                mask_node.location[1] = output_node.location[1]
                mask_node.image = mask_image
                mask_node.projection = 'FLAT'

                # make BsdfPrincipled
                bsdfPre_node = new_mtrl.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
                bsdfPre_node.location[1] = output_node.location[1]
                bsdfPre_node.inputs["IOR"].default_value = 1.0

                # make mixer node
                mixer_node = new_mtrl.node_tree.nodes.new("ShaderNodeMixShader")
                mixer_node.location[1] = output_node.location[1]
                
                # make transparent node
                trans_node = new_mtrl.node_tree.nodes.new("ShaderNodeBsdfTransparent")
                trans_node.location[1] = output_node.location[1]

                new_mtrl.node_tree.links.new(mixer_node.inputs[0], mask_node.outputs["Color"])
                new_mtrl.node_tree.links.new(mixer_node.inputs[1], trans_node.outputs["BSDF"])
                new_mtrl.node_tree.links.new(mixer_node.inputs[2], bsdfPre_node.outputs["BSDF"])
                new_mtrl.node_tree.links.new(bsdfPre_node.inputs["Base Color"], texture_node.outputs["Color"])
                new_mtrl.node_tree.links.new(output_node.inputs["Surface"], mixer_node.outputs["Shader"])

                setMaterialFlags(new_mtrl, mtrl.fn, material_flags, material_index)

            else:
                new_image = loadImage(image_path)

                # make texture node
                texture_node = new_mtrl.node_tree.nodes.new("ShaderNodeTexImage")
                texture_node.location[1] = output_node.location[1]
                texture_node.image = new_image
                texture_node.projection = 'FLAT'
                initBaseTextureFlag(texture_node)

                # make BsdfPrincipled
                bsdfPre_node = new_mtrl.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
                bsdfPre_node.location[1] = output_node.location[1]
                bsdfPre_node.inputs["IOR"].default_value = 1.0
                
                new_mtrl.node_tree.links.new(bsdfPre_node.inputs["Base Color"], texture_node.outputs["Color"])
                new_mtrl.node_tree.links.new(bsdfPre_node.inputs["Alpha"], texture_node.outputs["Alpha"])
                new_mtrl.node_tree.links.new(output_node.inputs["Surface"], bsdfPre_node.outputs["BSDF"])

        new_mtrl['flag'] = "%d" % mtrl.flag
        new_mtrl['group'] = "%d" % mtrl.group
        new_mtrl['diffuse'] = "0x%.08x" % mtrl.diffuse
        new_mtrl['handle'] = "%d" % mtrl.handle

    else:
        # make specular node
        specular_node = new_mtrl.node_tree.nodes.new("ShaderNodeEeveeSpecular")
        specular_node.location[1] = output_node.location[1]
        specular_node.inputs["Base Color"].default_value = (1, 1, 1, 1)
        specular_node.inputs["Specular"].default_value = [
            0.0, 0.0, 0.0, 0.0
        ]
        specular_node.inputs["Emissive Color"].default_value = [
            0.2, 0.2, 0.2, 0.2
        ]
        new_mtrl.node_tree.links.new(output_node.inputs["Surface"],
                                     specular_node.outputs["BSDF"])

    return {"material": new_mtrl, "image": new_image}

def getOutPutNodeFromMat(mat):
    # type OUTPUT_MATERIAL
    output_node = next((out for out in mat.node_tree.nodes if out.__class__.__name__ == "ShaderNodeOutputMaterial"), None)
    if not output_node:
        return None

    return output_node

# get or make node group specular material mix color with mutiply
def getSpecialMaterialMixWithMultiplyNodeGroup():
    group_name = "SPECULAR_MATERIAL_MIX_WITH_MUTLIPLY_NODE_GROUP_NAME"

    if group_name in bpy.data.node_groups:
        return bpy.data.node_groups[group_name]
    
    group = bpy.data.node_groups.new(group_name, "ShaderNodeTree")

    if bpy.app.version < (4, 0, 0):
        group.inputs.new("NodeSocketFloat", "Fac1")
        group.inputs.new("NodeSocketFloat", "Fac2")
        group.inputs.new("NodeSocketFloat", "Fac3")
        group.inputs.new("NodeSocketColor", "A")
        group.inputs.new("NodeSocketColor", "B")
        group.outputs.new("NodeSocketColor", "Color")
    else:
        group.interface.new_socket(name="Fac1", in_out="INPUT", socket_type="NodeSocketFloat")
        group.interface.new_socket(name="Fac2", in_out="INPUT", socket_type="NodeSocketFloat")
        group.interface.new_socket(name="Fac3", in_out="INPUT", socket_type="NodeSocketFloat")
        group.interface.new_socket(name="A", in_out="INPUT", socket_type="NodeSocketColor")
        group.interface.new_socket(name="B", in_out="INPUT", socket_type="NodeSocketColor")
        group.interface.new_socket(name="Color", in_out="OUTPUT", socket_type="NodeSocketColor")

    nodes = group.nodes
    input_node = nodes.new("NodeGroupInput")
    output_node = nodes.new("NodeGroupOutput")

    # Math Multiply Node
    math_multiply_node = nodes.new("ShaderNodeMath")
    math_multiply_node.location[1] = output_node.location[1]
    math_multiply_node.operation = "MULTIPLY"

    # Math Multiply Node
    math_multiply_node2 = nodes.new("ShaderNodeMath")
    math_multiply_node2.location[1] = output_node.location[1]
    math_multiply_node2.operation = "MULTIPLY"

    # Mixer Color Node
    mix_color_node = nodes.new("ShaderNodeMix")
    mix_color_node.location[1] = output_node.location[1]
    mix_color_node.data_type = "RGBA"
    mix_color_node.blend_type = "MIX"

    group.links.new(math_multiply_node.inputs[0], input_node.outputs["Fac1"])
    group.links.new(math_multiply_node.inputs[1], input_node.outputs["Fac2"])
    group.links.new(math_multiply_node2.inputs[0], math_multiply_node.outputs[0])
    group.links.new(math_multiply_node2.inputs[1], input_node.outputs["Fac3"])

    group.links.new(mix_color_node.inputs[0], math_multiply_node2.outputs[0])
    group.links.new(mix_color_node.inputs["A"], input_node.outputs["A"])
    group.links.new(mix_color_node.inputs["B"], input_node.outputs["B"])

    group.links.new(output_node.inputs["Color"], mix_color_node.outputs["Result"])

    return group

# get or make node group specular material switch by face material specular
def getSpecialMaterialSwitchNodeGroup():
    group_name = "SPECULAR_MATERIAL_MIX_WITH_SWITCH_NODE_GROUP_NAME"

    if group_name in bpy.data.node_groups:
        return bpy.data.node_groups[group_name]
    
    group = bpy.data.node_groups.new(group_name, "ShaderNodeTree")

    if bpy.app.version < (4, 0, 0):
        group.inputs.new("NodeSocketFloat", "Alpha1")
        group.inputs.new("NodeSocketFloat", "Alpha2")
        group.inputs.new("NodeSocketColor", "A")
        group.inputs.new("NodeSocketColor", "B")
        group.outputs.new("NodeSocketColor", "Color")
        group.outputs.new("NodeSocketFloat", "Alpha")
    else:
        group.interface.new_socket(name="Alpha1", in_out="INPUT", socket_type="NodeSocketFloat")
        group.interface.new_socket(name="Alpha2", in_out="INPUT", socket_type="NodeSocketFloat")
        group.interface.new_socket(name="A", in_out="INPUT", socket_type="NodeSocketColor")
        group.interface.new_socket(name="B", in_out="INPUT", socket_type="NodeSocketColor")
        group.interface.new_socket(name="Color", in_out="OUTPUT", socket_type="NodeSocketColor")
        group.interface.new_socket(name="Alpha", in_out="OUTPUT", socket_type="NodeSocketFloat")

    nodes = group.nodes
    input_node = nodes.new("NodeGroupInput")
    output_node = nodes.new("NodeGroupOutput")

    # make attribute node
    attribute_node = nodes.new("ShaderNodeAttribute")
    attribute_node.location[1] = output_node.location[1]
    attribute_node.attribute_name = get_face_material_espacular_index_name()

    # Math Greater Than Node
    math_greater_than_node = nodes.new("ShaderNodeMath")
    math_greater_than_node.location[1] = output_node.location[1]
    math_greater_than_node.operation = "GREATER_THAN"
    math_greater_than_node.inputs[1].default_value = -0.5

    # Mixer Float Node
    mix_float_node = nodes.new("ShaderNodeMix")
    mix_float_node.location[1] = output_node.location[1]
    mix_float_node.data_type = "FLOAT"
    mix_float_node.inputs[0].default_value = 1.0

    # Mixer Color Node
    mix_color_node = nodes.new("ShaderNodeMix")
    mix_color_node.location[1] = output_node.location[1]
    mix_color_node.data_type = "RGBA"
    mix_color_node.blend_type = "MIX"

    group.links.new(math_greater_than_node.inputs[0], attribute_node.outputs["Fac"])
    group.links.new(mix_float_node.inputs[0], math_greater_than_node.outputs[0])
    group.links.new(mix_color_node.inputs[0], math_greater_than_node.outputs[0])

    group.links.new(mix_color_node.inputs["A"], input_node.outputs["A"])
    group.links.new(mix_color_node.inputs["B"], input_node.outputs["B"])

    group.links.new(mix_float_node.inputs["A"], input_node.outputs["Alpha1"])
    group.links.new(mix_float_node.inputs["B"], input_node.outputs["Alpha2"])

    group.links.new(output_node.inputs["Color"], mix_color_node.outputs["Result"])
    group.links.new(output_node.inputs["Alpha"], mix_float_node.outputs["Result"])

    return group

# make specular materials
def makeSpecularMaterials(obj, spec_mat, idx):
    if not is_valid_object(obj):
        return

    if "light_splatting" in spec_mat.name:
        def makeSpecularMaterialGroup():
            group = bpy.data.node_groups.new(make_unique_name(spec_mat.name), "ShaderNodeTree")

            if bpy.app.version < (4, 0, 0):
                group.outputs.new("NodeSocketColor", "Color")
                group.outputs.new("NodeSocketFloat", "Alpha")
            else:
                group.interface.new_socket(name="Color", in_out="OUTPUT", socket_type="NodeSocketColor")
                group.interface.new_socket(name="Alpha", in_out="OUTPUT", socket_type="NodeSocketFloat")

            nodes = group.nodes
            output_node = nodes.new("NodeGroupOutput")
        
            smtlvs = [smtlv for smtlv in spec_mat.smtlvs if smtlv.type == eSPECULAR_MATERIAL_TYPE.SMTL_TEXTURE]

            len_mat = len(smtlvs)
            len_fx = int(spec_mat.name[3:4])

            if len_mat != len_fx:
                print("=========== WARNING ========", "specular material values len invalid. %d != %d" % (len_mat, len_fx), sep="\n")

            nodes_v = []
            for i in range(len_fx):
                nodes_v.append({})

                # make uv map node
                uvmap_node = nodes.new("ShaderNodeUVMap")
                uvmap_node.location[1] = output_node.location[1]
                uvmap_node.uv_map = "UVMap" if i == 0 else f"UVMap{i}"

                # make texture node
                image = None
                image_path = load_texture_path(obj["directory"], smtlvs[i].value)
                if pathlib.Path(image_path).exists():
                    image = loadImage(image_path)

                texture_node = nodes.new("ShaderNodeTexImage")
                texture_node.location[1] = output_node.location[1]
                texture_node.image = image
                texture_node.projection = 'FLAT'
                nodes_v[i]["texture"] = texture_node

                group.links.new(texture_node.inputs[0], uvmap_node.outputs[0])

                if i > 0:
                    # make uv map node
                    uvmap_node2 = nodes.new("ShaderNodeUVMap")
                    uvmap_node2.location[1] = output_node.location[1]
                    uvmap_node2.uv_map = f"UVMap{len_fx + i - 1}"

                    # make separate xyz node
                    separate_xyz_node = nodes.new("ShaderNodeSeparateXYZ")
                    separate_xyz_node.location[1] = output_node.location[1]

                    # Math Subtract Node
                    math_subtract_node = nodes.new("ShaderNodeMath")
                    math_subtract_node.location[1] = output_node.location[1]
                    math_subtract_node.operation = "SUBTRACT"
                    math_subtract_node.inputs[0].default_value = 1.0
                    nodes_v[i]["math_subtract"] = math_subtract_node

                    group.links.new(separate_xyz_node.inputs[0], uvmap_node2.outputs[0])
                    group.links.new(math_subtract_node.inputs[1], separate_xyz_node.outputs["X"])

                    # mixer values
                    mix_group = nodes.new("ShaderNodeGroup")
                    mix_group.location[1] = output_node.location[1]
                    mix_group.node_tree = getSpecialMaterialMixWithMultiplyNodeGroup()
                    nodes_v[i]["mix_group"] = mix_group

                    group.links.new(mix_group.inputs["Fac1"], nodes_v[0]["texture"].outputs["Alpha"])
                    group.links.new(mix_group.inputs["Fac2"], nodes_v[i]["texture"].outputs["Alpha"])
                    group.links.new(mix_group.inputs["Fac3"], nodes_v[i]["math_subtract"].outputs[0])

                    if i == 1:
                        group.links.new(mix_group.inputs["A"], nodes_v[0]["texture"].outputs["Color"])
                        group.links.new(mix_group.inputs["B"], nodes_v[i]["texture"].outputs["Color"])
                    else:
                        group.links.new(mix_group.inputs["A"], nodes_v[i - 1]["mix_group"].outputs["Color"])
                        group.links.new(mix_group.inputs["B"], nodes_v[i]["texture"].outputs["Color"])
        
            group.links.new(output_node.inputs["Color"], nodes_v[len_fx - 1]["mix_group"].outputs["Color"])
            group.links.new(output_node.inputs["Alpha"], nodes_v[0]["texture"].outputs["Alpha"])

            return group

        # insert group in material
        if idx >= len(obj.data.materials):
            # make specular material
            for _ in range(idx - len(obj.data.materials) + 1):
                new_mtrl = bpy.data.materials.new("Specular Material")
                initMaterialType("SPECULAR")
                if bpy.app.version < (5, 0, 0):
                    new_mtrl.use_nodes = True
                obj.data.append(new_mtrl)
        
        mat = obj.data.materials[idx]

        output_node = getOutPutNodeFromMat(mat)
        if not output_node:
            return

        tex_node = next((n for n in mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image and isBaseTexture(n)), None)
        if not tex_node:
            return
        
        specular_group = mat.node_tree.nodes.new("ShaderNodeGroup")
        specular_group.location[1] = output_node.location[1]
        specular_group.node_tree = makeSpecularMaterialGroup()

        switch_group = mat.node_tree.nodes.new("ShaderNodeGroup")
        switch_group.location[1] = output_node.location[1]
        switch_group.node_tree = getSpecialMaterialSwitchNodeGroup()

        to_socket_tex_color = tex_node.outputs["Color"].links[0].to_socket if tex_node.outputs["Color"].links else None
        if to_socket_tex_color:
            mat.node_tree.links.new(to_socket_tex_color, switch_group.outputs["Color"])

        for link in tex_node.outputs["Alpha"].links:
            mat.node_tree.links.new(link.to_socket, switch_group.outputs["Alpha"])

        mat.node_tree.links.new(switch_group.inputs["Alpha1"], tex_node.outputs["Alpha"])
        mat.node_tree.links.new(switch_group.inputs["Alpha2"], specular_group.outputs["Alpha"])

        mat.node_tree.links.new(switch_group.inputs["A"], tex_node.outputs["Color"])
        mat.node_tree.links.new(switch_group.inputs["B"], specular_group.outputs["Color"])

    else:
        print("=============WARNING===========", "Specular Material diferente de Light Splatting ainda não foi implementando: %s" % spec_mat.name, sep="\n")

# get or make node group vertex color filter
def getVertexColorFilterNodeGroup():
    group_name = "VERTEX_COLOR_FILTER_NODE_GROUP_NAME"

    if group_name in bpy.data.node_groups:
        return bpy.data.node_groups[group_name]
    
    group = bpy.data.node_groups.new(group_name, "ShaderNodeTree")

    if bpy.app.version < (4, 0, 0):
        group.inputs.new("NodeSocketColor", "Color")
        group.outputs.new("NodeSocketColor", "Color")
        group.outputs.new("NodeSocketFloat", "Alpha")
    else:
        group.interface.new_socket(name="Color", in_out="INPUT", socket_type="NodeSocketColor")
        group.interface.new_socket(name="Color", in_out="OUTPUT", socket_type="NodeSocketColor")
        group.interface.new_socket(name="Alpha", in_out="OUTPUT", socket_type="NodeSocketFloat")

    nodes = group.nodes
    input_node = nodes.new("NodeGroupInput")
    output_node = nodes.new("NodeGroupOutput")

    # vertex color
    vertex_color_node = nodes.new("ShaderNodeVertexColor")
    vertex_color_node.location[1] = output_node.location[1]
    vertex_color_node.layer_name = "Col"

    # Mixer Color Node
    mix_color_node = nodes.new("ShaderNodeMix")
    mix_color_node.location[1] = output_node.location[1]
    mix_color_node.data_type = "RGBA"
    mix_color_node.blend_type = "MULTIPLY"
    mix_color_node.inputs[0].default_value = 1.0

    group.links.new(mix_color_node.inputs["A"], input_node.outputs["Color"])
    group.links.new(mix_color_node.inputs["B"], vertex_color_node.outputs["Color"])

    group.links.new(output_node.inputs["Color"], mix_color_node.outputs["Result"])
    group.links.new(output_node.inputs["Alpha"], vertex_color_node.outputs["Alpha"])

    return group

# model base gbin shader vertex color filter
def makeVertexColorFilterToMaterial(mat):
    
    # pega o output node
    output_node = getOutPutNodeFromMat(mat)
    if not output_node:
        return

    bsdf_node = next((t for t in mat.node_tree.nodes if t.type == "BSDF_PRINCIPLED"), None)
    if not bsdf_node:
        return

    mix_node = next((t for t in mat.node_tree.nodes if t.type == "MIX_SHADER"), None)
    if not mix_node:
        return

    vtx_filter_group = mat.node_tree.nodes.new("ShaderNodeGroup")
    vtx_filter_group.location[1] = output_node.location[1]
    vtx_filter_group.node_tree = getVertexColorFilterNodeGroup()

    from_socket_base_color = bsdf_node.inputs["Base Color"].links[0].from_socket if bsdf_node.inputs["Base Color"].links else None
    if from_socket_base_color:
        mat.node_tree.links.new(vtx_filter_group.inputs["Color"], from_socket_base_color)

    mat.node_tree.links.new(bsdf_node.inputs["Base Color"], vtx_filter_group.outputs["Color"])
    mat.node_tree.links.new(mix_node.inputs[0], vtx_filter_group.outputs["Alpha"])

# make GBIN shadowmap Material
def makeGBinShadowmapMaterial(image):
    mat = bpy.data.materials.new(remove_and_make_unique_name(image.name))
    if bpy.app.version < (5, 0, 0):
        mat.use_nodes = True
    output_node = getOutPutNodeFromMat(mat)
    if output_node is None:
        output_node = mat.node_tree.nodes.new("ShaderNodeOutputMaterial")

    # remove unused nodes
    nodes_to_remove = [n for n in mat.node_tree.nodes if n != output_node]
    for n in nodes_to_remove:
        mat.node_tree.nodes.remove(n)

    # make texture node
    texture_node = mat.node_tree.nodes.new("ShaderNodeTexImage")
    texture_node.location[1] = output_node.location[1]
    texture_node.image = image
    texture_node.projection = 'FLAT'
    image.colorspace_settings.name = 'Non-Color'
    initBaseTextureFlag(texture_node)

    # make invert color node
    invert_color_node = mat.node_tree.nodes.new("ShaderNodeInvert")
    invert_color_node.location[1] = output_node.location[1]
    invert_color_node.inputs[0].default_value = 1.0

    # make mix color node
    mix_color_node = mat.node_tree.nodes.new("ShaderNodeMix")
    mix_color_node.location[1] = output_node.location[1]
    mix_color_node.data_type = 'RGBA'
    mix_color_node.blend_type = 'MIX'
    mix_color_node.inputs["A"].default_value = (0, 0, 0, 1)
    mix_color_node.inputs["B"].default_value = (1, 1, 1, 1)

    # make luiz suave node
    luiz_suave_node = mat.node_tree.nodes.new("ShaderNodeMix")
    luiz_suave_node.location[1] = output_node.location[1]
    luiz_suave_node.data_type = "RGBA"
    luiz_suave_node.blend_type = "SOFT_LIGHT"
    luiz_suave_node.clamp_result = True
    luiz_suave_node.inputs[0].default_value = 1.0

    # make gamma color node
    gamma_color_node = mat.node_tree.nodes.new("ShaderNodeGamma")
    gamma_color_node.location[1] = output_node.location[1]
    gamma_color_node.inputs[1].default_value = 0.3

    # make mixer node
    mixer_node = mat.node_tree.nodes.new("ShaderNodeMixShader")
    mixer_node.location[1] = output_node.location[1]
            
    # make transparent node
    trans_node = mat.node_tree.nodes.new("ShaderNodeBsdfTransparent")
    trans_node.location[1] = output_node.location[1]

    mat.node_tree.links.new(mix_color_node.inputs[0], texture_node.outputs["Color"])
    mat.node_tree.links.new(luiz_suave_node.inputs["A"], mix_color_node.outputs["Result"])
    mat.node_tree.links.new(luiz_suave_node.inputs["B"], mix_color_node.outputs["Result"])
    mat.node_tree.links.new(invert_color_node.inputs["Color"], luiz_suave_node.outputs["Result"])
    mat.node_tree.links.new(gamma_color_node.inputs["Color"], invert_color_node.outputs["Color"])
    mat.node_tree.links.new(mixer_node.inputs[0], gamma_color_node.outputs["Color"])
    mat.node_tree.links.new(mixer_node.inputs[1], trans_node.outputs["BSDF"])
    mat.node_tree.links.new(output_node.inputs["Surface"], mixer_node.outputs["Shader"])

    mat.blend_method = 'BLEND'
    mat.show_transparent_back = False
    mat.alpha_threshold = 0.4

    return mat

def findFaceMaterial(obj_armature, is_mpet):
    if is_mpet:
        # mpet(Mesh Puppet), Character
        char_letter = obj_armature.name.find("_")
        if char_letter == -1:
            return None
        fc_obj_name = obj_armature.name[:char_letter] + r"_fc_(def|\d)"
        fc_obj = next((obj for obj in bpy.context.view_layer.objects if obj.type == "MESH" and re.search(fc_obj_name, obj.name)), None)
        if not fc_obj:
            return None
        if len(fc_obj.data.materials) == 0:
            return None
        return fc_obj.data.materials[0]
    else:
        # Puppet, Caddie, NPC e etc
        obj = obj_armature.parent
        if not is_valid_object(obj):
            return None
        if len(obj.data.materials) == 0:
            return None
        return next((mat for mat in obj.data.materials if "head" in mat.name), None)

def getFirstSetupFaceReplaceFlagName():
    return "INITIALIZED_FACE_REPLACE"

def isFirstSetupFaceReplace(mat):
    return mat.node_tree.nodes.get(getFirstSetupFaceReplaceFlagName())

# make first setup face replace
def makeFirstSetupFaceReplace(mat):

    # pega o output node
    output_node = getOutPutNodeFromMat(mat)

    before_oupt_node = output_node.inputs["Surface"].links[0].from_node if output_node.inputs["Surface"].links else None
    if not before_oupt_node:
        return

    # initialized flag
    setup = mat.node_tree.nodes.new("ShaderNodeValue")
    setup.location[1] = output_node.location[1]
    setup.name = getFirstSetupFaceReplaceFlagName()

    # make mixer node face
    mixer_node_1 = mat.node_tree.nodes.new("ShaderNodeMixShader")
    mixer_node_1.location[1] = output_node.location[1]

    # make mixer node sub face
    mixer_node_2 = mat.node_tree.nodes.new("ShaderNodeMixShader")
    mixer_node_2.location[1] = output_node.location[1]

    # make menu switch face factor
    menu_factor_1 = mat.node_tree.nodes.new("GeometryNodeMenuSwitch")
    menu_factor_1.location[1] = output_node.location[1]
    menu_factor_1.name = "MenuFaceFactor"
    menu_factor_1.data_type = "FLOAT"
    menu_factor_1.enum_definition.enum_items.clear()
    menu_factor_1.enum_definition.enum_items.new("disable")
    menu_factor_1.inputs["disable"].default_value = 0.0
    menu_factor_1.inputs[0].default_value = "disable"

    # make menu switch sub face factor
    menu_factor_2 = mat.node_tree.nodes.new("GeometryNodeMenuSwitch")
    menu_factor_2.location[1] = output_node.location[1]
    menu_factor_2.name = "MenuSubFaceFactor"
    menu_factor_2.data_type = "FLOAT"
    menu_factor_2.enum_definition.enum_items.clear()
    menu_factor_2.enum_definition.enum_items.new("disable")
    menu_factor_2.inputs["disable"].default_value = 0.0
    menu_factor_2.inputs[0].default_value = "disable"

    # make menu switch face shader
    menu_shader_1 = mat.node_tree.nodes.new("GeometryNodeMenuSwitch")
    menu_shader_1.location[1] = output_node.location[1]
    menu_shader_1.name = "MenuFaceShader"
    menu_shader_1.data_type = "SHADER"
    menu_shader_1.enum_definition.enum_items.clear()
    menu_shader_1.enum_definition.enum_items.new("disable")
    menu_shader_1.inputs[0].default_value = "disable"

    # make menu switch sub face shader
    menu_shader_2 = mat.node_tree.nodes.new("GeometryNodeMenuSwitch")
    menu_shader_2.location[1] = output_node.location[1]
    menu_shader_2.name = "MenuSubFaceShader"
    menu_shader_2.data_type = "SHADER"
    menu_shader_2.enum_definition.enum_items.clear()
    menu_shader_2.enum_definition.enum_items.new("disable")
    menu_shader_2.inputs[0].default_value = "disable"

    mat.node_tree.links.new(mixer_node_1.inputs[0], menu_factor_1.outputs["Output"])
    mat.node_tree.links.new(mixer_node_1.inputs[1], before_oupt_node.outputs[0])
    mat.node_tree.links.new(mixer_node_1.inputs[2], menu_shader_1.outputs["Output"])

    mat.node_tree.links.new(mixer_node_2.inputs[0], menu_factor_2.outputs["Output"])
    mat.node_tree.links.new(mixer_node_2.inputs[1], mixer_node_1.outputs["Shader"])
    mat.node_tree.links.new(mixer_node_2.inputs[2], menu_shader_2.outputs["Output"])

    mat.node_tree.links.new(menu_shader_1.inputs["disable"], before_oupt_node.outputs[0])

    mat.node_tree.links.new(output_node.inputs["Surface"], mixer_node_2.outputs["Shader"])

    return menu_factor_1, menu_factor_2, menu_shader_1, menu_shader_2

def getMenusFromFaceReplace(mat):
    if not isFirstSetupFaceReplace(mat):
        return makeFirstSetupFaceReplace(mat)

    menu_factor_1 = mat.node_tree.nodes.get("MenuFaceFactor")
    menu_factor_2 = mat.node_tree.nodes.get("MenuSubFaceFactor")

    menu_shader_1 = mat.node_tree.nodes.get("MenuFaceShader")
    menu_shader_2 = mat.node_tree.nodes.get("MenuSubFaceShader")

    return menu_factor_1, menu_factor_2, menu_shader_1, menu_shader_2

# make image texture node
def makeImageTexNode(mat, name, img):

    # pega o output node
    output_node = getOutPutNodeFromMat(mat)

    if not output_node:
        return None, None

    # make rgb green color
    rgb_green = mat.node_tree.nodes.new("ShaderNodeRGB")
    rgb_green.location[1] = output_node.location[1]
    rgb_green.outputs[0].default_value = (0, 1, 0, 1)

    # make vector math(distance) node
    vector_math = mat.node_tree.nodes.new("ShaderNodeVectorMath")
    vector_math.location[1] = output_node.location[1]
    vector_math.operation = "DISTANCE"
    
    # make texture node
    texture_node = mat.node_tree.nodes.new("ShaderNodeTexImage")
    texture_node.location[1] = output_node.location[1]
    texture_node.name = name
    texture_node.image = img
    texture_node.projection = "FLAT"

    # make BsdfPrincipled
    bsdfPre_node = mat.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
    bsdfPre_node.location[1] = output_node.location[1]
    bsdfPre_node.inputs["IOR"].default_value = 1.0

    mat.node_tree.links.new(vector_math.inputs[0], rgb_green.outputs[0])
    mat.node_tree.links.new(vector_math.inputs[1], texture_node.outputs[0])
    mat.node_tree.links.new(bsdfPre_node.inputs["Base Color"], texture_node.outputs["Color"])

    return bsdfPre_node, vector_math

# insert image texture node in menu switch
def insertImageInMenuSwitch(mat, name, img):
    menu_factor_1, menu_factor_2, menu_shader_1, menu_shader_2 = getMenusFromFaceReplace(mat)

    menu_factor_1.enum_items.new(name)
    menu_factor_2.enum_items.new(name)

    menu_shader_1.enum_items.new(name)
    menu_shader_2.enum_items.new(name)

    bsdf, factor = makeImageTexNode(mat, name, img)

    mat.node_tree.links.new(menu_factor_1.inputs[name], factor.outputs["Value"])
    mat.node_tree.links.new(menu_factor_2.inputs[name], factor.outputs["Value"])

    mat.node_tree.links.new(menu_shader_1.inputs[name], bsdf.outputs["BSDF"])
    mat.node_tree.links.new(menu_shader_2.inputs[name], bsdf.outputs["BSDF"])

# make change face frame
def replaceFace(obj_armature, dirname, face_material_name, is_mpet, is_sub):

    # se não tiver o face mat não precisa gastar tempo nas outras coisas
    mat = findFaceMaterial(obj_armature, is_mpet)
    if not mat:
        return

    # check cache
    img = bpy.data.images.get(face_material_name)

    if not img:
        image_path = load_texture_path(dirname, face_material_name)
        if not pathlib.Path(image_path).exists():
            return
        
        img = loadImage(image_path)

    if bpy.app.version >= (5, 0, 0):
        menu_factor_1, menu_factor_2, menu_shader_1, menu_shader_2 = getMenusFromFaceReplace(mat)
    
        if not menu_factor_1.enum_items.get(face_material_name):
            insertImageInMenuSwitch(mat, face_material_name, img)

        if is_sub:
            menu_factor_2.inputs[0].default_value = face_material_name
            menu_shader_2.inputs[0].default_value = face_material_name
        else:
            menu_factor_2.inputs[0].default_value = "disable"

            menu_factor_1.inputs[0].default_value = face_material_name
            menu_shader_1.inputs[0].default_value = face_material_name

    else:

        mixer = mat.node_tree.nodes.get("Switch_Sub_Face")
        if mixer:
            texture_node = mat.node_tree.nodes.get("face_sub_replace" if is_sub else "face_replace")
            if texture_node:
                value = 1.0 if is_sub else 0.0
                if mixer.inputs[0].default_value != value:
                    mixer.inputs[0].default_value = value
                if texture_node.image != img:
                    texture_node.image = img
                return
    
        # verifica as coisas rápidas, depois as pesadas
        output_node = next((out for out in mat.node_tree.nodes if out.__class__.__name__ == "ShaderNodeOutputMaterial"), None)
        if not output_node and not output_node.inputs["Surface"].links:
            return
        before_oupt_node = output_node.inputs["Surface"].links[0].from_node
        if not before_oupt_node:
            return

        def makeSubMat(name, img):
            # make rgb green color
            rgb_green = mat.node_tree.nodes.new("ShaderNodeRGB")
            rgb_green.location[1] = output_node.location[1]
            rgb_green.outputs[0].default_value = (0, 1, 0, 1)

            # make vector math(distance) node
            vector_math = mat.node_tree.nodes.new("ShaderNodeVectorMath")
            vector_math.location[1] = output_node.location[1]
            vector_math.operation = "DISTANCE"
    
            # make texture node
            texture_node = mat.node_tree.nodes.new("ShaderNodeTexImage")
            texture_node.location[1] = output_node.location[1]
            texture_node.name = name
            texture_node.image = img
            texture_node.projection = "FLAT"

            # make BsdfPrincipled
            bsdfPre_node = mat.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
            bsdfPre_node.location[1] = output_node.location[1]
            bsdfPre_node.inputs["IOR"].default_value = 1.0

            # make mixer node
            mixer_node = mat.node_tree.nodes.new("ShaderNodeMixShader")
            mixer_node.location[1] = output_node.location[1]
    
            mat.node_tree.links.new(vector_math.inputs[0], rgb_green.outputs[0])
            mat.node_tree.links.new(vector_math.inputs[1], texture_node.outputs[0])
            mat.node_tree.links.new(mixer_node.inputs[0], vector_math.outputs["Value"])
            mat.node_tree.links.new(mixer_node.inputs[2], bsdfPre_node.outputs["BSDF"])
            mat.node_tree.links.new(bsdfPre_node.inputs["Base Color"], texture_node.outputs["Color"])

            return mixer_node

        mixer_face = makeSubMat("face_replace", img)
        mixer_sub_face = makeSubMat("face_sub_replace", img)

        # make mix node
        mixer_node = mat.node_tree.nodes.new("ShaderNodeMix")
        mixer_node.location[1] = output_node.location[1]
        mixer_node.data_type = "FLOAT"
        mixer_node.name = "Switch_Sub_Face"
        mixer_node.inputs[0].default_value = 0.0

        mat.node_tree.links.new(mixer_face.inputs[1], before_oupt_node.outputs[0])
        mat.node_tree.links.new(mixer_node.inputs[3], mixer_sub_face.inputs[0].links[0].from_node.outputs["Value"])
        mat.node_tree.links.new(mixer_sub_face.inputs[0], mixer_node.outputs[0])
        mat.node_tree.links.new(mixer_sub_face.inputs[1], mixer_face.outputs["Shader"])
        mat.node_tree.links.new(output_node.inputs["Surface"], mixer_sub_face.outputs["Shader"])