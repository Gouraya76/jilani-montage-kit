import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
s=bpy.context.scene; s.render.engine='CYCLES'; s.cycles.device='CPU'; s.cycles.samples=32; s.cycles.use_denoising=False; s.render.resolution_x=540; s.render.resolution_y=960
bpy.ops.object.text_add(location=(0,0,0)); t=bpy.context.object; t.data.body="C1 NEWS"; t.data.extrude=0.15; t.data.bevel_depth=0.02; t.data.align_x='CENTER'
m=bpy.data.materials.new("r"); m.use_nodes=True; m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value=(0.9,0.1,0.12,1); m.node_tree.nodes["Principled BSDF"].inputs["Metallic"].default_value=0.6; t.data.materials.append(m)
t.rotation_euler=(1.2,0,0.3)
bpy.ops.object.camera_add(location=(0,-6,1.2),rotation=(1.42,0,0)); s.camera=bpy.context.object
bpy.ops.object.light_add(type='AREA',location=(2,-3,4)); bpy.context.object.data.energy=800
w=bpy.data.worlds.new("w"); s.world=w; w.use_nodes=True; w.node_tree.nodes["Background"].inputs[0].default_value=(0.02,0.02,0.03,1)
s.render.filepath='/workspace/b3d/test.png'; bpy.ops.render.render(write_still=True)
