# Copyright 2016 John Chadwick <john@jchw.io>
# Copyright 2023-2026 Acrisio Filho

import bpy # pyright: ignore[reportMissingImports]
from mathutils import Matrix # pyright: ignore[reportMissingImports]
from bpy_extras.io_utils import ( # pyright: ignore[reportMissingImports]
    ImportHelper,
    ExportHelper,
)

from .util import (
    PangyaToBlenderMatrix,
    BlenderToPangyaMatrix
)

from .reload_addon import (
    ReloadAddonOperator,
    reigster_hotkey_reload_addon,
    unregister_hotkey_reload_addon,
    reload_addon_modules
)

# peice of code from valve benlder tools, to reload scripts(addon)
# Python doesn't reload package sub-modules at the same time as __init__.py!
reload_addon_modules()

bl_info = {
    "name": "PangYa Model",
    "author": "John Chadwick & Acrisio Filho",
    "version": (2, 0, 0),
    "blender": (2, 80, 0),
    "location": "File > Import-Export",
    "description": "Import-Export PangYa (.pet, .apet, .bpet and .mpet), (.gbin, .sgbin, .aibin, .sbin) files.",
    "category": "Import-Export",
    "warning": "Base from John Chadwick, with addition of new features and fixing of structures types by Acrisio Filho"
}

# ImportPet implements the operator for importing Pet models.
class ImportPet(bpy.types.Operator, ImportHelper):
    """Import from Pangya Model (.pet, .apet, .bpet, .mpet)"""
    bl_idname = 'import.pangya_pet'
    bl_label = 'Import Pangya Model'
    bl_options = {'UNDO'}

    filename_ext = ".pet;.apet;.bpet;.mpet"
    filter_glob: bpy.props.StringProperty(
        default="*.pet;*.apet;*.bpet;*.mpet",
        options={'HIDDEN'},
    ) # pyright: ignore[reportInvalidTypeForm]

    anim_enable: bpy.props.BoolProperty(
        name="Import Animation",
        description="Import animation if puppet have it",
        default=True
    ) # pyright: ignore[reportInvalidTypeForm]

    collisionBox_enable: bpy.props.BoolProperty(
        name="Import Collision Box",
        description="Import collision box if puppet have it",
        default=True
    ) # pyright: ignore[reportInvalidTypeForm]

    specular_material_filter_enable: bpy.props.BoolProperty(
        name="Apply Specular Material Filter",
        description="Apply Specular Material Filter if puppet have it",
        default=True
    ) # pyright: ignore[reportInvalidTypeForm]

    collisionBox_show: bpy.props.BoolProperty(
        name="Show Collision Box",
        description="Show collision box in render",
        default=False
    ) # pyright: ignore[reportInvalidTypeForm]

    # support to load multiples files
    files: bpy.props.CollectionProperty(type=bpy.types.PropertyGroup) # pyright: ignore[reportInvalidTypeForm]

    def execute(self, context):
        from . import import_pet

        # load
        return import_pet.load(self, context, PangyaToBlenderMatrix())

# ExportPet implements the operator for exporting to Pet.
class ExportPet(bpy.types.Operator, ExportHelper):
    """Export to Pangya Model (.pet, .apet, .bpet, .mpet)"""
    bl_idname = 'export.pangya_pet'
    bl_label = 'Export Pangya Model'

    filename_ext = ".pet"
    filter_glob: bpy.props.StringProperty(
        default="*.pet",
        options={'HIDDEN'},
        maxlen=255
    ) # pyright: ignore[reportInvalidTypeForm]

    def update_format(self, context):
        context.space_data.params.filter_glob = self.filter_glob = self.format
        context.space_data.operator.filename_ext = self.format[1:]
        bpy.ops.file.refresh()

    format: bpy.props.EnumProperty(
        name="Formato",
        description="Formato em que o modelo vai ser salvo",
        items=(
            ("*.pet", ".pet", "Modelo completo"),
            ("*.apet", ".apet", "Modelo de animação"),
            ("*.bpet", ".bpet", "Modelo de esqueleto"),
            ("*.mpet", ".mpet", "Modelo de parte separada do modelo completo")
        ),
        default="*.pet",
        update=update_format
    ) # pyright: ignore[reportInvalidTypeForm]

    version: bpy.props.EnumProperty(
        name="Versão",
        description="Versão em que o modelo vai ser salvo",
        items=(
            ("1,0", "1.0", "Versão suportada pela primeira temporada do PangYa"),
            ("1,1", "1.1", "Versão suportada pela segunda temporada do PangYa"),
            ("1,2", "1.2", "Versão suportada pela quarta temporada do PangYa"),
            ("1,3", "1.3", "Versão suportada pela sexta temporada do PangYa"),
        ),
        default="1,3"
    ) # pyright: ignore[reportInvalidTypeForm]

    ignore_frame_limitation: bpy.props.BoolProperty(
        name="Ignore frame limitation",
        description="Ignora limitação de frames independente da versão",
        default=False
    ) # pyright: ignore[reportInvalidTypeForm]

    ignore_animation_bone_limitation: bpy.props.BoolProperty(
        name="Ignore animation bone limitation",
        description="Ignora limitação de ossos de animação independente da versão",
        default=False
    ) # pyright: ignore[reportInvalidTypeForm]

    def invoke(self, context, event):
        self.filename_ext = self.format[1:]
        self.filter_glob = self.format
        
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        from . import export_pet

        # save
        return export_pet.save(self, context)


# ImportGBin implements the operator for importing GBIN
class ImportGBin(bpy.types.Operator, ImportHelper):
    """Import from Pangya GBIN (.gbin, .sgbin, .aibin, .sbin)"""
    bl_idname = 'import.pangya_gbin'
    bl_label = 'Import Pangya GBIN'
    bl_options = {'UNDO'}

    filename_ext = ".gbin;.sgbin;.aibin"
    filter_glob: bpy.props.StringProperty(
        default="*.gbin;*.sgbin;*.aibin",
        options={'HIDDEN'},
    ) # pyright: ignore[reportInvalidTypeForm]

    load_base_element: bpy.props.BoolProperty(
        name="Load Base Element",
        description="Import base element(3d course) from gbin",
        default=True
    ) # pyright: ignore[reportInvalidTypeForm]

    load_elements: bpy.props.BoolProperty(
        name="Load Elements",
        description="Import elements from gbin",
        default=True
    ) # pyright: ignore[reportInvalidTypeForm]

    load_cameras: bpy.props.BoolProperty(
        name="Load Cameras",
        description="Import cameras from gbin",
        default=True
    ) # pyright: ignore[reportInvalidTypeForm]

    load_lights: bpy.props.BoolProperty(
        name="Load Lights",
        description="Import lights from gbin",
        default=True
    ) # pyright: ignore[reportInvalidTypeForm]

    load_sound_boxs: bpy.props.BoolProperty(
        name="Load SoundBoxs",
        description="Import sound boxs from gbin",
        default=True
    ) # pyright: ignore[reportInvalidTypeForm]

    load_nodes: bpy.props.BoolProperty(
        name="Load Nodes",
        description="Import nodes from gbin",
        default=True
    ) # pyright: ignore[reportInvalidTypeForm]

    load_new_elements: bpy.props.BoolProperty(
        name="Load New Elements",
        description="Import new elements from gbin",
        default=True
    ) # pyright: ignore[reportInvalidTypeForm]

    load_sbin: bpy.props.BoolProperty(
        name="Load SBIN",
        description="Import sbin from gbin",
        default=True
    ) # pyright: ignore[reportInvalidTypeForm]

    vertex_color_filter_enable: bpy.props.BoolProperty(
        name="Apply Vertex Color Filter",
        description="Apply Vertex Color Filter to base element",
        default=True
    ) # pyright: ignore[reportInvalidTypeForm]

    specular_material_filter_enable: bpy.props.BoolProperty(
        name="Apply Specular Material Filter",
        description="Apply Specular Material Filter if puppet have it",
        default=True
    ) # pyright: ignore[reportInvalidTypeForm]

    anim_enable: bpy.props.BoolProperty(
        name="Import Animation",
        description="Import animation if puppet have it",
        default=True
    ) # pyright: ignore[reportInvalidTypeForm]

    collisionBox_enable: bpy.props.BoolProperty(
        name="Import Collision Box",
        description="Import collision box if puppet have it",
        default=True
    ) # pyright: ignore[reportInvalidTypeForm]

    collisionBox_show: bpy.props.BoolProperty(
        name="Show Collision Box",
        description="Show collision box in render",
        default=False
    ) # pyright: ignore[reportInvalidTypeForm]

    def execute(self, context):
        from . import import_gbin

        # load
        return import_gbin.load(self, context, PangyaToBlenderMatrix())

# ExportGBin implements the operator for exporting to GBIN.
class ExportGBin(bpy.types.Operator, ExportHelper):
    """Export to Pangya GBIN (.gbin, .sgbin, .aibin, .sbin)"""
    bl_idname = 'export.pangya_gbin'
    bl_label = 'Export Pangya GBIN'

    filename_ext = ".gbin"
    filter_glob: bpy.props.StringProperty(
        default="*.gbin",
        options={'HIDDEN'},
        maxlen=255
    ) # pyright: ignore[reportInvalidTypeForm]

    def update_format(self, context):
        context.space_data.params.filter_glob = self.filter_glob = self.format
        context.space_data.operator.filename_ext = self.format[1:]
        bpy.ops.file.refresh()

    format: bpy.props.EnumProperty(
        name="Formato",
        description="Formato em que o GBIN vai ser salvo",
        items=(
            ("*.gbin", ".gbin", "GBIN completo"),
            ("*.sgbin", ".sgbin", "SGBIN extras shortgame"),
            ("*.aibin", ".aibin", "AIBIN node grandprix AI"),
            ("*.sbin", ".sbin", "SBIN precalculated ShadowMap")
        ),
        default="*.gbin",
        update=update_format
    ) # pyright: ignore[reportInvalidTypeForm]

    version: bpy.props.EnumProperty(
        name="Versão",
        description="Versão em que o GBIN vai ser salvo",
        items=(
            ("112", "112", "Versão suportada pela primeira até a quarta temporada do PangYa"),
            ("113", "113", "Versão suportada pela quinta até a sétima temporada do PangYa"),
            ("114", "114", "Versão suportada pela oitava até a nona temporada do PangYa"),
        ),
        default="114"
    ) # pyright: ignore[reportInvalidTypeForm]

    save_sbin: bpy.props.BoolProperty(
        name="Save sbin",
        description="save sbin from gbin",
        options={"HIDDEN"},
        default=False
    ) # pyright: ignore[reportInvalidTypeForm]

    sbin_version: bpy.props.EnumProperty(
        name="Versão",
        description="Versão em que o SBIN vai ser salvo",
        items=(
            ("0,0", "Beta", "Versão suportada pela primeira até a sexta temporada do PangYa"),
            ("1,0", "1.0", "Versão suportada pela sétima até a nona temporada do PangYa"),
        ),
        options={"HIDDEN"},
        default="1,0"
    ) # pyright: ignore[reportInvalidTypeForm]

    def draw(self, context):
        self.layout.use_property_split = True
        self.layout.use_property_decorate = False
        
        col = self.layout.column()
        col.prop(self, "format")

        if self.format in ("*.gbin", "*.sgbin", "*.aibin"):
            col.prop(self, "version")
        elif self.format == "*.sbin":
            col.prop(self, "sbin_version")

    def invoke(self, context, event):
        self.filename_ext = self.format[1:]
        self.filter_glob = self.format
        
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        from . import export_gbin

        # save
        return export_gbin.save(self, context, BlenderToPangyaMatrix())

# ExportSBin Panel Internal in ExportGBin
class FILE_BROWSER_PT_ExportSBinPanelInternal(bpy.types.Panel):
    """ExportSBinPanelInternal"""
    bl_space_type = "FILE_BROWSER"
    bl_region_type = "TOOL_PROPS"
    bl_label = "Save SBin"

    @classmethod
    def poll(cls, context):
        op = context.space_data.active_operator

        return op.bl_idname == "EXPORT_OT_pangya_gbin" and op.format == "*.gbin"
    
    def draw_header(self, context):
        self.layout.prop(
            context.space_data.active_operator,
            "save_sbin",
            text=""
        )

    def draw(self, context):
        layout = self.layout
        op = context.space_data.active_operator
        
        layout.active = op.save_sbin
        layout.use_property_split = True
        layout.use_property_decorate = False

        col = layout.column()
        col.prop(op, "sbin_version")


# Select Director Operator
class SelectDirectory(bpy.types.Operator):

    """Select directory to Pangya resources"""
    bl_idname = "select_dir.pangya_resource"
    bl_label = "Select directory Pangya resources"
    bl_options = {"REGISTER"}

    directory: bpy.props.StringProperty(
        name="Pangya resources folder",
        description="Pangya resources folder",
        subtype="DIR_PATH"
    ) # pyright: ignore[reportInvalidTypeForm]

    # filter folder
    filter_folder: bpy.props.BoolProperty(
        default=True,
        options={"HIDDEN"}
    ) # pyright: ignore[reportInvalidTypeForm]

    def execute(self, context):

        print("selected dir: ", self.directory)
        pangya_resource = context.scene.pangya_resources.add()
        pangya_resource.name = self.directory
        pangya_resource.directory = self.directory

        return {"FINISHED"}
    
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

class PangyaResourceItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Pangya Resource Item", default="Unknown") # pyright: ignore[reportInvalidTypeForm]
    directory: bpy.props.StringProperty(name="Pangya Resource Folder", default="") # pyright: ignore[reportInvalidTypeForm]

# Registration/Menu items
def menu_func_export(self, context):
    self.layout.operator(ExportPet.bl_idname, text="PangYa Model (.pet, .apet, .bpet, .mpet)")
    self.layout.operator(ExportGBin.bl_idname, text="PangYa GBIN (.gbin, .sgbin, .aibin, .sbin)")


def menu_func_import(self, context):
    self.layout.operator(ImportPet.bl_idname, text="PangYa Model (.pet, .apet, .bpet, .mpet)")
    self.layout.operator(ImportGBin.bl_idname, text="PangYa GBIN (.gbin, .sgbin, .aibin, .sbin)")

def menu_func_external_data(self, context):
    self.layout.operator(SelectDirectory.bl_idname, text="Seleciona um diretório de recursos do Pangya")

def register():
    bpy.utils.register_class(ImportPet)
    bpy.utils.register_class(ImportGBin)
    bpy.utils.register_class(ExportPet)
    bpy.utils.register_class(ExportGBin)
    bpy.utils.register_class(FILE_BROWSER_PT_ExportSBinPanelInternal)

    bpy.utils.register_class(SelectDirectory)
    bpy.utils.register_class(PangyaResourceItem)

    bpy.utils.register_class(ReloadAddonOperator)
    reigster_hotkey_reload_addon()

    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

    bpy.types.TOPBAR_MT_file_external_data.append(menu_func_external_data)

    bpy.types.Scene.pangya_resources = bpy.props.CollectionProperty(type=PangyaResourceItem)
    
    # current draw armature props
    bpy.types.Mesh.current_draw_armature = bpy.props.PointerProperty(type=bpy.types.Object)

    def setOrientationFlag(self, value):
        self["orientation_flag"] = value

    def getMatrixLocalPangya(self):
        if bpy.app.version >= (5, 0, 0):
            return Matrix(tuple(tuple(self.get("matrix_local_pangya", Matrix.Identity(4))[row + col * 4] for col in range(4)) for row in range(4)))
        
        return self.get("matrix_local_pangya", Matrix.Identity(4))

    for cls in [bpy.types.EditBone, bpy.types.Bone]:
        cls.matrix_local_pangya = bpy.props.FloatVectorProperty(
            name="Matrix Local PangYa",
            subtype="MATRIX",
            precision=3,
            step=1,
            options={"HIDDEN"},
            size=[4,4],
            default=Matrix.Identity(4),
            get= getMatrixLocalPangya
        )
        cls.orientation_flag = bpy.props.FloatProperty(
            name="Orientation Flag",
            precision=3,
            step=1,
            default=-1,
            get=lambda self: self.get("orientation_flag", -1),
            set= setOrientationFlag
        )
    
    # Orientation Flag PoseBone
    bpy.types.PoseBone.orientation_flag = bpy.props.FloatProperty(
        name="Orientation Flag",
        precision=3,
        step=1,
        default=-1,
        get=lambda self: self.get("orientation_flag", -1),
        set= setOrientationFlag
    )

def unregister():
    bpy.utils.unregister_class(ImportPet)
    bpy.utils.unregister_class(ImportGBin)
    bpy.utils.unregister_class(ExportPet)
    bpy.utils.unregister_class(ExportGBin)
    bpy.utils.unregister_class(FILE_BROWSER_PT_ExportSBinPanelInternal)

    bpy.utils.unregister_class(SelectDirectory)
    bpy.utils.unregister_class(PangyaResourceItem)

    bpy.utils.unregister_class(ReloadAddonOperator)
    unregister_hotkey_reload_addon()

    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

    bpy.types.TOPBAR_MT_file_external_data.remove(menu_func_external_data)

    del bpy.types.Scene.pangya_resources
    
    # current draw armature props
    del bpy.types.Mesh.current_draw_armature

    for cls in [bpy.types.EditBone, bpy.types.Bone]:
        del cls.matrix_local_pangya
        del cls.orientation_flag

if __name__ == "__main__":
    register()
