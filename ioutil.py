# Copyright 2016 John Chadwick <john@jchw.io>
# Copyright 2023-2026 Acrisio Filho

# ioutil.py - Just some simple utilities for reading/writing C-style data.
# Every project has to have it's own little utility functions. It sucks but
# it's better than repeating yourself ad nauseum.

import struct

def wraptext(s, w):
    return [s[i:i + w] for i in range(0, len(s), w)]

# read_struct reads struct data from a file-like object
def read_struct(file, fmt):
    size = struct.calcsize(fmt)
    data = file.read(size)

    if len(data) < size:
        print('warning: short struct read (%i < %i)' % (len(data), size))

    return struct.unpack(fmt, data)


# write_struct writes struct data to a file-like object
def write_struct(file, fmt, *args):
    file.write(struct.pack(fmt, *args))


# read_cstr reads a C-style string (and returns a `bytes` object.)
def read_cstr(file):
    buf = bytearray()
    while True:
        b = file.read(1)
        if b == '' or b == b'\x00':
            return bytes(buf)
        else:
            buf.append(ord(b))

# write_cstr writes a C-style string
def write_cstr(file, buf):
    file.write(buf + b'\x00')


def read_fixed_string(file):
    length, = read_struct(file, '<I')

    if length <= 0:
        return b''
    
    return read_struct(file, "<{}s".format(length))[0].split(b'\x00')[0]

def write_fixed_string(file, buff):
    length = len(buff)

    write_struct(file, '<I', length)

    if length > 0:
        file.write(buff)

def read_bone_id(file):
    bone_id, = read_struct(file, '<B')

    if bone_id == 0xFF:
        return -1

    if bone_id == 0xFE:
        bone_id, = read_struct(file, '<h')

    if bone_id == 0xFFFF:
        return -1
    
    return bone_id

def write_bone_id(file, bone_id):
    if bone_id > 0xFD:
        write_struct(file, '<Bh', 0xFE, bone_id)
    else:
        write_struct(file, '<B', bone_id & 0xFF)

def bytesFromCP949ToUnicode(bytes, replace="Invalid bytes"):
    try:
        return bytes.decode('cp949')
    except UnicodeDecodeError as e:
        print("[", bytes, "]", e)
        return replace

def unicodeTobytesCP949(unicode):
    try:
        return unicode.encode('cp949')
    except UnicodeEncodeError as e:
        print("[" + unicode + "]", e)

class AABB:
    def __init__(self, minx=None, miny=None, minz=None, maxx=None, maxy=None, maxz=None):
        self.minx = minx
        self.miny = miny
        self.minz = minz
        self.maxx = maxx
        self.maxy = maxy
        self.maxz = maxz

    def load(self, file):
        self.minx, self.miny, self.minz = read_struct(file, "<3f")
        self.maxx, self.maxy, self.maxz = read_struct(file, "<3f")

    def save(self, file):
        write_struct(file, "<3f", self.minx, self.miny, self.minz)
        write_struct(file, "<3f", self.maxx, self.maxy, self.maxz)

    def tolist(self):
        return [
            self.minx, self.miny, self.minz,
            self.maxx, self.maxy, self.maxz
        ]

    def copy(self):
        return AABB(*self.tolist())

    def __repr__(self):
        return "AABB(minx=%f, miny=%f, minz=%f, maxx=%f, maxy=%f, maxz=%f)" % (
            self.minx, self.miny, self.minz,
            self.maxx, self.maxy, self.maxz
        )
        return unicode.encode('cp949', errors='backslashreplace')