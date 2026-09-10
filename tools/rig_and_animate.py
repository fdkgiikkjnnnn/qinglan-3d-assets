import bpy, math, os
from mathutils import Vector

SRC = "models/hero01/hero01_tpose_shape.glb"
OUT = "models/hero01/hero01_rigged_animated.glb"
SWORD_OUT = "models/sword/sword01.glb"
os.makedirs(os.path.dirname(OUT), exist_ok=True)
os.makedirs(os.path.dirname(SWORD_OUT), exist_ok=True)

# reset
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
bpy.ops.import_scene.gltf(filepath=SRC)
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
if not meshes:
    raise RuntimeError("No mesh imported")
# join meshes
bpy.ops.object.select_all(action='DESELECT')
for o in meshes:o.select_set(True)
bpy.context.view_layer.objects.active=meshes[0]
if len(meshes)>1:bpy.ops.object.join()
mesh=bpy.context.view_layer.objects.active
mesh.name="Hero01Mesh"
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

# bounds
corners=[mesh.matrix_world @ Vector(c) for c in mesh.bound_box]
minx=min(v.x for v in corners); maxx=max(v.x for v in corners)
miny=min(v.y for v in corners); maxy=max(v.y for v in corners)
minz=min(v.z for v in corners); maxz=max(v.z for v in corners)
cx=(minx+maxx)/2; cy=(miny+maxy)/2
w=maxx-minx; h=maxz-minz; d=maxy-miny
print("bounds",minx,maxx,miny,maxy,minz,maxz,"w/h/d",w,h,d)

# Project the matching T-pose reference onto the generated mesh as a lightweight color texture.
# This is a real mesh texture, not a 2D sprite: UVs live on the 3D surface and export inside GLB.
uv = mesh.data.uv_layers.get("Hero01UV") or mesh.data.uv_layers.new(name="Hero01UV")
for loop in mesh.data.loops:
    co = mesh.data.vertices[loop.vertex_index].co
    u = max(0.0, min(1.0, (co.x-minx)/(w if w else 1.0)))
    v = max(0.0, min(1.0, (co.z-minz)/(h if h else 1.0)))
    uv.data[loop.index].uv = (u, v)
hero_mat=bpy.data.materials.new("Hero01ProjectedColor")
hero_mat.use_nodes=True
bsdf=hero_mat.node_tree.nodes.get("Principled BSDF")
bsdf.inputs["Roughness"].default_value=.72
img=bpy.data.images.load("refs/hero01_tpose_ref.png")
tex=hero_mat.node_tree.nodes.new("ShaderNodeTexImage"); tex.image=img; tex.interpolation='Linear'
hero_mat.node_tree.links.new(tex.outputs["Color"],bsdf.inputs["Base Color"])
mesh.data.materials.clear(); mesh.data.materials.append(hero_mat)

# armature
bpy.ops.object.armature_add(enter_editmode=True, location=(0,0,0))
arm=bpy.context.object
arm.name="Hero01Rig"
arm.data.name="Hero01Armature"
for b in list(arm.data.edit_bones): arm.data.edit_bones.remove(b)

def eb(name, head, tail, parent=None):
    b=arm.data.edit_bones.new(name)
    b.head=head; b.tail=tail
    if parent: b.parent=arm.data.edit_bones[parent]
    return b

z=lambda f:minz+h*f
eb("Hips",(cx,cy,z(.45)),(cx,cy,z(.54)))
eb("Spine",(cx,cy,z(.54)),(cx,cy,z(.66)),"Hips")
eb("Chest",(cx,cy,z(.66)),(cx,cy,z(.76)),"Spine")
eb("Neck",(cx,cy,z(.76)),(cx,cy,z(.83)),"Chest")
eb("Head",(cx,cy,z(.83)),(cx,cy,z(.95)),"Neck")

shoulder_z=z(.75)
# arms roughly horizontal for T pose
for side,sgn in [("Left",1),("Right",-1)]:
    x0=cx+sgn*w*.10; x1=cx+sgn*w*.27; x2=cx+sgn*w*.41; x3=cx+sgn*w*.48
    eb(side+"UpperArm",(x0,cy,shoulder_z),(x1,cy,shoulder_z),"Chest")
    eb(side+"LowerArm",(x1,cy,shoulder_z),(x2,cy,shoulder_z),side+"UpperArm")
    eb(side+"Hand",(x2,cy,shoulder_z),(x3,cy,shoulder_z),side+"LowerArm")

for side,sgn in [("Left",1),("Right",-1)]:
    x=cx+sgn*w*.075
    eb(side+"UpperLeg",(x,cy,z(.47)),(x,cy,z(.27)),"Hips")
    eb(side+"LowerLeg",(x,cy,z(.27)),(x,cy,z(.07)),side+"UpperLeg")
    eb(side+"Foot",(x,cy,z(.07)),(x,cy-d*.18,z(.035)),side+"LowerLeg")

bpy.ops.object.mode_set(mode='OBJECT')

# auto weights; fallback to armature modifier if weighting fails
bpy.ops.object.select_all(action='DESELECT')
mesh.select_set(True); arm.select_set(True)
bpy.context.view_layer.objects.active=arm
try:
    bpy.ops.object.parent_set(type='ARMATURE_AUTO')
    print("automatic weights ok")
except Exception as e:
    print("automatic weights failed",e)
    mesh.parent=arm
    mod=mesh.modifiers.new(name="Armature",type='ARMATURE'); mod.object=arm
    # simple region weights fallback
    names=[b.name for b in arm.data.bones if b.use_deform]
    groups={n:mesh.vertex_groups.get(n) or mesh.vertex_groups.new(name=n) for n in names}
    def add(group, idx, wt=1.0): groups[group].add([idx],wt,'REPLACE')
    for v in mesh.data.vertices:
        p=v.co
        f=(p.z-minz)/h
        xr=(p.x-cx)/(w if w else 1)
        if f<.08: add("LeftFoot" if xr>=0 else "RightFoot",v.index)
        elif f<.27: add("LeftLowerLeg" if xr>=0 else "RightLowerLeg",v.index)
        elif f<.48: add("LeftUpperLeg" if xr>=0 else "RightUpperLeg",v.index)
        elif abs(xr)>.34 and f>.66: add(("LeftHand" if xr>=0 else "RightHand"),v.index)
        elif abs(xr)>.24 and f>.66: add(("LeftLowerArm" if xr>=0 else "RightLowerArm"),v.index)
        elif abs(xr)>.12 and f>.64: add(("LeftUpperArm" if xr>=0 else "RightUpperArm"),v.index)
        elif f>.84: add("Head",v.index)
        elif f>.76: add("Neck",v.index)
        elif f>.65: add("Chest",v.index)
        elif f>.54: add("Spine",v.index)
        else: add("Hips",v.index)

# sword asset
def mat(name, base, metallic=.0, rough=.5):
    m=bpy.data.materials.new(name); m.diffuse_color=(*base,1); m.metallic=metallic; m.roughness=rough; return m
silver=mat("BladeSilver",(0.55,0.62,0.68),.9,.22)
bronze=mat("GuardBronze",(0.28,0.20,0.12),.65,.32)
teal=mat("HiltTeal",(0.05,0.18,0.17),.2,.45)

sword=[]
# blade
bpy.ops.mesh.primitive_cube_add(location=(0,0,0))
blade=bpy.context.object; blade.name="Sword_Blade"; blade.dimensions=(0.055,0.018,1.08); bpy.ops.object.transform_apply(location=False,rotation=False,scale=True); blade.data.materials.append(silver); sword.append(blade)
# tip cone
bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=.04, radius2=0, depth=.18, location=(0,0,-.63), rotation=(0,0,math.radians(45)))
tip=bpy.context.object; tip.name="Sword_Tip"; tip.data.materials.append(silver); sword.append(tip)
# guard
bpy.ops.mesh.primitive_cube_add(location=(0,0,.58))
guard=bpy.context.object; guard.name="Sword_Guard"; guard.dimensions=(.28,.05,.04); bpy.ops.object.transform_apply(location=False,rotation=False,scale=True); guard.data.materials.append(bronze); sword.append(guard)
# grip
bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=.035, depth=.24, location=(0,0,.72))
grip=bpy.context.object; grip.name="Sword_Grip"; grip.data.materials.append(teal); sword.append(grip)
# pommel
bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=.055, location=(0,0,.87))
pom=bpy.context.object; pom.name="Sword_Pommel"; pom.data.materials.append(bronze); sword.append(pom)

# export sword independently
bpy.ops.object.select_all(action='DESELECT')
for o in sword:o.select_set(True)
bpy.context.view_layer.objects.active=blade
bpy.ops.export_scene.gltf(filepath=SWORD_OUT, export_format='GLB', use_selection=True)

# parent sword to right hand
for o in sword:
    o.parent=arm; o.parent_type='BONE'; o.parent_bone='RightHand'
    o.location=(0.05,0,-0.70)
    o.rotation_euler=(math.radians(90),0,math.radians(90))

# animation helpers
scene=bpy.context.scene
scene.render.fps=30
def clear_pose():
    for pb in arm.pose.bones:
        pb.rotation_mode='XYZ'; pb.rotation_euler=(0,0,0); pb.location=(0,0,0); pb.scale=(1,1,1)
def key(frame, rotations=None, locs=None):
    scene.frame_set(frame)
    rotations=rotations or {}; locs=locs or {}
    for n,vals in rotations.items():
        pb=arm.pose.bones.get(n)
        if pb:
            pb.rotation_euler=tuple(math.radians(v) for v in vals)
            pb.keyframe_insert("rotation_euler",frame=frame)
    for n,vals in locs.items():
        pb=arm.pose.bones.get(n)
        if pb:
            pb.location=vals; pb.keyframe_insert("location",frame=frame)

def make_action(name, end, frames):
    clear_pose()
    act=bpy.data.actions.new(name); arm.animation_data_create(); arm.animation_data.action=act
    for fr,rots,locs in frames: key(fr,rots,locs)
    for fc in act.fcurves:
        for kp in fc.keyframe_points: kp.interpolation='BEZIER'
    track=arm.animation_data.nla_tracks.new(); track.name=name
    strip=track.strips.new(name,1,act); strip.action_frame_start=1; strip.action_frame_end=end
    arm.animation_data.action=None
    return act

idle=[
(1,{"Chest":(0,0,-1.5),"LeftUpperArm":(-68,0,-4),"RightUpperArm":(-68,0,4),"LeftLowerArm":(-8,0,0),"RightLowerArm":(-8,0,0)},{"Hips":(0,0,0)}),
(30,{"Chest":(1.2,0,1.5),"LeftUpperArm":(-70,0,-5),"RightUpperArm":(-70,0,5),"LeftLowerArm":(-10,0,0),"RightLowerArm":(-10,0,0)},{"Hips":(0,0,.012)}),
(60,{"Chest":(0,0,-1.5),"LeftUpperArm":(-68,0,-4),"RightUpperArm":(-68,0,4),"LeftLowerArm":(-8,0,0),"RightLowerArm":(-8,0,0)},{"Hips":(0,0,0)})]
run=[
(1,{"LeftUpperLeg":(30,0,0),"RightUpperLeg":(-30,0,0),"LeftLowerLeg":(-18,0,0),"RightLowerLeg":(35,0,0),"LeftUpperArm":(-55,0,-25),"RightUpperArm":(-80,0,25),"Chest":(5,0,0)},{"Hips":(0,0,.03)}),
(8,{"LeftUpperLeg":(0,0,0),"RightUpperLeg":(0,0,0),"LeftLowerLeg":(25,0,0),"RightLowerLeg":(25,0,0),"LeftUpperArm":(-68,0,-8),"RightUpperArm":(-68,0,8)},{"Hips":(0,0,0)}),
(15,{"LeftUpperLeg":(-30,0,0),"RightUpperLeg":(30,0,0),"LeftLowerLeg":(35,0,0),"RightLowerLeg":(-18,0,0),"LeftUpperArm":(-80,0,25),"RightUpperArm":(-55,0,-25),"Chest":(5,0,0)},{"Hips":(0,0,.03)}),
(22,{"LeftUpperLeg":(0,0,0),"RightUpperLeg":(0,0,0),"LeftLowerLeg":(25,0,0),"RightLowerLeg":(25,0,0),"LeftUpperArm":(-68,0,-8),"RightUpperArm":(-68,0,8)},{"Hips":(0,0,0)}),
(29,{"LeftUpperLeg":(30,0,0),"RightUpperLeg":(-30,0,0),"LeftLowerLeg":(-18,0,0),"RightLowerLeg":(35,0,0),"LeftUpperArm":(-55,0,-25),"RightUpperArm":(-80,0,25),"Chest":(5,0,0)},{"Hips":(0,0,.03)})]
attack=[
(1,{"LeftUpperArm":(-68,0,-4),"RightUpperArm":(-55,-15,20),"RightLowerArm":(-20,0,-20),"Chest":(0,0,-8)},{}),
(8,{"LeftUpperArm":(-68,0,-4),"RightUpperArm":(-20,-35,45),"RightLowerArm":(-35,0,-35),"Chest":(0,0,-20)},{}),
(14,{"LeftUpperArm":(-68,0,-4),"RightUpperArm":(-55,25,-50),"RightLowerArm":(10,0,15),"Chest":(5,0,32),"Hips":(0,0,10)},{}),
(22,{"LeftUpperArm":(-68,0,-4),"RightUpperArm":(-65,-10,15),"RightLowerArm":(-12,0,-10),"Chest":(0,0,-5)},{}),
(30,{"LeftUpperArm":(-68,0,-4),"RightUpperArm":(-68,0,4),"RightLowerArm":(-8,0,0),"Chest":(0,0,0)}, {})]
make_action("Idle",60,idle)
make_action("Run",29,run)
make_action("Attack",30,attack)

# export hero + armature + sword with all NLA animations
bpy.ops.object.select_all(action='DESELECT')
mesh.select_set(True); arm.select_set(True)
for o in sword:o.select_set(True)
bpy.context.view_layer.objects.active=arm
bpy.ops.export_scene.gltf(
    filepath=OUT, export_format='GLB', use_selection=True,
    export_animations=True, export_nla_strips=True,
    export_skins=True, export_morph=False
)
print("exported",OUT,os.path.getsize(OUT),SWORD_OUT,os.path.getsize(SWORD_OUT))
