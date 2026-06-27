# Copyright 2023-2026 Acrisio Filho

# gbin.py - implementation of Ntreev PangYa .gbin, .sgbin, .aibin format.
# By Acrisio Filho

from os.path import splitext
from enum import IntEnum
from collections import defaultdict
import ctypes

from .util import getNewGUID
from .ioutil import (
    read_struct, write_struct,
    read_fixed_string, write_fixed_string,
    bytesFromCP949ToUnicode, unicodeTobytesCP949,
    AABB
)

class eFILE_TYPE(IntEnum):
    FT_GBIN= 1,
    FT_SGBIN= 2,
    FT_AIBIN= 3,

VERSION_70 = 0x70
VERSION_71 = 0x71
VERSION_72 = 0x72

gMagic = b'WEPX'
gVersion = VERSION_72
gFileType = eFILE_TYPE.FT_GBIN

def setFileType(filepath):
    global gFileType
    gFileType = eFILE_TYPE.FT_GBIN

    if filepath == '':
        return

    base, ext = splitext(filepath)

    if ext == '.gbin':
        gFileType = eFILE_TYPE.FT_GBIN
    elif ext == '.sgbin':
        gFileType = eFILE_TYPE.FT_SGBIN
    elif ext == '.aibin':
        gFileType = eFILE_TYPE.FT_AIBIN

class GBin:
    def __init__(self, version=VERSION_72, base_element=None, elements=None, cameras=None, lights=None, sound_boxs=None, textures=None, nodes=None, new_elements_v72=None, map_check=None):
        self.version = version
        self.base_element = base_element
        self.elements = elements
        self.cameras = cameras
        self.lights = lights
        self.sound_boxs = sound_boxs
        self.textures = textures
        self.nodes = nodes
        self.new_elements_v72 = new_elements_v72
        self.map_check = map_check
        self.is_gbin, self.is_sgbin, self.is_aibin = False, False, False

    def load(self, file):
        global gVersion

        # Reset version to 0x70
        self.version = gVersion = VERSION_70

        self.base_element = None
        self.elements = []
        self.cameras = []
        self.lights = []
        self.sound_boxs = []
        self.textures = []
        self.nodes = []
        self.new_elements_v72 = []
        self.map_check = None

        self.initFileType(file.name)

        magic, = read_struct(file, "<4s")

        if magic != gMagic:
            raise Exception("Formato de arquivo inválido")
        
        self.version, = read_struct(file, "<I")
        gVersion = self.version
        print("Version: 0x%X" % self.version)
        
        num_global_element, = read_struct(file, "<I")
        num_type_element = read_struct(file, "<2I")
        num_camera, = read_struct(file, "<I")
        num_light, = read_struct(file, "<I")
        num_sound_box, = read_struct(file, "<I")
        num_texture, = read_struct(file, "<I")
        num_node, = read_struct(file, "<I")
        num_new_element = 0

        if gVersion > VERSION_71:
            num_new_element, = read_struct(file, "<I")

        for i in range(num_camera):
            cam = Camera()
            cam.load(file)
            
            self.cameras.append(cam)
        
        for i in range(num_light):
            light = Light()
            light.load(file)

            self.lights.append(light)

        for i in range(num_sound_box):
            soundbox = SoundBox()
            soundbox.load(file)

            self.sound_boxs.append(soundbox)

        for i in range(num_texture):
            texture = Texture()
            texture.load(file)

            self.textures.append(texture)
        
        for i in range(num_node):
            node = Node()
            node.load(file)

            self.nodes.append(node)

        if (num_global_element + num_type_element[0] + num_type_element[1]) > 0:
            self.base_element = BaseElement()
            self.base_element.load(file)
        
        for i in range(num_global_element + num_type_element[0] + num_type_element[1]):
            element = Element()
            element.load(file)

            self.elements.append(element)
        
        for i in range(num_new_element):
            new_element = NewElementV72()
            new_element.load(file)

            self.new_elements_v72.append(new_element)

        if (num_global_element + num_type_element[0] + num_type_element[1]) > 0:
            self.map_check = MapCheck()
            self.map_check.load(file)

    def save(self, file):
        global gVersion

        if (
            not isinstance(self.elements, list) or
            not isinstance(self.cameras, list) or
            not isinstance(self.lights, list) or
            not isinstance(self.sound_boxs, list) or
            not isinstance(self.textures, list) or
            not isinstance(self.nodes, list) or
            not isinstance(self.new_elements_v72, list)
        ):
            raise Exception("Invalid paramters")

        # set global version
        gVersion = self.version

        self.initFileType(file.name)

        write_struct(file, "<4s", gMagic)
        write_struct(file, "<I", self.version)

        num_global_element = len([el for el in self.elements if el.course_type == 0])
        num_type_element = [
            len([el for el in self.elements if el.course_type == 1]),
            len([el for el in self.elements if el.course_type == 2])
        ]
        num_camera = len(self.cameras)
        num_light = len(self.lights)
        num_sound_box = len(self.sound_boxs)
        num_texture = len(self.textures)
        num_node = len(self.nodes)
        num_new_element = len(self.new_elements_v72)

        write_struct(file, "<I", num_global_element)
        write_struct(file, "<2I", *num_type_element)
        write_struct(file, "<I", num_camera)
        write_struct(file, "<I", num_light)
        write_struct(file, "<I", num_sound_box)
        write_struct(file, "<I", num_texture)
        write_struct(file, "<I", num_node)

        if gVersion > VERSION_71:
            write_struct(file, "<I", num_new_element)

        for i in range(num_camera):
            self.cameras[i].save(file)
        
        for i in range(num_light):
            self.lights[i].save(file)

        for i in range(num_sound_box):
            self.sound_boxs[i].save(file)

        for i in range(num_texture):
            self.textures[i].save(file)
        
        for i in range(num_node):
            self.nodes[i].save(file)

        if len(self.elements) > 0:
            self.base_element.save(file)

        for i in range(len(self.elements)):
            self.elements[i].save(file)

        if gVersion > VERSION_71:
            for i in range(num_new_element):
                self.new_elements_v72[i].save(file)

        if len(self.elements) > 0:
            self.map_check.save(file)

    def initFileType(self, filename):

        setFileType(filename)

        if gFileType == eFILE_TYPE.FT_GBIN:
            self.is_gbin = True
        elif gFileType == eFILE_TYPE.FT_SGBIN:
            self.is_sgbin = True
        elif gFileType == eFILE_TYPE.FT_AIBIN:
            self.is_aibin = True
    
    def __repr__(self):
        return "GBIN(Version=0x%X, BaseElement=%s, Elements=%s, Cameras=%s, Lights=%s, SoundBoxs=%s, Textures=%s, Nodes=%s, NewElementsV72=%s, MapCheck=%s)" % (
            self.version,
            repr(self.base_element),
            repr(self.elements),
            repr(self.cameras),
            repr(self.lights),
            repr(self.sound_boxs),
            repr(self.textures),
            repr(self.nodes),
            repr(self.new_elements_v72),
            repr(self.map_check),
        )

class ExtraValueV72:
    def __init__(self, guid=None, parent_guid=-1):
        self.guid = guid
        self.parent_guid = parent_guid
    
    def load(self, file):
        self.guid, self.parent_guid = read_struct(file, "<2i")
    
    def save(self, file):
        write_struct(file, "<2i", self.guid, self.parent_guid)
    
    def __repr__(self):
        return "ExtraValueV72(guid=%d, parent_guid=%d)" % (self.guid, self.parent_guid)

class Camera:
    def __init__(self, name=None, vpos_world=None, vdest_world=None, fov=None, bank=None, vpos_local=None, vdest_local=None, extra_value=None):
        self.name = name
        self.vpos_world = vpos_world
        self.vdest_world = vdest_world
        self.fov = fov
        self.bank = bank
        self.vpos_local = vpos_local if vpos_local else (vpos_world[:] if vpos_world else vpos_world)
        self.vdest_local = vdest_local if vdest_local else (vdest_world[:] if vdest_world else vdest_world)
        self.extra_value = extra_value if extra_value else ExtraValueV72(getNewGUID(), -1)

    def load(self, file):
        self.name = bytesFromCP949ToUnicode(read_struct(file, "<32s")[0].split(b"\x00")[0])
        self.vpos_world = read_struct(file, "<3f")
        self.vdest_world = read_struct(file, "<3f")
        self.fov, = read_struct(file, "<f")
        self.bank, = read_struct(file, "<f")

        # set o local aqui, para quando não tem o parent ou a versão for menor que 0x72
        self.vpos_local = self.vpos_world[:]
        self.vdest_local = self.vdest_world[:]

        if gVersion > VERSION_71:
            self.vpos_local = read_struct(file, "<3f")
            self.vdest_local = read_struct(file, "<3f")
            self.extra_value = ExtraValueV72()
            self.extra_value.load(file)

    def save(self, file):
        write_struct(file, "<32s", unicodeTobytesCP949(self.name))
        write_struct(file, "<3f", *self.vpos_world)
        write_struct(file, "<3f", *self.vdest_world)
        write_struct(file, "<f", self.fov)
        write_struct(file, "<f", self.bank)

        if gVersion > VERSION_71:
            write_struct(file, "<3f", *self.vpos_local)
            write_struct(file, "<3f", *self.vdest_local)
            self.extra_value.save(file)
    
    def __repr__(self):
        values = [self.name, *self.vpos_world, *self.vdest_world, self.fov, self.bank]
        fmt = "Camera(name=%s, vpos_world=[%f, %f, %f], vdest_world=[%f, %f, %f], fov=%f, bank=%f"
        if gVersion > VERSION_71:
            values.extend([
                *self.vpos_local,
                *self.vdest_local,
                repr(self.extra_value)
            ])
            fmt = fmt + ", vpos_local=[%f, %f, %f], vdest_local=[%f, %f, %f], extra_value=%s"
        fmt = fmt + ")"

        return fmt % tuple(values)

class Light:
    def __init__(self, type=None, name=None, vpos_world=None, data=None, vpos_local=None, extra_value=None):
        self.type = type
        self.name = name
        self.vpos_world = vpos_world
        self.data = data
        self.vpos_local = vpos_local if vpos_local else (vpos_world[:] if vpos_world else vpos_world)
        self.extra_value = extra_value if extra_value else ExtraValueV72(getNewGUID(), -1)

    def load(self, file):
        self.type, = read_struct(file, "<B")
        self.name = bytesFromCP949ToUnicode(read_struct(file, "<32s")[0].split(b"\x00")[0])
        self.vpos_world = read_struct(file, "<3f")
        
        # set o local aqui, para quando não tem o parent ou a versão for menor que 0x72
        self.vpos_local = self.vpos_world[:]

        if self.type != 0:
            self.data = bytesFromCP949ToUnicode(read_struct(file, "<64s")[0].split(b"\x00")[0])

        if gVersion > VERSION_71:
            self.vpos_local = read_struct(file, "<3f")
            self.extra_value = ExtraValueV72()
            self.extra_value.load(file)

    def save(self, file):
        write_struct(file, "<B", self.type & 0xFF)
        write_struct(file, "<32s", unicodeTobytesCP949(self.name))
        write_struct(file, "<3f", *self.vpos_world)
        
        if self.type != 0:
            write_struct(file, "<64s", unicodeTobytesCP949(self.data))

        if gVersion > VERSION_71:
            write_struct(file, "<3f", *self.vpos_local)
            self.extra_value.save(file)
    
    def __repr__(self):
        values = [self.type, self.name, *self.vpos_world, self.data]
        fmt = "Light(type=%d, name=%s, vpos_world=[%f, %f, %f], data=%s"
        if gVersion > VERSION_71:
            values.extend([
                *self.vpos_local,
                repr(self.extra_value)
            ])
            fmt = fmt + ", vpos_local=[%f, %f, %f], extra_value=%s"
        fmt = fmt + ")"

        return fmt % tuple(values)

class SoundBox:
    def __init__(self, type=None, name=None, min_max_world=None, min_max_local=None, extra_value=None):
        self.type = type
        self.name = name
        self.min_max_world = min_max_world
        self.min_max_local = min_max_local if min_max_local else (min_max_world.copy() if min_max_world else min_max_world)
        self.extra_value = extra_value if extra_value else ExtraValueV72(getNewGUID(), -1)

    def load(self, file):
        self.type, = read_struct(file, "<B")
        self.name = bytesFromCP949ToUnicode(read_struct(file, "<64s")[0].split(b"\x00")[0])
        self.min_max_world = AABB()
        self.min_max_world.load(file)

        # set o local aqui, para quando não tem o parent ou a versão for menor que 0x72
        self.min_max_local = self.min_max_world.copy()

        if gVersion > VERSION_71:
            self.min_max_local = AABB()
            self.min_max_local.load(file)
            self.extra_value = ExtraValueV72()
            self.extra_value.load(file)
    
    def save(self, file):
        write_struct(file, "<B", self.type & 0xFF)
        write_struct(file, "<64s", unicodeTobytesCP949(self.name))
        self.min_max_world.save(file)
        
        if gVersion > VERSION_71:
            self.min_max_local.save(file)
            self.extra_value.save(file)
    
    def __repr__(self):
        values = [self.type, self.name, repr(self.min_max_world)]
        fmt = "SoundBox(type=%d, name=%s, min_max_world=%s"
        if gVersion > VERSION_71:
            values.extend([
                repr(self.min_max_local),
                repr(self.extra_value)
            ])
            fmt = fmt + ", min_max_local=%s, extra_value=%s"
        fmt = fmt + ")"

        return fmt % tuple(values)

class Texture:
    def __init__(self, name=None):
        self.name = name

    def load(self, file):
        self.name = bytesFromCP949ToUnicode(read_struct(file, "<32s")[0].split(b"\x00")[0])

    def save(self, file):
        write_struct(file, "<32s", unicodeTobytesCP949(self.name))

    def __repr__(self):
        return "Texture(name=%s)" % self.name

class Node:
    def __init__(self, name=None, type=None, vects=None):
        self.name = name
        self.type = type
        self.vects = vects
    
    def load(self, file):
        self.vects = []

        if gFileType == eFILE_TYPE.FT_AIBIN:
            self.name = bytesFromCP949ToUnicode(read_struct(file, "<32s")[0].split(b"\x00")[0])
        else:
            self.name = bytesFromCP949ToUnicode(read_struct(file, "<16s")[0].split(b"\x00")[0])
        
        num_vect, = read_struct(file, "<I")
        self.type, = read_struct(file, "<I")

        for i in range(num_vect):
            self.vects.append(read_struct(file, "<3f"))

    def save(self, file):
        
        if not isinstance(self.vects, list) or not isinstance(self.type, int):
            raise Exception("Invalid paramters")

        if gFileType == eFILE_TYPE.FT_AIBIN:
            write_struct(file, "<32s", unicodeTobytesCP949(self.name))
        else:
            write_struct(file, "<16s", unicodeTobytesCP949(self.name))
        
        num_vect = len(self.vects)

        write_struct(file, "<I", num_vect)
        write_struct(file, "<I", self.type)

        for i in range(num_vect):
            write_struct(file, "<3f", *self.vects[i])
    
    def __repr__(self):
        return "Node(name=%s, type=%d, vects[]=%s)" % (self.name, self.type, repr(self.vects))

class ElementOptionAnimateFlag(ctypes.LittleEndianStructure):
    _fields_ = [
        ("anim1", ctypes.c_uint8, 1),       # animate NPC default
        ("anim2", ctypes.c_uint8, 1),       # rotate(rotação) no próprio eixo
        ("anim3", ctypes.c_uint8, 1),       # self animate
        ("reserved", ctypes.c_uint8, 5)
    ]

    # combinações:
    # anim1 + anim2 = self animate
    # anim1 + anim3 = freeze
    # ainm2 + anim3 = freeze

    def is_animate(self):
        return not self.is_freeze()
    
    def is_freeze(self):
        return ((self.anim3 == 1 and (self.anim1 == 1 or self.anim2 == 1)) or
                (self.anim1 == 0 and self.anim2 == 0 and self.anim3 == 0)
        )
    
    def is_rotate(self):
        return self.anim2 == 1 and self.anim1 == 0 and self.anim3 == 0
    
    def is_shadow(self):
        return self.anim3 == 1 or (self.anim1 == 0 and self.anim2 == 0)

    def to_value(self):
        return ctypes.c_uint8.from_buffer(self).value & 7

    @classmethod
    def from_value(cls, val):
        return cls.from_buffer_copy(ctypes.c_uint8(val))

    def update_value(self, val):
        ctypes.memmove(ctypes.addressof(self), ctypes.addressof(ctypes.c_uint8(val)), ctypes.sizeof(self))

    def __repr__(self):
        return f"ElementOptionAnimationFlag(anim1={self.anim1}, anim2={self.anim2}, anim3={self.anim3})"

class ElementOptionCollisionFlag(ctypes.LittleEndianStructure):
    _fields_ = [
        ("reserved", ctypes.c_uint8, 3),
        ("coll1", ctypes.c_uint8, 1),       # solid(sólido) visual
        ("coll2", ctypes.c_uint8, 1),       # collision secundária
        ("coll3", ctypes.c_uint8, 1),       # tem no mland(gz) no ground dele
        ("coll4", ctypes.c_uint8, 1),       # tem no mland(gz) no ground dele
        ("coll5", ctypes.c_uint8, 1),
    ]

    def to_value(self):
        val = ctypes.c_uint8.from_buffer(self).value
        return (val >> 3) & 0x1F
    
    @classmethod
    def from_value(cls, val):
        return cls.from_buffer_copy(ctypes.c_uint8(val))

    def update_value(self, val):
        ctypes.memmove(ctypes.addressof(self), ctypes.addressof(ctypes.c_uint8(val)), ctypes.sizeof(self))

    def __repr__(self):
        return f"ElementOptionCollisionFlag(coll1={self.coll1}, coll2={self.coll2}, coll3={self.coll3}, coll4={self.coll4}, coll5={self.coll5})"

class ElementOptionFlag:
    def __init__(self, anim_flag=None, coll_flag=None):
        self.anim_flag=anim_flag
        self.coll_flag=coll_flag

    def load(self, file):
        self.anim_flag = ElementOptionAnimateFlag.from_value(0)
        self.coll_flag = ElementOptionCollisionFlag.from_value(0)

        (opt1, _) = read_struct(file, "<2B") # segundo byte é lixo de memória (reserved)

        self.anim_flag.update_value(opt1)
        self.coll_flag.update_value(opt1)

    def save(self, file):
        if (
            type(self.anim_flag).__name__ != "ElementOptionAnimateFlag" or
            type(self.coll_flag).__name__ != "ElementOptionCollisionFlag"
        ):
            raise Exception("Invalid parameters")

        opt1 = (self.coll_flag.to_value() << 3) | self.anim_flag.to_value()

        write_struct(file, "<2B", opt1, 0) # segundo byte é lixo de memória (reserved)
    
    def __repr__(self):
        return f"ElementOptionFlag({repr(self.anim_flag)}, {repr(self.coll_flag)})"

class Element:
    def __init__(self, option=None, face_num=None, name=None, min_max=None, fit_base_model=None, matrix_world=None, course_type=None, script="", matrix_local=None, extra_value=None):
        self.option = option # flags to animate object and collision object(solid)
        self.face_num = face_num
        self.name = name
        self.min_max = min_max
        self.fit_base_model = fit_base_model
        self.matrix_world = matrix_world
        self.course_type = course_type # type[0], type[1] (1 - Blue Lagoon, 2 - Blue Water)
        self.script = script # used in portals, values to warp ball trajectory
        self.matrix_local = matrix_local if matrix_local else (matrix_world[:] if matrix_world else matrix_world)
        self.extra_value = extra_value if extra_value else ExtraValueV72(getNewGUID(), -1)
    
    def load(self, file):
        self.option = ElementOptionFlag() # 2 bytes "<H"
        self.option.load(file)
        file.read(2) # align 4
        self.face_num, = read_struct(file, "<I")
        self.name = bytesFromCP949ToUnicode(read_struct(file, "<32s")[0].split(b"\x00")[0])
        self.min_max = AABB()
        self.fit_base_model = AABB()
        self.min_max.load(file)
        self.fit_base_model.load(file)
        self.matrix_world = read_struct(file, "<12f")
        self.course_type, = read_struct(file, "<i")

        # set o local aqui, para quando não tem o parent ou a versão for menor que 0x72
        self.matrix_local = self.matrix_world[:]

        if gVersion > VERSION_70:
            self.script = bytesFromCP949ToUnicode(read_struct(file, "<32s")[0].split(b"\x00")[0])

        if gVersion > VERSION_71:
            self.matrix_local = read_struct(file, "<12f")
            self.extra_value = ExtraValueV72()
            self.extra_value.load(file)
    
    def save(self, file):
        if type(self.option).__name__ != "ElementOptionFlag":
            raise Exception("Invalid parameters")

        self.option.save(file) # 2 bytes "<H"
        file.write(b'\x00\x00') # align 4
        write_struct(file, "<I", self.face_num)
        write_struct(file, "<32s", unicodeTobytesCP949(self.name))
        self.min_max.save(file)
        self.fit_base_model.save(file)
        write_struct(file, "<12f", *self.matrix_world)
        write_struct(file, "<i", self.course_type)

        if gVersion > VERSION_70:
            write_struct(file, "<32s", unicodeTobytesCP949(self.script))

        if gVersion > VERSION_71:
            write_struct(file, "<12f", *self.matrix_local)
            self.extra_value.save(file)

    def __repr__(self):
        values = [self.name, repr(self.option), self.face_num, repr(self.min_max), repr(self.fit_base_model), *self.matrix_world, self.course_type]
        fmt = "Element(name=%s, option=%s, face_num=%d, min_max=%s, fit_base_model=%s, matrix_world=[%f" + (", %f" * 11) + "], course_type=%d"
        if gVersion > VERSION_70:
            values.append(self.script)
            fmt = fmt + ", script=%s"
        if gVersion > VERSION_71:
            values.extend([
                *self.matrix_local,
                repr(self.extra_value)
            ])
            fmt = fmt + ", matrix_local=[%f" + (", %f" * 11) + "], extra_value=%s"
        fmt = fmt + ")"

        return fmt % tuple(values)

class BaseElement:
    def __init__(self, element=None, map_color_vtx_v70=None, map_color_vtx_v72=None):
        self.element = element
        self.map_color_vtx_v70 = map_color_vtx_v70
        self.map_color_vtx_v72 = map_color_vtx_v72 if map_color_vtx_v72 else defaultdict(list)

    def load(self, file):
        self.element = Element()
        self.element.load(file)

        self.map_color_vtx_v70 = []

        if gVersion < VERSION_72:
            for i in range(self.element.face_num):
                self.map_color_vtx_v70.append(read_struct(file, "<3I"))
        else:
            num_bone_name_puppet_map, = read_struct(file, "<I")

            for i in range(num_bone_name_puppet_map):
                bone_name_puppet = bytesFromCP949ToUnicode(read_fixed_string(file))
                face_num, = read_struct(file, "<I")
                faces = []

                for j in range(face_num):
                    vtxNum, = read_struct(file, "<I")
                    faces.append(read_struct(file, "<{}I".format(vtxNum)))
                
                self.map_color_vtx_v72[bone_name_puppet] = faces
    
    def save(self, file):
        self.element.save(file)

        if gVersion < VERSION_72:
            if isinstance(self.map_color_vtx_v70, list) and self.element.face_num != len(self.map_color_vtx_v70):
                raise Exception("map_color_vtx_v70 o tamanho da lista é diferente do face_num do element. %d != %d" % (
                    self.element.face_num, len(self.map_color_vtx_v70)
                ))

            for i in range(self.element.face_num):
                write_struct(file, "<3I", *self.map_color_vtx_v70[i])
        else:
            num_bone_name_puppet_map = len(self.map_color_vtx_v72)

            write_struct(file, "<I", num_bone_name_puppet_map)

            for bone_name_puppet, faces in self.map_color_vtx_v72.items():
                write_fixed_string(file, unicodeTobytesCP949(bone_name_puppet))
                write_struct(file, "<I", len(faces))

                for face in faces:
                    vtxNum = len(face)
                    write_struct(file, "<I", vtxNum)
                    write_struct(file, "<{}I".format(vtxNum), *face)

    def __repr__(self):
        values = [repr(self.element)]
        if gVersion < VERSION_72:
            values.append(repr(self.map_color_vtx_v70))
        else:
            values.append(repr(self.map_color_vtx_v72))

        return "BaseElement(Element=%s, MapColorVtx=%s)" % tuple(values)

# Esse aqui é do Grand Zodiac, tem o Green tipo 1, e Tee Shot tipo 2
class NewElementV72:
    def __init__(self, extra_value=None, name=None, type=None, matrix_world=None, matrix_local=None):
        self.extra_value = extra_value if extra_value else ExtraValueV72(getNewGUID(), -1)
        self.name = name
        self.type = type
        self.matrix_world = matrix_world
        self.matrix_local = matrix_local if matrix_local else (matrix_world[:] if matrix_world else matrix_world)
    
    def load(self, file):
        self.extra_value = ExtraValueV72()
        self.extra_value.load(file)
        self.name = bytesFromCP949ToUnicode(read_struct(file, "<64s")[0].split(b"\x00")[0])
        self.matrix_world = read_struct(file, "<12f")
        self.matrix_local = read_struct(file, "<12f")
        self.type, = read_struct(file, "<I")

    def save(self, file):
        self.extra_value.save(file)
        write_struct(file, "<64s", unicodeTobytesCP949(self.name))
        write_struct(file, "<12f", *self.matrix_world)
        write_struct(file, "<12f", *self.matrix_local)
        write_struct(file, "<I", self.type)

    def __repr__(self):
        return ("NewElementV72(name=%s, type=%d, extra_value=%s, matrix_world=[%f" + (", %f" * 11) + "], matrix_local=[%f" + (", %f" * 11) + "])") % (
            self.name,
            self.type,
            repr(self.extra_value),
            *self.matrix_world,
            *self.matrix_local
        )

class MapCheck:
    def __init__(self, par_hole=None, tee_type=None, pin_type=None):
        self.par_hole = par_hole
        self.tee_type = tee_type    # array com 2 ponto(X,Z) em float
        self.pin_type = pin_type    # array com 2 array com 3 ponto(X,Z) em float
    
    def load(self, file):
        self.par_hole, = read_struct(file, "<B")
        
        self.tee_type = []
        self.pin_type = []

        if gVersion < VERSION_72:
            for i in range(2):
                self.tee_type.append(read_struct(file, "<2f"))
            for i in range(2):
                pins = []
                for j in range(3):
                    pins.append(read_struct(file, "<2f"))
                self.pin_type.append(pins)

    def save(self, file):
        if (
            not isinstance(self.tee_type, list) or
            not isinstance(self.pin_type, list) or
            not isinstance(self.par_hole, int)
        ):
            raise Exception("Invalid paramters")

        write_struct(file, "<B", self.par_hole & 0xFF)

        if gVersion < VERSION_72:
            for i in range(min(len(self.tee_type), 2)):
                write_struct(file, "<2f", *self.tee_type[i])
            for i in range(min(len(self.pin_type), 2)):
                for j in range(min(len(self.pin_type[i]), 3)):
                    write_struct(file, "<2f", *self.pin_type[i][j])
    
    def __repr__(self):
        values = [self.par_hole]
        fmt = "MapCheck(par_hole=%d"
        if gVersion < VERSION_72:
            values.extend([
                repr(self.tee_type),
                repr(self.pin_type)
            ])
            fmt = fmt + ", tee_type[]=%s, pin_type[]=%s"
        fmt = fmt + ")"

        return fmt % tuple(values)