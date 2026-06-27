# Copyright 2016 John Chadwick <john@jchw.io>
# Copyright 2023-2026 Acrisio Filho

# pet.py - implementation of Ntreev PangYa .pet, .apet, .bpet, .mpet format.
# By John Chadwick <johnwchadwick@gmail.com>
# By Acrisio Filho
#
# Special thanks to HSReina for their universal extractor and a few pointers.
# Also, to the developers of the original paktools and mpetmqo tool.

from io import BytesIO
from os.path import splitext
from enum import IntEnum

from .ioutil import (
    read_struct, write_struct,
    read_cstr, write_cstr,
    read_fixed_string, write_fixed_string,
    read_bone_id, write_bone_id,
    bytesFromCP949ToUnicode, unicodeTobytesCP949
)

class eFILE_TYPE(IntEnum):
    FT_TEXT= 1,
    FT_SMTL= 2,
    FT_BONE= 4,
    FT_ANIM= 8,
    FT_MESH= 16,
    FT_FANM= 32,
    FT_FRAM= 64,
    FT_MOTI= 128,
    FT_EXTR= 256
    FT_COLL= 512,
    FT_ALL= 1023,
    FT_SKINLIST= 65536,

class eSPECULAR_MATERIAL_TYPE(IntEnum):
    SMTL_BOOL= 0,
    SMTL_INT= 1,
    SMTL_FLOAT= 2,
    SMTL_VECTOR2= 3,
    SMTL_VECTOR3= 4,
    SMTL_VECTOR4= 5,
    SMTL_MATRIX= 6,
    SMTL_MATRIXARRAY= 7,
    SMTL_TEXTURE= 8,
    SMTL_NUM= 9

FILE_PET = eFILE_TYPE.FT_ALL
FILE_APET = eFILE_TYPE.FT_BONE | eFILE_TYPE.FT_ANIM | eFILE_TYPE.FT_FRAM | eFILE_TYPE.FT_MOTI
FILE_BPET = eFILE_TYPE.FT_BONE | eFILE_TYPE.FT_EXTR | eFILE_TYPE.FT_COLL
FILE_MPET = eFILE_TYPE.FT_TEXT | eFILE_TYPE.FT_SMTL | eFILE_TYPE.FT_BONE | eFILE_TYPE.FT_MESH | eFILE_TYPE.FT_FANM | eFILE_TYPE.FT_SKINLIST

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
            self.rest = 0xFFFE

    def save(self, file):
        write_struct(file, '<B', self.minor & 0xFF)
        write_struct(file, '<B', self.major & 0xFF)
        write_struct(file, '<H', self.rest)

    def __repr__(self):
        return "Version(%d.%d)" % (self.major, self.minor)

VERSION_1_0 = Version(1, 0)
VERSION_1_1 = Version(1, 1)
VERSION_1_2 = Version(1, 2)
VERSION_1_3 = Version(1, 3)

gFileType = FILE_PET
gVersion = VERSION_1_0

def setFileType(filepath):
    global gFileType
    gFileType = FILE_PET

    if filepath == '':
        return

    base, ext = splitext(filepath)

    if ext == '.pet':
        gFileType = FILE_PET
    elif ext == '.apet':
        gFileType = FILE_APET
    elif ext == '.bpet':
        gFileType = FILE_BPET
    elif ext == '.mpet':
        gFileType = FILE_MPET

def compareVersions(v1, v2):
    if v1.fullVersion() == v2.fullVersion():
        return 0
    
    if v1.major == v2.major:
        return -1 if v1.minor < v2.minor else 1

    return -1 if v1.major < v2.major else 1

class Puppet:
    def __init__(self, version=VERSION_1_3, bones=None, extras=None, mesh=None, textures=None, animations=None, fanims=None, frames=None, motions=None, collisions=None, smtls=None):
        self.version = version
        self.smtls = smtls
        self.animations = animations
        self.face_anims = fanims
        self.frames = frames
        self.motions = motions
        self.collisions = collisions
        self.extras = extras
        self.bones = bones
        self.textures = textures
        self.mesh = mesh
        self.is_pet, self.is_apet, self.is_bpet, self.is_mpet = False, False, False, False

    def load(self, file):
        global gVersion

        # Reset Version to 1.0
        self.version = gVersion = VERSION_1_0

        self.bones = []
        self.textures = []
        self.mesh = None
        self.smtls = []
        self.animations = []
        self.face_anims = []
        self.frames = []
        self.motions = []
        self.collisions = []
        self.extras = []

        self.initFileType(file.name)

        while True:
            block = Block()
            block.load(file)

            # EOF
            if not block.is_valid():
                return

            # Version block
            if block.id == b'VERS':
                self.version = Version()
                self.version.load(block.stream)
                gVersion = self.version
                print(self.version)
            
            # Specular Material block
            elif block.id == b'SMTL':
                count, = read_struct(block.stream, '<I')

                for i in range(count):
                    smtl = SpecularMaterial()
                    smtl.load(block.stream)

                    self.smtls.append(smtl)

            # Texture block
            elif block.id == b'TEXT':
                count, = read_struct(block.stream, '<I')

                for i in range(count):
                    texture = Texture()
                    texture.load(block.stream)

                    self.textures.append(texture)

            # Animation block
            elif block.id == b'ANIM':
                while True:
                    bone_id = read_bone_id(block.stream)
                    if bone_id == -1:
                        break

                    animation = Animation(bone_id)
                    animation.load(block.stream)

                    self.animations.append(animation)

            # Bone block
            elif block.id == b'BONE':
                count, = read_struct(block.stream, '<B')
                if count == 0:
                    count, = read_struct(block.stream, '<H')

                for i in range(count):
                    bone = Bone()
                    bone.load(block.stream)

                    self.bones.append(bone)

            # Mesh block
            elif block.id == b'MESH':
                mesh = Mesh()
                mesh.load(block.stream)

                self.mesh = mesh

            # Face Animation block
            elif block.id == b'FANM':
                count, = read_struct(block.stream, '<I')

                for i in range(count):
                    fanim = FaceAnimation()
                    fanim.load(block.stream)

                    self.face_anims.append(fanim)
            
            # Frame block
            elif block.id == b'FRAM':
                count, = read_struct(block.stream, '<I')

                for i in range(count):
                    frame = Frame()
                    frame.load(block.stream)

                    self.frames.append(frame)

            # Motion block
            elif block.id == b'MOTI':
                count, = read_struct(block.stream, '<I')

                for i in range(count):
                    motion = Motion()
                    motion.load(block.stream)

                    self.motions.append(motion)

            # Collision block
            elif block.id == b'COLL':
                count, = read_struct(block.stream, '<I')

                for i in range(count):
                    collision = Collision()
                    collision.load(block.stream)

                    self.collisions.append(collision)

            # Extra block
            elif block.id == b'EXTR':
                count, = read_struct(block.stream, '<I')

                for i in range(count):
                    extra = Extra()
                    extra.load(block.stream)

                    self.extras.append(extra)

            # Unknown block
            else:
                print('warning: unknown block type: %s' % block.id)

    def save(self, file, ignore_frame_limitation = False, ignore_animation_bone_limitation = False):
        global gVersion

        if (
            not isinstance(self.bones, list) or
            not isinstance(self.textures, list) or
            not isinstance(self.smtls, list) or
            not isinstance(self.animations, list) or
            not isinstance(self.face_anims, list) or
            not isinstance(self.frames, list) or
            not isinstance(self.motions, list) or
            not isinstance(self.collisions, list) or
            not isinstance(self.extras, list)
        ):
            raise Exception("Invalid Parameters")

        # set version
        gVersion = self.version

        self.initFileType(file.name)

        # Version block
        block = Block(b'VERS')

        self.version.save(block.stream)

        block.save(file)
        
        if gFileType & eFILE_TYPE.FT_TEXT: 
            # Texture block
            block = Block(b'TEXT')
            write_struct(block.stream, '<I', len(self.textures))

            for texture in self.textures:
                texture.save(block.stream)

            block.save(file)
        
        if gFileType & eFILE_TYPE.FT_SMTL:
            # Specular Material block
            block = Block(b'SMTL')
            write_struct(block.stream, '<I', len(self.smtls))

            for smtrl in self.smtls:
                smtrl.save(block.stream)

            block.save(file)

        if gFileType & eFILE_TYPE.FT_BONE:
            # Bone block
            block = Block(b'BONE')
            count = len(self.bones)
            if count > 0xFF or count == 0:
                write_struct(block.stream, '<BH', 0, count)
            else:
                write_struct(block.stream, '<B', count)

            for bone in self.bones:
                bone.save(block.stream)

            block.save(file)

        if gFileType & eFILE_TYPE.FT_ANIM:
            # Animation block
            block = Block(b'ANIM')
            count = len(self.animations)

            if not ignore_animation_bone_limitation:
                if compareVersions(gVersion, VERSION_1_3) == 0: # sexta temporada versão 1.3 máximo de 1024 animation bones
                    if count > 1024:
                        print("Aviso: Salvando os 1024 primeiros animation bones que é suportado pela versão 1.3")
                    count = min(count, 1024) # máximo de 1024 animation bones
                elif compareVersions(gVersion, VERSION_1_2) == 0: # quarta temporada versão 1.2 máximo de 512 animation bones
                    if count > 512:
                        print("Aviso: Salvando os 512 primeiros animation bones que é suportado pela versão 1.2")
                    count = min(count, 512) # máximo de 512 animation bones
                elif compareVersions(gVersion, VERSION_1_1) == 0: # segunda temporada versão 1.1 máximo de 256 animation bones
                    if count > 256:
                        print("Aviso: Salvando os 256 primeiros animation bones que é o suportado pela versão 1.1")
                    count = min(count, 256) # máximo de 256 animation bones
                else: # primeira temporada versão 1.0 máximo de 127 animation bones
                    if count > 127:
                        print("Aviso: Salvando os 127 primeiros animation bones que é o suportado pela versão 1.0")
                    count = min(count, 127) # máximo de 127 animation bones

            for i in range(count):
                self.animations[i].save(block.stream)
            write_struct(block.stream, '<B', 0xFF) # end

            block.save(file)
        
        if gFileType & eFILE_TYPE.FT_MESH:
            # Mesh block
            block = Block(b'MESH')

            self.mesh.save(block.stream)

            block.save(file)
        
        if gFileType & eFILE_TYPE.FT_FANM:
            # Face Animation block
            block = Block(b'FANM')
            write_struct(block.stream, '<I', len(self.face_anims))

            for fanim in self.face_anims:
                fanim.save(block.stream)

            block.save(file)
        
        if gFileType & eFILE_TYPE.FT_FRAM:
            # Frame block
            block = Block(b'FRAM')
            count = len(self.frames)

            if not ignore_frame_limitation:
                if compareVersions(gVersion, VERSION_1_3) == 0: # sexta temporada versão 1.3 máximo de 20000 frames
                    if count > 20000:
                        print("Aviso: Salvando os 20000 primeiros frames que é suportado pela versão 1.3")
                    count = min(count, 20000) # máximo de 20000 frames
                elif compareVersions(gVersion, VERSION_1_2) == 0: # quarta temporada versão 1.2 máximo de 10000 frames
                    if count > 10000:
                        print("Aviso: Salvando os 10000 primeiros frames que é suportado pela versão 1.2")
                    count = min(count, 10000) # máximo de 10000 frames
                elif compareVersions(gVersion, VERSION_1_1) == 0: # segunda temporada versão 1.1 máximo de 512 frames
                    if count > 512:
                        print("Aviso: Salvando os 512 primeiros frames que é o suportado pela versão 1.1")
                    count = min(count, 512) # máximo de 512 frames
                else: # primeira temporada versão 1.0 máximo de 256 frames
                    if count > 256:
                        print("Aviso: Salvando os 256 primeiros frames que é o suportado pela versão 1.0")
                    count = min(count, 256) # máximo de 256 frames

            write_struct(block.stream, '<I', count)

            for i in range(count):
                self.frames[i].save(block.stream)
            
            block.save(file)

        if gFileType & eFILE_TYPE.FT_MOTI:
            # Motion block
            block = Block(b'MOTI')
            write_struct(block.stream, '<I', len(self.motions))

            for motion in self.motions:
                motion.save(block.stream)

            block.save(file)
        
        if gFileType & eFILE_TYPE.FT_EXTR:
            # Extra block
            block = Block(b'EXTR')
            write_struct(block.stream, '<I', len(self.extras))

            for extra in self.extras:
                extra.save(block.stream)

            block.save(file)

        if gFileType & eFILE_TYPE.FT_COLL:
            # Collision block
            block = Block(b'COLL')
            write_struct(block.stream, '<I', len(self.collisions))

            for collision in self.collisions:
                collision.save(block.stream)

            block.save(file)
    
    def initFileType(self, filename):

        setFileType(filename)

        if gFileType == FILE_PET:
            self.is_pet = True
        elif gFileType == FILE_APET:
            self.is_apet = True
        elif gFileType == FILE_BPET:
            self.is_bpet = True
        elif gFileType == FILE_MPET:
            self.is_mpet = True

    def getTotalAnimationTime(self):
        return round(max(self.animations, key=lambda x: x.animTime, default=Animation()).animTime * 30)

    def __repr__(self):
        return "Puppet(Version=%s, SpecularMaterial=%s, Bones=%s, Textures=%s, Collisions=%s, Extras=%s, mesh=%s, Frames=%s, Motions=%s, FaceAnimation=%s, Animations=%s)" % (
            repr(self.version),
            repr(self.smtls),
            repr(self.bones),
            repr(self.textures),
            repr(self.collisions),
            repr(self.extras),
            repr(self.mesh),
            repr(self.frames),
            repr(self.motions),
            repr(self.face_anims),
            repr(self.animations)
        )

class Block:
    def __init__(self, id=None):
        self.stream = BytesIO()
        self.id = id

    def is_valid(self):
        return self.id is not None

    def load(self, file):
        id = file.read(4)
        if id is None or len(id) == 0:
            id = None
            return
        size, = read_struct(file, '<I')
        data = file.read(size)

        self.id = id
        self.stream = BytesIO(data)

    def save(self, file):
        size = self.stream.tell()
        self.stream.seek(0)
        data = self.stream.read()

        file.write(self.id)
        write_struct(file, '<I', size)
        file.write(data)

    def __repr__(self):
        return "Block(id=%s)" % str(self.id)

# Aqui a maioria é o id dos ossos de animação de asas
class Extra:
    def __init__(self, bone_id=None):
        self.bone_id = bone_id

    def load(self, file):
        self.bone_id = read_bone_id(file)

    def save(self, file):
        write_bone_id(file, self.bone_id)

    def __repr__(self):
        return "Extra(boneId=%d)" % (self.bone_id)

class Collision:
    def __init__(self, shape=None, show=None, scripts=None, area=None):
        self.shape=shape
        self.show=show
        self.scripts=scripts # Sempre uma lista de tamanho 4, {[0] - Box name, [1] - Bone name, [2:3] - Options(bound_box) %s %s}
        self.area=area

    def load(self, file):
        self.scripts = []

        self.shape, = read_struct(file, '<I')
        self.show, = read_struct(file, '<I')
        
        for i in range(4):
            script = read_fixed_string(file)
            self.scripts.append(bytesFromCP949ToUnicode(script))

        self.area = read_struct(file, '<6f')

    def save(self, file):
        if not isinstance(self.scripts, list):
            raise Exception("Invalid parameters")

        write_struct(file, '<2I', self.shape, self.show)

        for i in range(4):
            try:
                write_fixed_string(file, unicodeTobytesCP949(self.scripts[i]))
            except IndexError:
                write_fixed_string(file, b'')

        write_struct(file, '<6f', *self.area)

    def __repr__(self):
        return "Collision(shape=%d, show=%d, box_name=%s, bone_name=%s, option1=%s, option2=%s, minx=%f, miny=%f, minz=%f, maxx=%f, maxy=%f, maxz=%f)" % (
            self.shape, self.show, *self.scripts, *self.area
        )

class Motion:
    def __init__(self, name=None, frame_start=None, frame_end=None, next_move=None, connection_method=None, connection_time=None, root_bone=None):
        self.name=name
        self.frame_start=frame_start
        self.frame_end=frame_end
        self.next_move=next_move
        self.connection_method=connection_method
        self.connection_time=connection_time
        self.root_bone=root_bone

    def load(self, file):
        self.name = bytesFromCP949ToUnicode(read_fixed_string(file))
        self.frame_start, = read_struct(file, '<I')
        self.frame_end, = read_struct(file, '<I')
        self.next_move = bytesFromCP949ToUnicode(read_fixed_string(file))
        self.connection_method = bytesFromCP949ToUnicode(read_fixed_string(file))
        self.connection_time, = read_struct(file, '<f')
        self.root_bone = bytesFromCP949ToUnicode(read_fixed_string(file))

    def save(self, file):
        write_fixed_string(file, unicodeTobytesCP949(self.name))
        write_struct(file, '<I', self.frame_start)
        write_struct(file, '<I', self.frame_end)
        write_fixed_string(file, unicodeTobytesCP949(self.next_move))
        write_fixed_string(file, unicodeTobytesCP949(self.connection_method))
        write_struct(file, '<f', self.connection_time)
        write_fixed_string(file, unicodeTobytesCP949(self.root_bone))
    
    def __repr__(self):
        return "Motion(name=%s, frame_start=%d, frame_end=%d, next_move=%s, connection_method=%s, connection_time=%f, root_bone=%s)" % (
            self.name, self.frame_start, self.frame_end, self.next_move, self.connection_method, self.connection_time, self.root_bone
        )

class Frame:
    def __init__(self, index=None, script='', check=0):
        self.index=index
        self.script=script # Sempre uma lista de tamanho 3, do tipo String
        self.check=check

    def load(self, file):
        self.script = ''
        self.check = 0

        self.index, = read_struct(file, '<I')
        for i in range(3):
            msg = read_fixed_string(file)
            self.script += bytesFromCP949ToUnicode(msg, '')

        self.check, = read_struct(file, '<I')

    def save(self, file):
        write_struct(file, '<I', self.index)

        chunk_len = -1

        if compareVersions(gVersion, VERSION_1_1) <= 0:
            chunk_len = 512
        elif compareVersions(gVersion, VERSION_1_2) == 0:
            chunk_len = 1024
        
        def chunked(size, source):
            return [source[i:i+size] for i in range(0, len(source), size)]
        
        def makeChunks(script):
            if chunk_len == -1:
                return [script]
            return chunked(chunk_len, script)
        
        chunks = makeChunks(unicodeTobytesCP949(self.script))

        for i in range(3):
            try:
                write_fixed_string(file, chunks[i])
            except IndexError:
                write_fixed_string(file, b'')

        write_struct(file, '<I', self.check)

    def __repr__(self):
        return "Frame(index=%d, script=%s, check=%d)" % (self.index, self.script, self.check)

class FaceAnimation:
    def __init__(self, group=None, name=None, material_name=None):
        self.group=group
        self.name=name
        self.material_name=material_name

    def load(self, file):
        self.group, = read_struct(file, '<B')
        self.name = bytesFromCP949ToUnicode(read_struct(file, '<32s')[0].split(b'\x00')[0])
        self.material_name = bytesFromCP949ToUnicode(read_struct(file, '<32s')[0].split(b'\x00')[0])

    def save(self, file):
        write_struct(file, '<B', self.group & 0xFF)
        write_struct(file, '<32s', unicodeTobytesCP949(self.name))
        write_struct(file, '<32s', unicodeTobytesCP949(self.material_name))

    def __repr__(self):
        return "FaceAnimation(name=%s, material_name=%s, group=%d)" % (self.name, self.material_name, self.group)

class Position:
    def __init__(self, time=None, position=None):
        self.time=time
        self.position=position

    def load(self, file):
        self.position = ()

        self.time, = read_struct(file, '<f')
        self.position = read_struct(file, '<3f')

    def save(self, file):
        if not isinstance(self.position, (list, tuple)):
            raise Exception("Invalid parameters")

        write_struct(file, '<4f', self.time, *self.position)

    def __repr__(self):
        return "Position(time=%f, x=%f, y=%f, z=%f)" % (self.time, *self.position)

class Rotation:
    def __init__(self, time=None, rotation=None):
        self.time=time
        self.rotation=rotation

    def load(self, file):
        self.rotation = ()

        self.time, = read_struct(file, '<f')
        self.rotation = read_struct(file, '<4f')

    def save(self, file):
        if not isinstance(self.rotation, (list, tuple)):
            raise Exception("Invalid parameters")

        write_struct(file, '<5f', self.time, *self.rotation)

    def __repr__(self):
        return "Rotation(time=%f, x=%f, y=%f, z=%f, w=%f)" % (self.time, *self.rotation)

class Scaling:
    def __init__(self, time=None, scaling=None):
        self.time=time
        self.scaling=scaling

    def load(self, file):
        self.scaling = ()

        self.time, = read_struct(file, '<f')
        self.scaling = read_struct(file, '<3f')

    def save(self, file):
        if not isinstance(self.scaling, (list, tuple)):
            raise Exception("Invalid parameters")

        write_struct(file, '<4f', self.time, *self.scaling)

    def __repr__(self):
        return "Scaling(time=%f, x=%f, y=%f, z=%f)" % (self.time, *self.scaling)

class OrientationFlag:
    def __init__(self, time=None, orientation_flag = -1.0):
        self.time=time
        self.orientation_flag=orientation_flag

    def load(self, file):
        self.time, = read_struct(file, '<f')
        self.orientation_flag, = read_struct(file, '<f')

    def save(self, file):
        write_struct(file, '<2f', self.time, self.orientation_flag)

    def __repr__(self):
        return "OrientationFlag(time=%f, orientation_flag=%f)" % (self.time, self.orientation_flag)

class Animation:
    def __init__(self, bone_id=None, positions=None, rotations=None, scalings=None, orientation_flags=None, animTime=0.0):
        self.bone_id=bone_id
        self.positions=positions
        self.rotations=rotations
        self.scalings=scalings
        self.orientation_flags=orientation_flags # version 1.3
        self.animTime=animTime

    def load(self, file):
        self.positions = []
        self.rotations = []
        self.scalings = []
        self.orientation_flags = []
        self.animTime = 0.0

        count, = read_struct(file, '<I')

        for i in range(count):
            position = Position()
            position.load(file)

            self.positions.append(position)
        
        if len(self.positions) > 0:
            self.animTime = max(self.animTime, max(self.positions, key=lambda pos: pos.time).time)
        
        count, = read_struct(file, '<I')

        for i in range(count):
            rotation = Rotation()
            rotation.load(file)

            self.rotations.append(rotation)

        if len(self.rotations) > 0:
            self.animTime = max(self.animTime, max(self.rotations, key=lambda rot: rot.time).time)

        count, = read_struct(file, '<I')

        for i in range(count):
            scaling = Scaling()
            scaling.load(file)

            self.scalings.append(scaling)

        if len(self.scalings) > 0:
            self.animTime = max(self.animTime, max(self.scalings, key=lambda scal: scal.time).time)

        if compareVersions(gVersion, VERSION_1_3) >= 0:
            count, = read_struct(file, '<I')

            for i in range(count):
                orientation_flag = OrientationFlag()
                orientation_flag.load(file)

                self.orientation_flags.append(orientation_flag)

            if len(self.orientation_flags) > 0:
                self.animTime = max(self.animTime, max(self.orientation_flags, key=lambda orientation_flag: orientation_flag.time).time)
    
    def save(self, file):
        if (
            not isinstance(self.positions, list) or
            not isinstance(self.rotations, list) or
            not isinstance(self.scalings, list) or
            not isinstance(self.orientation_flags, list)
        ):
            raise Exception("Invalid parameters")

        write_bone_id(file, self.bone_id)

        write_struct(file, '<I', len(self.positions))

        for position in self.positions:
            position.save(file)

        write_struct(file, '<I', len(self.rotations))

        for rotation in self.rotations:
            rotation.save(file)

        if compareVersions(gVersion, VERSION_1_2) >= 0:
            write_struct(file, '<I', len(self.scalings))

            for scaling in self.scalings:
                scaling.save(file)
        else:
            write_struct(file, '<I', 0)

        if compareVersions(gVersion, VERSION_1_3) >= 0:
            write_struct(file, '<I', len(self.orientation_flags))

            for orientation_flag in self.orientation_flags:
                orientation_flag.save(file)

    def __repr__(self):
        return "Animation(BoneId=%d, Time=%f, Positions=%s, Rotations=%s, Scalings=%s, OrientationFlags=%s)" % (
            self.bone_id, self.animTime,
            repr(self.positions),
            repr(self.rotations),
            repr(self.scalings),
            repr(self.orientation_flags)
        )

class SpecularValue:
    def __init__(self, name=None, type=None, value=None):
        self.name=name
        self.type=type
        self.value=value

    def load(self, file):
        self.name = bytesFromCP949ToUnicode(read_fixed_string(file))
        self.type, = read_struct(file, '<I')

        if self.type == eSPECULAR_MATERIAL_TYPE.SMTL_BOOL:
            self.value, = read_struct(file, '<I')
        elif self.type == eSPECULAR_MATERIAL_TYPE.SMTL_INT:
            self.value, = read_struct(file, '<i')
        elif self.type == eSPECULAR_MATERIAL_TYPE.SMTL_FLOAT:
            self.value, = read_struct(file, '<f')
        elif self.type == eSPECULAR_MATERIAL_TYPE.SMTL_VECTOR2:
            self.value = read_struct(file, '<2f')
        elif self.type == eSPECULAR_MATERIAL_TYPE.SMTL_VECTOR3:
            self.value = read_struct(file, '<3f')
        elif self.type == eSPECULAR_MATERIAL_TYPE.SMTL_VECTOR4:
            self.value = read_struct(file, "<4f")
        elif self.type == eSPECULAR_MATERIAL_TYPE.SMTL_MATRIX:
            self.value = read_struct(file, "<16f")
        elif self.type == eSPECULAR_MATERIAL_TYPE.SMTL_TEXTURE:
            self.value = bytesFromCP949ToUnicode(read_fixed_string(file))
    
    def save(self, file):
        write_fixed_string(file, unicodeTobytesCP949(self.name))
        write_struct(file, '<I', self.type)

        if self.type == eSPECULAR_MATERIAL_TYPE.SMTL_BOOL:
            write_struct(file, '<I', self.value)
        elif self.type == eSPECULAR_MATERIAL_TYPE.SMTL_INT:
            write_struct(file, '<i', self.value)
        elif self.type == eSPECULAR_MATERIAL_TYPE.SMTL_FLOAT:
            write_struct(file, '<f', self.value)
        elif self.type == eSPECULAR_MATERIAL_TYPE.SMTL_VECTOR2:
            write_struct(file, '<2f', *self.value)
        elif self.type == eSPECULAR_MATERIAL_TYPE.SMTL_VECTOR3:
            write_struct(file, '<3f', *self.value)
        elif self.type == eSPECULAR_MATERIAL_TYPE.SMTL_VECTOR4:
            write_struct(file, '<4f', *self.value)
        elif self.type == eSPECULAR_MATERIAL_TYPE.SMTL_MATRIX:
            write_struct(file, '<16f', *self.value)
        elif self.type == eSPECULAR_MATERIAL_TYPE.SMTL_TEXTURE:
            write_fixed_string(file, unicodeTobytesCP949(self.value))

    def __repr__(self):
        return ("SpecularValue(name=%s, type=%d, value=" % (self.name, self.type)) + self.value + ")"

class SpecularMaterial:
    def __init__(self, name=None, smtlvs=None):
        self.name=name
        self.smtlvs=smtlvs

    def load(self, file):
        self.smtlvs = []

        self.name = bytesFromCP949ToUnicode(read_fixed_string(file))
        count, = read_struct(file, '<I')

        for i in range(count):
            sv = SpecularValue()
            sv.load(file)

            self.smtlvs.append(sv)

    def save(self, file):
        if not isinstance(self.smtlvs, list):
            raise Exception("Invalid parameters")

        write_fixed_string(file, unicodeTobytesCP949(self.name))
        write_struct(file, '<I', len(self.smtlvs))
        for sv in self.smtlvs:
            sv.save(file)

    def __repr__(self):
        return "SpacularMaterial(name=%s, SpecularValue=%s)" % (self.name, repr(self.smtlvs))

class Texture:
    def __init__(self, fn=None, flag=None, group=None, diffuse=None, handle=None):
        self.fn = fn
        self.flag = flag
        self.group = group
        self.diffuse = diffuse
        self.handle = handle

    def is_valid(self):
        return self.fn is not None

    def load(self, file):
        # looks like Ntreev left us some stack garbage
        self.fn = bytesFromCP949ToUnicode(read_struct(file, '<32s')[0].split(b'\x00')[0])
        self.flag = int.from_bytes(read_struct(file, '<c')[0], byteorder='little', signed=True)
        self.group, = read_struct(file, '<B')
        file.read(2) # align 4
        self.diffuse, = read_struct(file, '<I')
        self.handle, = read_struct(file, '<I')

    def save(self, file):
        write_struct(file, '<32s', unicodeTobytesCP949(self.fn))
        write_struct(file, '<c', int.to_bytes(self.flag, 1, byteorder='little', signed=True))
        write_struct(file, '<B', self.group & 0xFF)
        file.write(b'\x00\x00') # align 4
        write_struct(file, '<I', self.diffuse)
        write_struct(file, '<I', self.handle)

    def __repr__(self):
        return "Texture(filename=%s, flag=%d, group=%d, diffuse=0x%.08x, handle=%d)" % (
            self.fn, self.flag, self.group, self.diffuse, self.handle
        )

class Bone:
    def __init__(self, name=None, parent=None, matrix=None, orientation_flag = -1.0):
        self.name = name
        self.parent = parent
        self.matrix = matrix
        self.orientation_flag = orientation_flag # version 1.3

    def is_valid(self):
        return self.name is not None

    def load(self, file):
        self.matrix = ()

        self.name = bytesFromCP949ToUnicode(read_cstr(file))
        self.parent = read_bone_id(file)
        if gFileType != FILE_APET and (gFileType & eFILE_TYPE.FT_BONE):
            self.matrix = read_struct(file, '<12f')
            if compareVersions(gVersion, VERSION_1_3) >= 0:
                self.orientation_flag, = read_struct(file, "<f")

    def save(self, file):
        if not isinstance(self.matrix, (list, tuple)):
            raise Exception("Invalid parameters")

        write_cstr(file, unicodeTobytesCP949(self.name))
        write_bone_id(file, self.parent)
        if gFileType != FILE_APET and (gFileType & eFILE_TYPE.FT_BONE):
            write_struct(file, '<12f', *self.matrix)
            if compareVersions(gVersion, VERSION_1_3) >= 0:
                write_struct(file, '<f', self.orientation_flag)

    def __repr__(self):
        values = [self.name, self.parent]
        fmt = "Bone(name=%s, parent=%d"
        if gFileType != FILE_APET and (gFileType & eFILE_TYPE.FT_BONE):
            values.extend(self.matrix)
            fmt = fmt + ", matrix=[%f" + (", %f" * 11) + "]"
            if compareVersions(gVersion, VERSION_1_3) >= 0:
                values.append(self.orientation_flag)
                fmt = fmt + ", orientation_flag=%f"
        fmt = fmt + ")"

        return fmt % tuple(values)

class MpetExtraValue:
    def __init__(self, bone_id=0, vertice_idx=0, vertice_len=0, poly_idx=0, poly_len=0):
        self.bone_id=bone_id
        self.vertice_idx=vertice_idx
        self.vertice_len=vertice_len
        self.poly_idx=poly_idx
        self.poly_len=poly_len
    
    def load(self, file):
        self.bone_id, = read_struct(file, '<B')
        file.read(3) # align 4
        self.vertice_idx, = read_struct(file, '<I')
        self.vertice_len, = read_struct(file, '<I')
        self.poly_idx, = read_struct(file, '<I')
        self.poly_len, = read_struct(file, '<I')

    def save(self, file):
        write_struct(file, '<B', self.bone_id & 0xFF)
        file.write(b'\x00\x00\x00') # align 4
        write_struct(file, '<I', self.vertice_idx)
        write_struct(file, '<I', self.vertice_len)
        write_struct(file, '<I', self.poly_idx)
        write_struct(file, '<I', self.poly_len)

    def __repr__(self):
        return "MpetExtraVelue(bone_id=%d, vertice_index=%d, vertice_len=%d, polygon_index=%d, polygon_length=%d)" % (
            self.bone_id, self.vertice_idx, self.vertice_len, self.poly_idx, self.poly_len
        )

class BoneWeight:
    def __init__(self, weight=None, id=None):
        self.weight = weight
        self.id = id

    def load(self, file):
        self.weight, = read_struct(file, '<B')
        self.id = read_bone_id(file)

    def save(self, file):
        write_struct(file, '<B', self.weight & 0xFF)
        write_bone_id(file, self.id)

    def __repr__(self):
        return "BoneWeight(weight=%d, id=%d)" % (self.weight, self.id)

class Vertex:
    def __init__(self, x=None, y=None, z=None, weight_global=None, bone_weights=None):
        self.x, self.y, self.z = x, y, z
        self.bone_weights = bone_weights
        self.weight_global = weight_global

    def load(self, file):
        wsum = 0
        self.bone_weights = []

        self.x, self.y, self.z = read_struct(file, '<3f')

        if gFileType == FILE_MPET:
            self.weight_global, = read_struct(file, '<f')
        else:
            self.weight_global = 1.0

        # Bone weights continue until saturated.
        while wsum < 0xFF:
            weight = BoneWeight()
            weight.load(file)

            wsum += weight.weight
            self.bone_weights.append(weight)

        # Strangely, file leaves space for at least 2.
        if len(self.bone_weights) < 2:
            file.read(2)

    def save(self, file):
        if not isinstance(self.bone_weights, list):
            raise Exception("Invalid parameters")

        write_struct(file, '<3f', self.x, self.y, self.z)

        if gFileType == FILE_MPET:
            write_struct(file, '<f', self.weight_global)

        for weight in self.bone_weights:
            weight.save(file)

        if len(self.bone_weights) < 2:
            file.write(b'\x00\x00')

    def __repr__(self):
        return "Vertex(x=%f, y=%f, z=%f, weight_global=%f, bone_weights=%s)" % (
            self.x, self.y, self.z,
            self.weight_global,
            repr(self.bone_weights)
        )

class UVMapping:
    def __init__(self, u=None, v=None):
        self.u=u
        self.v=v

    def load(self, file):
        self.u, self.v = read_struct(file, '<2f')

    def save(self, file):
        write_struct(file, '<2f', self.u, self.v)

    def __repr__(self):
        return "UVMapping(u=%f, v=%f)" % (self.u, self.v)

class PolygonIndex:
    def __init__(self, index=None, nx=None, ny=None, nz=None, uvMapping=None):
        self.index = index
        self.nx, self.ny, self.nz = nx, ny, nz
        self.uvMapping = uvMapping

    def load(self, file):
        self.uvMapping = []

        self.index, = read_struct(file, '<I')
        self.nx, self.ny, self.nz = read_struct(file, '<3f')
        count = 1
        if compareVersions(gVersion, VERSION_1_2) >= 0:
            count, = read_struct(file, '<B')
        for i in range(count):
            uv = UVMapping()
            uv.load(file)

            self.uvMapping.append(uv)

    def save(self, file):
        if not isinstance(self.uvMapping, list):
            raise Exception("Invalid parameters")

        write_struct(file, '<I', self.index)
        write_struct(file, '<3f', self.nx, self.ny, self.nz)
        if compareVersions(gVersion, VERSION_1_2) >= 0:
            write_struct(file, '<B', len(self.uvMapping))

            for uv in self.uvMapping:
                uv.save(file)

        elif len(self.uvMapping) > 0:
            self.uvMapping[0].save(file)
        else:
            write_struct(file, '<2f', 0.0, 0.0)

    def __repr__(self):
        return "PolygonIndex(index=%d, nx=%f, ny=%f, nz=%f, uvMapping=%s)" % (
            self.index,
            self.nx, self.ny, self.nz,
            repr(self.uvMapping)
        )

class Polygon:
    def __init__(self, indices=None):
        self.indices = indices

    def load(self, file):
        self.indices = []
        for i in range(3):
            index = PolygonIndex()
            index.load(file)

            self.indices.append(index)

    def save(self, file):
        if not isinstance(self.indices, list):
            raise Exception("Invalid parameters")

        for index in self.indices:
            index.save(file)
    
    def __repr__(self):
        return "Polygon(indices=%s)" % repr(self.indices)

class Mesh:
    def __init__(self, vertices=None, polygons=None, texmap=None, mpetexs=None, texmap_specular=None):
        self.vertices = vertices
        self.polygons = polygons
        self.texmap = texmap
        self.mpetexs = mpetexs
        self.texmap_specular = texmap_specular # versão 1.2 - Aqui é o texmap para os Specular Material, -1 sem index, >= 0 tem o index do Specular Material

    def load(self, file):
        self.vertices = []
        self.polygons = []
        self.texmap = []
        self.mpetexs = []
        self.texmap_specular = []

        if gFileType == FILE_MPET:
            num_mpetex, = read_struct(file, '<B')
            for i in range(num_mpetex):
                mpetEx = MpetExtraValue()
                mpetEx.load(file)
                self.mpetexs.append(mpetEx)

        # Vertices
        num_vertices, = read_struct(file, '<I')
        for i in range(num_vertices):
            vertex = Vertex()
            vertex.load(file)

            self.vertices.append(vertex)

        # Polygons
        num_polygons, = read_struct(file, '<I')
        for i in range(num_polygons):
            polygon = Polygon()
            polygon.load(file)

            self.polygons.append(polygon)

        # Mapping of polygons to textures
        for i in range(num_polygons):
            self.texmap.append(read_struct(file, '<b')[0])

        if compareVersions(gVersion, VERSION_1_2) >= 0:
            for i in range(num_polygons):
                self.texmap_specular.append(read_struct(file, '<b')[0])
    
    def save(self, file):
        if (
            not isinstance(self.vertices, list) or
            not isinstance(self.polygons, list) or
            not isinstance(self.texmap, list) or
            not isinstance(self.mpetexs, list) or
            not isinstance(self.texmap_specular, list)
        ):
            raise Exception("Invalid parameters")

        if gFileType == FILE_MPET:
            write_struct(file, '<B', len(self.mpetexs))
            for mpetex in self.mpetexs:
                mpetex.save(file)
        write_struct(file, '<I', len(self.vertices))
        for vertex in self.vertices:
            vertex.save(file)
        write_struct(file, '<I', len(self.polygons))
        for polygon in self.polygons:
            polygon.save(file)
        for tex in self.texmap:
            write_struct(file, '<b', tex)
        if compareVersions(gVersion, VERSION_1_2) >= 0:
            for tex in self.texmap_specular:
                write_struct(file, '<b', tex)

    def __repr__(self):
        return "Mesh(vertices=%s, polygons=%s, texmap=%s, mpetexs=%s, texmap_specular=%s)" % (
            repr(self.vertices),
            repr(self.polygons),
            repr(self.texmap),
            repr(self.mpetexs),
            repr(self.texmap_specular)
        )