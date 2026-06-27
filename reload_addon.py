# Copyright 2023-2026 Acrisio Filho

import importlib, sys, bpy, os, time # pyright: ignore[reportMissingImports]

# peice of code from valve benlder tools, to reload scripts(addon)
# Python doesn't reload package sub-modules at the same time as __init__.py!
def reload_addon_modules():

    addon_dir = os.path.dirname(os.path.realpath(__file__))
    addon_name = os.path.basename(addon_dir)

    print('Reload Addon and your modules: %r' % addon_name)

    time1 = time.process_time()

    for filename in [ f for f in os.listdir(addon_dir) if f.endswith(".py") and f not in ['__init__.py', os.path.basename(__file__)] ]:
        module_name = "{}.{}".format(addon_name,filename[:-3])
        module = sys.modules.get(module_name)
        if module:
            importlib.reload(module)
        else:
            importlib.import_module(module_name)

    print('Reloaded in %.4f sec.' % (time.process_time() - time1))

# Reload Addon Operator
class ReloadAddonOperator(bpy.types.Operator):

    """Reload Addon Operator"""
    bl_idname = "addon.reload"
    bl_label = "Reload Addon"

    def execute(self, context):

        reload_addon_modules()

        return {"FINISHED"}

def reigster_hotkey_reload_addon():
    km = bpy.context.window_manager.keyconfigs.addon.keymaps.new(name="Window", space_type="EMPTY")
    kmi = km.keymap_items.new(ReloadAddonOperator.bl_idname, type='R', value='PRESS', ctrl=True, shift=True)
    kmi.active = True

def unregister_hotkey_reload_addon():
    for km in bpy.context.window_manager.keyconfigs.addon.keymaps:
        for kmi in km.keymap_items:
            if kmi.idname == ReloadAddonOperator.bl_idname:
                km.keymap_items.remove(kmi)