# Copyright 2023-2026 Acrisio Filho

# sbin.py - implementation of Ntreev PangYa .sbin format.
# By Acrisio Filho

from math import floor

from .ioutil import (
    read_struct,
    read_fixed_string,
    write_struct,
    write_fixed_string,
    bytesFromCP949ToUnicode, unicodeTobytesCP949
)

class Version:
    def __init__(self, major=None, minor=None):
        self.major=major
        self.minor=minor
        self.rest=0xFFFE

    def fullVersion(self):
        return (self.rest << 16) | (self.major << 8) | self.minor

    def load(self, file):
        self.minor, = read_struct(file, '<B')
        self.major, = read_struct(file, '<B')
        self.rest, = read_struct(file, '<H')
        if self.rest != 0xFFFE:
            print("Version.rest invalid(%d)" % self.rest)

    def save(self, file):
        write_struct(file, '<B', self.minor & 0xFF)
        write_struct(file, '<B', self.major & 0xFF)
        write_struct(file, '<H', self.rest)

    def __repr__(self):
        return "Version(%d.%d)" % (self.major, self.minor)

VERSION_0_0 = Version(0, 0)
VERSION_1_0 = Version(1, 0)

gVersion = VERSION_1_0

def compareVersions(v1, v2):
    if v1.fullVersion() == v2.fullVersion():
        return 0
    
    if v1.major == v2.major:
        return -1 if v1.minor < v2.minor else 1

    return -1 if v1.major < v2.major else 1

class SBinCtx:
    def __init__(self, version=VERSION_1_0, bones=None):
        self.version=version
        self.bones=bones

    def load(self, file, bone_name="Beta version"):
        global gVersion

        # Reset Version to 1.0
        self.version = gVersion = VERSION_1_0

        self.bones=[]

        self.version.load(file)

        if (self.version.fullVersion() & 0xFFFE0000) == 0xFFFE0000 and compareVersions(self.version, VERSION_1_0) >= 0:
            gVersion = self.version
            print("SBIN %s" % repr(self.version))

            numBones, = read_struct(file, '<I')

            for i in range(numBones):
                bone = SBinBone()
                bone.load(file)

                self.bones.append(bone)
        else:
            # Beta version
            self.version = gVersion = VERSION_0_0
            print("SBIN Version beta")

            # reset file index
            file.seek(0)

            bone = SBinBone()
            bone.load(file, bone_name)

            self.bones.append(bone)

    def save(self, file):
        global gVersion

        if not isinstance(self.bones, list) or len(self.bones) == 0:
            raise Exception("Invalid bones length require minimal of 1 and have 0")

        gVersion = self.version

        if compareVersions(self.version, VERSION_1_0) >= 0:
            self.version.save(file)

            write_struct(file, '<I', len(self.bones))

            for bone in self.bones:
                bone.save(file)
        else:
            self.bones[0].save(file)
    
    def __repr__(self):
        return "SBinCtx(version=%s, bones=[%s])" % (
            repr(self.version),
            repr(self.bones)
        )

class SBin:
    def __init__(self, in_frag_mesh=None, out_frag_mesh=None):
        self.in_frag_mesh=in_frag_mesh
        self.out_frag_mesh=out_frag_mesh

    def load(self, file):
        self.in_frag_mesh = InFragMesh()
        self.in_frag_mesh.load(file)

        self.out_frag_mesh = OutFragMesh()
        self.out_frag_mesh.load(file, len(self.in_frag_mesh.info_meshes))

    def save(self, file):
        self.in_frag_mesh.save(file)
        self.out_frag_mesh.save(file)

    def __repr__(self):
        return "SBin(in_frag_mesh=%s, out_frag_mesh=%s)" % (
            repr(self.in_frag_mesh),
            repr(self.out_frag_mesh)
        )

class SBinBone:
    def __init__(self, name=None, sbin=None):
        self.name=name
        self.sbin=sbin

    def load(self, file, default_name=None):
        if compareVersions(gVersion, VERSION_1_0) >= 0:
            self.name = bytesFromCP949ToUnicode(read_fixed_string(file))
        elif default_name:
            self.name = default_name
        else:
            self.name = "Beta version"

        self.sbin = SBin()
        self.sbin.load(file)
    
    def save(self, file):
        if compareVersions(gVersion, VERSION_1_0) >= 0:
            write_fixed_string(file, unicodeTobytesCP949(self.name))
        
        self.sbin.save(file)

    def __repr__(self):
        return "SBinBone(name=%s, sbin=%s)" % (self.name, repr(self.sbin))

class Vector2d:
    def __init__(self, x=None, y=None):
        self.x=x
        self.y=y

    def load(self, file):
        self.x, self.y = read_struct(file, '<2f')

    def save(self, file):
        write_struct(file, '<2f', self.x, self.y)

    def __repr__(self):
        return "Vector2d(x=%f, y=%f)" % (self.x, self.y)

class Vector3d:
    def __init__(self, x=None, y=None, z=None):
        self.x=x
        self.y=y
        self.z=z

    def load(self, file):
        self.x, self.y, self.z = read_struct(file, '<3f')

    def save(self, file):
        write_struct(file, '<3f', self.x, self.y, self.z)

    def __repr__(self):
        return "Vector3d(x=%f, y=%f, z=%f)" % (self.x, self.y, self.z)

class MeshInfo:
    def __init__(self, vtxNum=None, idxNum=None):
        self.vtxNum=vtxNum
        self.idxNum=idxNum
    
    def load(self, file):
        self.vtxNum, = read_struct(file, '<I')
        self.idxNum, = read_struct(file, '<I')

    def save(self, file):
        write_struct(file, '<I', self.vtxNum)
        write_struct(file, '<I', self.idxNum)

    def __repr__(self):
        return "MeshInfo(vtxNum=%d, idxNum=%d)" % (self.vtxNum, self.idxNum)

class IndexVertex:
    def __init__(self, flag=None, index=None):
        self.flag=flag
        self.index=index
    
    def load(self, file):
        u16, = read_struct(file, "<H")

        self.flag = (u16 >> 15) & 1
        self.index = u16 & 0x7FFF
    
    def save(self, file):
        u16 = self.index | ((self.flag >= 1) << 15)

        write_struct(file, "<H", u16)
    
    def __repr__(self):
        return "IndexVertex(flag=%d, index=%d)" % (self.flag, self.index)

class MapDDSValue:
    def __init__(self, mesh_index=None, poly_index=None, indexes_vertex=None, indexes_uv=None, align_memory=0):
        self.mesh_index = mesh_index
        self.align_memory = align_memory
        self.poly_index = poly_index
        self.indexes_vertex = indexes_vertex # array with IndexVertex[3](uint16_t)
        self.indexes_uv = indexes_uv # array with uint16_t indexes_uv[3]

    def load(self, file):
        self.mesh_index, = read_struct(file, '<B')
        self.align_memory, = read_struct(file, '<B') # align memory struct
        self.poly_index, = read_struct(file, '<h')
        self.indexes_vertex = []
        self.indexes_uv = ()

        for i in range(3):
            index_vertex = IndexVertex()
            index_vertex.load(file)

            self.indexes_vertex.append(index_vertex)

        self.indexes_uv = read_struct(file, '<3H')

    def save(self, file):
        if not isinstance(self.indexes_vertex, list) or len(self.indexes_vertex) != 3:
            raise Exception("(indexes_vertex) Invalid array length require 3 and have %d" % len(self.indexes_vertex))
        if not isinstance(self.indexes_uv, (list, tuple)) or len(self.indexes_uv) != 3:
            raise Exception("(indexes_uv) Invalid array length require 3 and have %d" % len(self.indexes_uv))

        write_struct(file, '<B', self.mesh_index & 0xFF)
        write_struct(file, '<B', self.align_memory & 0xFF) # align memory struct
        write_struct(file, '<h', self.poly_index)

        for index_vertex in self.indexes_vertex:
            index_vertex.save(file)

        write_struct(file, '<3H', *self.indexes_uv)

    def getSize(self):
        # 16 = 1 mesh_index, 1 align_memory, 2 poly_index, 6(2 * 3) index_vertex, 6(2 * 3) index_uv
        return 16

    def __repr__(self):
        return "MapDDSValue(mesh_index=%d, align_memory=%02X, poly_index=%d, indexes_vertex[3]=[%s, %s, %s], indexes_uv[3]=[%d, %d, %d])" % (
            self.mesh_index,
            self.align_memory,
            self.poly_index,
            *self.indexes_vertex,
            *self.indexes_uv
        )

class TextureDDS:
    def __init__(self, width=None, height=None, dataDDS=None, mapDDSValues=None):
        self.width=width
        self.height=height
        self.dataDDS=dataDDS
        self.mapDDSValues=mapDDSValues

    def load(self, file):
        self.mapDDSValues = []
        self.dataDDS = ()

        self.width, = read_struct(file, '<I')
        self.height, = read_struct(file, '<I')
        self.dataDDS = read_struct(file, "<{}B".format((self.width * self.height) // 2))

        numMapDDS, = read_struct(file, '<I')

        for i in range(numMapDDS):
            mapDDSValue = MapDDSValue()
            mapDDSValue.load(file)

            self.mapDDSValues.append(mapDDSValue)

    def save(self, file):
        if not isinstance(self.dataDDS, (list, tuple)) or not isinstance(self.mapDDSValues, list):
            raise Exception("Invalid parameters")

        if len(self.dataDDS) != ((self.width * self.height) // 2):
            raise Exception("Invalid dataDDS lenght to (width * height) // 2, %d != %d" % len(self.dataDDS), (self.width * self.height) // 2)

        write_struct(file, '<I', self.width)
        write_struct(file, '<I', self.height)
        write_struct(file, "<{}B".format(len(self.dataDDS)), *self.dataDDS)
        write_struct(file, '<I', len(self.mapDDSValues))

        for mapDDSValue in self.mapDDSValues:
            mapDDSValue.save(file)

    def getSize(self):
        # 12 = 4 width, 4 height, 4 length mapDDSValue
        size = 12 + len(self.dataDDS)
        for mp in self.mapDDSValues:
            size += mp.getSize()
        return size
    
    def __repr__(self):
        return "TextureDDS(width=%d, height=%d, dataDDS=[%s], mapDDSValues=[%s])" % (
            self.width,
            self.height,
            repr(self.dataDDS),
            repr(self.mapDDSValues)
        )

class InFragMesh:
    def __init__(self, info_meshes=None, vertexes=None, uvs=None, size_texture_global=None, size_texture_type=None, texture_globals=None, texture_types=None):
        self.info_meshes=info_meshes
        self.vertexes=vertexes
        self.uvs=uvs
        self.size_texture_global=size_texture_global
        self.size_texture_type=size_texture_type # Array uint32_t Type[2]
        self.texture_globals=texture_globals
        self.texture_types=texture_types # Array TextureDDS Types[2][]

    def load(self, file):
        self.info_meshes=[]
        self.vertexes=[]
        self.uvs=[]
        self.size_texture_type=[0] * 2
        self.texture_globals=[]
        self.texture_types=[[] for i in range(2)]

        numInfoMeshes, = read_struct(file, '<I')

        for i in range(numInfoMeshes):
            info_mesh = MeshInfo()
            info_mesh.load(file)

            self.info_meshes.append(info_mesh)

        numVertex, = read_struct(file, '<I')
        numUV, = read_struct(file, '<I')

        for i in range(numVertex):
            vec3 = Vector3d()
            vec3.load(file)

            self.vertexes.append(vec3)

        for i in range(numUV):
            vec2 = Vector2d()
            vec2.load(file)

            self.uvs.append(vec2)

        self.size_texture_global, = read_struct(file, '<I')

        if self.size_texture_global > 0:
            numTexture, = read_struct(file, '<I')

            for i in range(numTexture):
                texture = TextureDDS()
                texture.load(file)

                self.texture_globals.append(texture)

        for i in range(2):
            self.size_texture_type[i], = read_struct(file, '<I')

            if self.size_texture_type[i] > 0:
                numTexture, = read_struct(file, '<I')

                for j in range(numTexture):
                    texture = TextureDDS()
                    texture.load(file)

                    self.texture_types[i].append(texture)

    def save(self, file):
        if (
            not isinstance(self.info_meshes, list) or
            not isinstance(self.vertexes, list) or
            not isinstance(self.uvs, list) or
            not isinstance(self.size_texture_type, list) or
            not isinstance(self.texture_globals, list) or
            not isinstance(self.texture_types, list)
        ):
            raise Exception("Invalid parameters")

        if len(self.size_texture_type) != 2:
            raise Exception("Invalid Array length of size_texture_type require 2 and have %d" % len(self.size_texture_type))
        if len(self.texture_types) != 2:
            raise Exception("Invalid Array length of texture_types require 2 and have %d" % len(self.texture_types))

        write_struct(file, '<I', len(self.info_meshes))

        for info_mesh in self.info_meshes:
            info_mesh.save(file)

        write_struct(file, '<I', len(self.vertexes))
        write_struct(file, '<I', len(self.uvs))

        for vec3 in self.vertexes:
            vec3.save(file)

        for vec2 in self.uvs:
            vec2.save(file)

        # calcule size
        if self.size_texture_global == -1:
            self.size_texture_global = 4 # 4 por que é o length das texturas
            for tex in self.texture_globals:
                self.size_texture_global += tex.getSize()

        write_struct(file, '<I', self.size_texture_global)

        if self.size_texture_global > 0:
            write_struct(file, '<I', len(self.texture_globals))

            for texture in self.texture_globals:
                texture.save(file)

        for i in range(2):
            # calcule size
            if self.size_texture_type[i] == -1:
                self.size_texture_type[i] = 4 # 4 por que é o length das texturas
                for tex in self.texture_types[i]:
                    self.size_texture_type[i] += tex.getSize()

            write_struct(file, '<I', self.size_texture_type[i])

            if self.size_texture_type[i] > 0:
                write_struct(file, '<I', len(self.texture_types[i]))

                for texture in self.texture_types[i]:
                    texture.save(file)

    def __repr__(self):
        return "InFragMesh(info_meshes=[%s], vertexes=[%s], uvs=[%s], size_texture_global=%d, size_texture_type=[%s], texture_globals=[%s], texture_types=[%s])" % (
            repr(self.info_meshes),
            repr(self.vertexes),
            repr(self.uvs),
            self.size_texture_global,
            repr(self.size_texture_type),
            repr(self.texture_globals),
            repr(self.texture_types)
        )

class OutFragMeshValue:
    def __init__(self, poly_index=None, indexes_vertex=None):
        self.poly_index =poly_index
        self.indexes_vertex = indexes_vertex

    def load(self, file):
        self.poly_index, = read_struct(file, '<h')
        self.indexes_vertex = []

        for i in range(3):
            index_vertex = IndexVertex()
            index_vertex.load(file)

            self.indexes_vertex.append(index_vertex)

    def save(self, file):
        if not isinstance(self.indexes_vertex, list) or len(self.indexes_vertex) != 3:
            raise Exception("(indexes_vertex) Invalid array length require 3 and have %d" % len(self.indexes_vertex))

        write_struct(file, '<h', self.poly_index)
        
        for index_vertex in self.indexes_vertex:
            index_vertex.save(file)

    def __repr__(self):
        return "OutFragMeshValue(poly_index=%d, indexes_vertex[3]=[%s, %s, %s])" % (
            self.poly_index,
            *self.indexes_vertex
        )

class OutFragMesh:
    def __init__(self, global_num_values=None, type_num_values=None, global_values=None, type_values=None):
        self.global_num_values=global_num_values
        self.type_num_values=type_num_values # Array uint32_t[2]
        self.global_values=global_values # Array OutFragValue[N(Mesh)][]
        self.type_values=type_values # Array OutFragValue[2][N(Mesh)][]

    def load(self, file, numMesh):
        self.global_num_values=[]
        self.type_num_values=[[] for i in range(2)]
        self.global_values=[]
        self.type_values=[[] for i in range(2)]

        numGlobal, = read_struct(file, '<I')
        numType = read_struct(file, '<2I')

        if numGlobal > 0:
            for i in range(numMesh):
                self.global_num_values.append(read_struct(file, '<I')[0])
        
        for i in range(2):
            if numType[i] > 0:
                for j in range(numMesh):
                    self.type_num_values[i].append(read_struct(file, '<I')[0])

        for value in self.global_num_values:
            self.global_values.append([])
            if value <= 0:
                continue
            for i in range(value):
                out_frag_mesh_value = OutFragMeshValue()
                out_frag_mesh_value.load(file)

                self.global_values[-1].append(out_frag_mesh_value)
        
        for i in range(2):
            for value in self.type_num_values[i]:
                self.type_values[i].append([])
                if value <= 0:
                    continue
                for j in range(value):
                    out_frag_mesh_value = OutFragMeshValue()
                    out_frag_mesh_value.load(file)

                    self.type_values[i][-1].append(out_frag_mesh_value)

    def save(self, file):
        if (
            not isinstance(self.global_num_values, list) or
            not isinstance(self.type_num_values, list) or
            not isinstance(self.global_values, list) or
            not isinstance(self.type_values, list)
        ):
            raise Exception("Invalid parameters")

        if len(self.type_num_values) != 2:
            raise Exception("Invalid Array length of type_num_values require 2 and have %d" % len(self.type_num_values))
        if len(self.type_values) != 2:
            raise Exception("Invalid Array length of type_values require 2 and have %d" % len(self.type_values))

        numGlobal = sum([v for v in sum(self.global_num_values, [])], 0)
        numType = [
            sum([v for v in sum(self.type_num_values[0], [])], 0),
            sum([v for v in sum(self.type_num_values[1], [])], 0)
        ]

        write_struct(file, "<I", numGlobal)
        write_struct(file, "<2I", *numType)

        if numGlobal > 0 and len(self.global_num_values) > 0:
            write_struct(file, "<{}I".format(len(self.global_num_values)), *self.global_num_values)

        for i in range(2):
            if numType[i] > 0 and len(self.type_num_values[i]) > 0:
                write_struct(file, "<{}I".format(len(self.type_num_values[i])), *self.type_num_values)
        
        if numGlobal > 0:
            for mesh in self.global_values:
                for value in mesh:
                    value.save(file)

        for i in range(2):
            if numType[i] > 0:
                for mesh in self.type_values[i]:
                    for value in mesh:
                        value.save(file)

    def __repr__(self):
        return "OutFrag(global_num_values=[%s], type_num_values=[%s], global_values=[%s], type_values=[%s])" % (
            repr(self.global_num_values),
            repr(self.type_num_values),
            repr(self.global_values),
            repr(self.type_values)
        )