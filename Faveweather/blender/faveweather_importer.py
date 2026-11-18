bl_info = {
    "name": "FaveWeather",
    "author": "FaveWeather Contributors",
    "version": (0, 3, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar (N) > FaveWeather  |  File > Import > FaveWeather Sky",
    "description": "Make and edit skies and volumetric clouds inside Blender, or import a sky from the FaveWeather app",
    "category": "Lighting",
}

# MIT License — part of FaveWeather

import json
import math
import os
import random
import re
import zipfile

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper
from mathutils import Euler, Vector

# ---------------------------------------------------------------------------
#  i18n (Japanese UI when Blender's interface language is Japanese)
# ---------------------------------------------------------------------------
JA = {
    "Sky": "空", "Make Sky": "空を作る", "Sun Elevation": "太陽の高さ", "Sun Azimuth": "太陽の方位",
    "Haze": "かすみ", "Air": "空気の濃さ", "Ozone": "オゾン", "Sky Strength": "空の明るさ", "Sun Strength": "太陽の強さ",
    "Clear": "快晴", "Morning": "朝", "Sunset": "夕焼け", "Twilight": "夕暮れ",
    "Clouds": "雲", "Add Cloud": "雲を置く", "Scatter Clouds": "雲を散らす", "Count": "数",
    "Selected Cloud": "選んでいる雲", "Color": "色", "Density": "濃さ", "Puffiness": "もこもこ", "Flatness": "平たさ",
    "New Shape": "形を変える", "Size (m)": "大きさ (m)", "Delete Clouds": "雲を全部消す",
    "Import from App": "アプリから読み込む", "Import Sky (.zip / .hdr)": "空を読み込む (.zip / .hdr)",
    "Tip: move / scale clouds with G / S like any object": "ヒント：雲はふつうの物体と同じく G で移動、S で拡大縮小",
    "Small puff": "わた雲", "Cumulus": "積雲", "Tower": "入道雲", "Stratocumulus": "層積雲",
    "Lenticular": "レンズ雲", "Rain cloud": "雨雲", "My shape": "マイ形",
    "Detail": "もこもこの細かさ", "Render": "レンダリング", "Realistic Render Setup": "リアルな描画設定にする",
    "Draft": "下書き", "High": "高品質", "Ultra": "最高品質", "Render 360° HDRI": "360° HDRI を描画",
    "Resolution": "解像度", "Import Cloud Shapes (.zip / .json)": "雲の形を読み込む (.zip / .json)",
    "Render with F12. Ultra takes time but looks the most real": "F12 で描画。最高品質は時間がかかるぶん一番リアル",
    "HDRI for Unity / Unreal / Twinmotion skyboxes": "Unity・Unreal・Twinmotion のスカイボックス用 HDRI",
}


def T(s):
    try:
        if bpy.context.preferences.view.language.startswith("ja"):
            return JA.get(s, s)
    except Exception:
        pass
    return s


# ---------------------------------------------------------------------------
#  Sky (Blender's physical sky texture + a matching Sun lamp)
# ---------------------------------------------------------------------------
SUN_NAME = "FaveWeather Sun"


def _sky_type():
    items = [e.identifier for e in bpy.types.ShaderNodeTexSky.bl_rna.properties["sky_type"].enum_items]
    for k in ("MULTIPLE_SCATTERING", "SINGLE_SCATTERING", "NISHITA"):
        if k in items:
            return k
    return items[0]


def _sky_nodes(scene, create=False):
    world = scene.world
    if world is None:
        if not create:
            return None, None
        world = bpy.data.worlds.new("FaveWeather")
        scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    sky = nt.nodes.get("FW Sky")
    bg = nt.nodes.get("FW Background")
    if (sky is None or bg is None) and create:
        nt.nodes.clear()
        sky = nt.nodes.new("ShaderNodeTexSky"); sky.name = "FW Sky"; sky.location = (-400, 0)
        sky.sky_type = _sky_type()
        bg = nt.nodes.new("ShaderNodeBackground"); bg.name = "FW Background"; bg.location = (-150, 0)
        out = nt.nodes.new("ShaderNodeOutputWorld"); out.location = (100, 0)
        nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
        nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    return sky, bg


def _sun_vector(el_deg, az_deg):
    """FaveWeather azimuth: 0 = north (+Y), 90 = east (+X)."""
    el, az = math.radians(el_deg), math.radians(az_deg)
    return Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))


def update_sky(self=None, context=None):
    scene = (context or bpy.context).scene
    p = scene.fw_sky
    sky, bg = _sky_nodes(scene)
    if sky is not None:
        sky.sun_elevation = math.radians(p.sun_elevation)
        # measured: Blender's sky rotation runs from +Y (north) towards +X (east), like FaveWeather's azimuth
        sky.sun_rotation = math.radians(p.sun_azimuth)
        if hasattr(sky, "aerosol_density"):
            sky.aerosol_density = p.haze
        elif hasattr(sky, "dust_density"):
            sky.dust_density = p.haze
        sky.air_density = p.air
        sky.ozone_density = p.ozone
        sky.sun_disc = True
        bg.inputs["Strength"].default_value = p.sky_strength
    sun = bpy.data.objects.get(SUN_NAME)
    if sun is not None:
        d = _sun_vector(p.sun_elevation, p.sun_azimuth)
        sun.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
        sun.location = d * 30.0
        sun.data.energy = p.sun_strength * max(0.0, min(1.0, (p.sun_elevation + 1.0) / 4.0))
        warm = max(0.0, min(1.0, p.sun_elevation / 15.0))
        sun.data.color = (1.0, 0.55 + 0.42 * warm, 0.30 + 0.62 * warm)


class FWSkyProps(bpy.types.PropertyGroup):
    sun_elevation: FloatProperty(name="Sun Elevation", default=35.0, min=-10.0, max=90.0, subtype="NONE", update=update_sky)
    sun_azimuth: FloatProperty(name="Sun Azimuth", default=200.0, min=0.0, max=360.0, update=update_sky)
    haze: FloatProperty(name="Haze", default=1.0, min=0.0, max=10.0, update=update_sky)
    air: FloatProperty(name="Air", default=1.0, min=0.0, max=10.0, update=update_sky)
    ozone: FloatProperty(name="Ozone", default=1.0, min=0.0, max=10.0, update=update_sky)
    sky_strength: FloatProperty(name="Sky Strength", default=0.25, min=0.0, soft_max=2.0, update=update_sky)
    sun_strength: FloatProperty(name="Sun Strength", default=4.0, min=0.0, soft_max=20.0, update=update_sky)
    cloud_type: EnumProperty(name="Cloud", items=[
        ("puff", "Small puff", ""), ("cumulus", "Cumulus", ""), ("tower", "Tower", ""),
        ("sheet", "Stratocumulus", ""), ("lens", "Lenticular", ""), ("rain", "Rain cloud", "")], default="cumulus")
    scatter_count: IntProperty(name="Count", default=12, min=1, max=80)
    quality: EnumProperty(name="Quality", items=[("draft", "Draft", ""), ("high", "High", ""), ("ultra", "Ultra", "")], default="high")
    hdri_res: EnumProperty(name="Resolution", items=[("2048", "2K", ""), ("4096", "4K", ""), ("8192", "8K", "")], default="4096")


def make_sky(context):
    scene = context.scene
    _sky_nodes(scene, create=True)
    sun = bpy.data.objects.get(SUN_NAME)
    if sun is None:
        light = bpy.data.lights.new(SUN_NAME, type="SUN")
        light.angle = math.radians(0.53)
        sun = bpy.data.objects.new(SUN_NAME, light)
        scene.collection.objects.link(sun)
    update_sky(None, context)


SKY_PRESETS = {
    "clear": dict(sun_elevation=45.0, sun_azimuth=190.0, haze=1.0),
    "morning": dict(sun_elevation=8.0, sun_azimuth=95.0, haze=2.0),
    "sunset": dict(sun_elevation=1.5, sun_azimuth=255.0, haze=3.0),
    "twilight": dict(sun_elevation=-3.0, sun_azimuth=260.0, haze=1.5),
}

# ---------------------------------------------------------------------------
#  Realistic volumetric clouds
#  Each cloud is a cluster of spheres (big lobes -> smaller and smaller billows, like real
#  cumulus). Geometry Nodes turn the spheres into a volume; a shared material erodes the edges
#  with noise and scatters light with a real cloud-droplet (Mie) phase function. Render with
#  Cycles and many volume bounces to get the bright, soft, "real photo" look.
# ---------------------------------------------------------------------------
CLOUD_TYPES = {
    #           size (m)                base (m)  detail (puff)
    "puff":    dict(size=(1500, 1200, 1100), base=1400, puff=0.55),
    "cumulus": dict(size=(4200, 3400, 3000), base=1200, puff=0.60),
    "tower":   dict(size=(6200, 5600, 8200), base=1200, puff=0.65),
    "sheet":   dict(size=(6500, 4500, 650),  base=1800, puff=0.50),
    "lens":    dict(size=(4800, 1900, 750),  base=3800, puff=0.12),
    "rain":    dict(size=(9000, 7000, 2600), base=700,  puff=0.35),
}
TYPE_LABEL = dict(puff="Small puff", cumulus="Cumulus", tower="Tower", sheet="Stratocumulus", lens="Lenticular", rain="Rain cloud", custom="My shape")
MAT_NAME = "FaveWeather Cloud Volume"
GN_NAME = "FaveWeather Cloud Volume"
BASE_DENSITY = 0.07   # 1/m: real cumulus has a mean free path of roughly 10-20 m


def _children(rnd, level, S, top_limit, counts, ratio=(0.42, 0.62), up_bias=0.6, keep_base=True):
    for lv, k in enumerate(counts):
        nxt = []
        for (x, y, z, r) in level:
            for _ in range(k):
                th = rnd.uniform(0, 2 * math.pi)
                up = rnd.uniform(0.05, 1.0) ** up_bias
                s = math.sqrt(max(0.0, 1 - up * up))
                cr = r * rnd.uniform(*ratio)
                cx, cy, cz = x + math.cos(th) * s * r * 0.78, y + math.sin(th) * s * r * 0.78, z + up * r * 0.78
                if keep_base and cz - cr < -r * 0.1:
                    continue
                if cz + cr > top_limit:
                    cr *= 0.6
                nxt.append((cx, cy, cz, cr))
        S += nxt
        level = nxt
    return S


def gen_spheres(ctype, size, seed, prof=None):
    """Sphere cluster in local metres; the cloud base sits at z = 0."""
    rnd = random.Random(seed)
    W, D, H = size
    S = []
    if ctype == "custom" and prof:
        n = len(prof)
        step = W / n
        for i, (b, t) in enumerate(prof):
            th = (t - b) * H
            if th < H * 0.02:
                continue
            x = -W / 2 + (i + 0.5) * step
            r = max(step * 0.9, th * 0.5)
            zc = b * H + th * 0.5
            dd = D * (0.3 + 0.7 * math.sqrt(max(0.0, (t - b))))
            for j in range(max(1, int(dd / (r * 1.2)))):
                y = (j - (int(dd / (r * 1.2)) - 1) / 2) * r * 1.1 + rnd.uniform(-0.15, 0.15) * r
                S.append((x + rnd.uniform(-0.2, 0.2) * step, y, max(r * 0.5, zc), r * rnd.uniform(0.85, 1.05)))
        top = max((t for b, t in prof), default=1) * H
        return _children(rnd, list(S), S, top * 1.05, (3, 3, 2))
    if ctype == "lens":
        n = 26
        for i in range(n):
            u = -1 + 2 * (i + 0.5) / n
            r = H * 0.5 * math.sqrt(max(0.02, 1 - u * u)) + 20
            for v in (-0.35, 0.0, 0.35):
                w = math.sqrt(max(0.0, 1 - u * u))
                S.append((u * W / 2 * 0.95, v * D / 2 * w, H * 0.5, r * (0.9 if v else 1.0)))
        return S
    if ctype == "sheet":
        cell = H * 1.1
        nx, ny = int(W / cell), int(D / cell)
        for i in range(nx):
            for j in range(ny):
                if rnd.random() < 0.18:
                    continue
                x = -W / 2 + (i + 0.5) * cell + rnd.uniform(-0.3, 0.3) * cell
                y = -D / 2 + (j + 0.5) * cell + rnd.uniform(-0.3, 0.3) * cell
                if (2 * x / W) ** 2 + (2 * y / D) ** 2 > 1:
                    continue
                r = H * rnd.uniform(0.45, 0.7)
                S.append((x, y, r * 0.6, r))
        return _children(rnd, list(S), S, H * 1.3, (3, 2), up_bias=0.8)
    if ctype == "tower":
        # towering cumulus: a broad base that narrows upward, every level a ring of lobes
        R0 = W * 0.19
        z = R0 * 0.6
        while z < H - R0 * 0.5:
            k = z / H
            r = R0 * (1.0 - 0.3 * k) * rnd.uniform(0.9, 1.1)
            Wz = W / 2 * (0.72 + 0.28 * math.sin(math.pi * min(1.0, k * 1.1))) * (1.0 - 0.75 * max(0.0, (k - 0.78) / 0.22) ** 2)
            ring = max(0.0, Wz - r)
            n = max(1, int(2 * math.pi * ring / (r * 1.1)))
            a0 = rnd.uniform(0, 2 * math.pi)
            for i in range(n):
                a = a0 + 2 * math.pi * i / n + rnd.uniform(-0.2, 0.2)
                rr = ring * rnd.uniform(0.7, 1.0)
                S.append((math.cos(a) * rr, math.sin(a) * rr * D / W, z + rnd.uniform(-0.15, 0.15) * r, r * rnd.uniform(0.85, 1.05)))
            S.append((rnd.uniform(-0.1, 0.1) * W, rnd.uniform(-0.1, 0.1) * D, z, r * 1.1))
            z += r * 0.8
        return _children(rnd, list(S), S, H * 1.03, (2, 2), ratio=(0.5, 0.68), up_bias=0.35)
    # cumulus-like (puff / cumulus / rain)
    R0 = H * (0.32 if ctype != "rain" else 0.42)
    n0 = max(3, int(W * D / (R0 * R0 * 2.2)))
    for _ in range(n0):
        a = rnd.uniform(0, 2 * math.pi); r = math.sqrt(rnd.random())
        x, y = math.cos(a) * r * (W / 2 - R0 * 0.6), math.sin(a) * r * (D / 2 - R0 * 0.6)
        edge = 1 - r * r
        rad = R0 * (0.7 + 0.4 * rnd.random()) * (0.75 + 0.35 * edge)
        z = rad * 0.55 + (edge * H * 0.18 * rnd.random() if ctype != "rain" else 0)
        S.append((x, y, z, rad))
    counts = (4, 3, 3, 2) if ctype == "cumulus" else ((3, 3, 2) if ctype == "puff" else (3, 2, 2))
    return _children(rnd, list(S), S, H * 1.05, counts, up_bias=(0.6 if ctype != "rain" else 1.2))


def _iface_id(ng, name):
    for it in ng.interface.items_tree:
        if getattr(it, "name", None) == name and getattr(it, "in_out", "") == "INPUT":
            return it.identifier
    return None


def cloud_gn_group():
    ng = bpy.data.node_groups.get(GN_NAME)
    if ng is not None:
        return ng
    ng = bpy.data.node_groups.new(GN_NAME, "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    vs = ng.interface.new_socket("Voxel Size", in_out="INPUT", socket_type="NodeSocketFloat")
    vs.default_value = 14.0
    vs.min_value = 2.0
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = ng.nodes, ng.links.new
    gi = N.new("NodeGroupInput"); gi.location = (-800, 0)
    go = N.new("NodeGroupOutput"); go.location = (900, 0)
    na = N.new("GeometryNodeInputNamedAttribute"); na.location = (-800, -200)
    na.data_type = "FLOAT"; na.inputs["Name"].default_value = "fw_r"
    m2p = N.new("GeometryNodeMeshToPoints"); m2p.location = (-550, 0)
    L(gi.outputs[0], m2p.inputs["Mesh"]); L(na.outputs[0], m2p.inputs["Radius"])
    p2v = N.new("GeometryNodePointsToVolume"); p2v.location = (-300, 0)
    L(m2p.outputs[0], p2v.inputs["Points"]); L(na.outputs[0], p2v.inputs["Radius"])
    p2v.inputs["Density"].default_value = 1.0
    rm = p2v.inputs.get("Resolution Mode")
    if rm is not None:
        rm.default_value = "Size"
    else:
        p2v.resolution_mode = "VOXEL_SIZE"
    L(gi.outputs[1], p2v.inputs["Voxel Size"])
    out = p2v.outputs[0]
    if hasattr(bpy.types, "GeometryNodeGridMean"):
        # Blender 5: soften the voxel edges a little so the noise erosion has a gradient to bite on
        gg = N.new("GeometryNodeGetNamedGrid"); gg.location = (-50, 0)
        gg.data_type = "FLOAT"; gg.inputs["Name"].default_value = "density"
        if "Remove" in gg.inputs:
            gg.inputs["Remove"].default_value = True
        L(out, gg.inputs["Volume"])
        gm = N.new("GeometryNodeGridMean"); gm.location = (200, -150)
        gm.data_type = "FLOAT"; gm.inputs["Width"].default_value = 1; gm.inputs["Iterations"].default_value = 1
        L(gg.outputs["Grid"], gm.inputs["Grid"])
        sg = N.new("GeometryNodeStoreNamedGrid"); sg.location = (450, 0)
        sg.data_type = "FLOAT"; sg.inputs["Name"].default_value = "density"
        L(gg.outputs["Volume"], sg.inputs["Volume"]); L(gm.outputs["Grid"], sg.inputs["Grid"])
        out = sg.outputs[0]
    sm = N.new("GeometryNodeSetMaterial"); sm.location = (680, 0)
    sm.inputs["Material"].default_value = cloud_material()
    L(out, sm.inputs["Geometry"]); L(sm.outputs[0], go.inputs[0])
    return ng


def _attr(nt, name, loc, kind="FAC", atype="OBJECT"):
    a = nt.nodes.new("ShaderNodeAttribute")
    a.attribute_type = atype
    a.attribute_name = name
    a.location = loc
    return a.outputs["Fac" if kind == "FAC" else ("Vector" if kind == "VEC" else "Color")]


def _math(nt, op, a, b=None, loc=(0, 0), clamp=False):
    m = nt.nodes.new("ShaderNodeMath"); m.operation = op; m.location = loc; m.use_clamp = clamp
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            m.inputs[i].default_value = v
        else:
            nt.links.new(v, m.inputs[i])
    return m.outputs[0]


def cloud_material():
    mat = bpy.data.materials.get(MAT_NAME)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(MAT_NAME)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    N, L = nt.nodes, nt.links.new
    out = N.new("ShaderNodeOutputMaterial"); out.location = (1300, 0)
    sc = N.new("ShaderNodeVolumeScatter"); sc.location = (1050, 0)
    try:
        sc.phase = "MIE"                       # water droplets: bright silver lining + soft glow
        sc.inputs["Diameter"].default_value = 15.0
    except Exception:
        sc.inputs["Anisotropy"].default_value = 0.75
    L(sc.outputs[0], out.inputs["Volume"])
    L(_attr(nt, "fw_color", (800, 200), kind="COL"), sc.inputs["Color"])
    dens = _attr(nt, "density", (-600, 300), atype="GEOMETRY")
    tc = N.new("ShaderNodeTexCoord"); tc.location = (-900, 0)
    seed = _attr(nt, "fw_seed", (-900, -300))
    sv = N.new("ShaderNodeCombineXYZ"); sv.location = (-700, -300)
    for k in ("X", "Y", "Z"):
        L(seed, sv.inputs[k])
    sm = _math(nt, "MULTIPLY", seed, 37.0, (-700, -450))
    off = N.new("ShaderNodeVectorMath"); off.operation = "ADD"; off.location = (-500, -150)
    L(tc.outputs["Object"], off.inputs[0]); L(sv.outputs[0], off.inputs[1])
    P = off.outputs[0]
    vor = N.new("ShaderNodeTexVoronoi"); vor.location = (-300, -100); vor.inputs["Scale"].default_value = 1 / 60.0
    L(P, vor.inputs["Vector"])
    fbm = N.new("ShaderNodeTexNoise"); fbm.location = (-300, -350)
    fbm.inputs["Scale"].default_value = 1 / 30.0; fbm.inputs["Detail"].default_value = 6.0; fbm.inputs["Roughness"].default_value = 0.55
    L(P, fbm.inputs["Vector"])
    big = N.new("ShaderNodeTexNoise"); big.location = (-300, -600)
    big.inputs["Scale"].default_value = 1 / 380.0; big.inputs["Detail"].default_value = 2.0; big.inputs["Roughness"].default_value = 0.5
    L(P, big.inputs["Vector"])
    noise = _math(nt, "ADD", _math(nt, "ADD", _math(nt, "MULTIPLY", vor.outputs["Distance"], 0.46, (-50, -100)),
                  _math(nt, "MULTIPLY", fbm.outputs["Fac"], 0.44, (-50, -350)), (120, -200)),
                  _math(nt, "MULTIPLY", big.outputs["Fac"], 0.10, (-50, -600)), (200, -300))
    puff = _attr(nt, "fw_puff", (120, -400))
    lo = _math(nt, "MULTIPLY", noise, _math(nt, "MULTIPLY", puff, 1.25, (300, -400)), (450, -250))
    mr = N.new("ShaderNodeMapRange"); mr.location = (620, 150); mr.clamp = True
    L(dens, mr.inputs["Value"]); L(lo, mr.inputs["From Min"]); mr.inputs["From Max"].default_value = 0.75
    sep = N.new("ShaderNodeSeparateXYZ"); sep.location = (300, 450)
    L(tc.outputs["Object"], sep.inputs[0])
    base = N.new("ShaderNodeMapRange"); base.location = (500, 450); base.interpolation_type = "SMOOTHSTEP"
    L(sep.outputs["Z"], base.inputs["Value"]); base.inputs["From Min"].default_value = 0.0; base.inputs["From Max"].default_value = 120.0
    user = _attr(nt, "fw_density", (620, -150))
    d = _math(nt, "MULTIPLY", _math(nt, "MULTIPLY", mr.outputs["Result"], base.outputs["Result"], (800, 100)), user, (900, 0))
    L(_math(nt, "MULTIPLY", d, BASE_DENSITY, (980, -100)), sc.inputs["Density"])
    return mat


def _cloud_collection(scene):
    coll = bpy.data.collections.get("FaveWeather Clouds")
    if coll is None:
        coll = bpy.data.collections.new("FaveWeather Clouds")
        scene.collection.children.link(coll)
    return coll


def _write_spheres(obj, spheres):
    me = obj.data
    me.clear_geometry()
    me.from_pydata([(s[0], s[1], s[2]) for s in spheres], [], [])
    at = me.attributes.get("fw_r") or me.attributes.new("fw_r", "FLOAT", "POINT")
    at.data.foreach_set("value", [s[3] for s in spheres])
    me.update()


def _apply_voxel(obj):
    mod = obj.modifiers.get("FaveWeather Cloud")
    if mod is None:
        return
    sz = obj.get("fw_size", [3000, 3000, 3000])
    sc = max(abs(v) for v in obj.scale) or 1.0
    vox = max(4.0, min(60.0, max(sz) / 240.0)) / sc * (2.0 if obj.get("fw_draft") else 1.0)
    key = _iface_id(mod.node_group, "Voxel Size")
    if key:
        _set_mod_input(mod, key, vox)
        obj.update_tag()


def _set_mod_input(mod, key, value):
    """Blender 4.x stores modifier inputs as ID properties; Blender 5 has mod.properties.inputs."""
    props = getattr(mod, "properties", None)
    if props is not None and hasattr(props, "inputs"):
        sock = getattr(props.inputs, key, None)
        if sock is not None and hasattr(sock, "value"):
            if abs(sock.value - value) > 1e-4:
                sock.value = value
            return
    if abs(mod.get(key, -1) - value) > 1e-4:
        mod[key] = value


def rebuild_cloud(obj):
    ctype = obj["fw_cloud"]
    prof = obj.get("fw_prof")
    prof = [tuple(prof[i:i + 2]) for i in range(0, len(prof), 2)] if prof else None
    _write_spheres(obj, gen_spheres(ctype, tuple(obj["fw_size"]), int(obj["fw_seed"] * 1000), prof))
    _apply_voxel(obj)


def add_cloud(context, ctype, location=None, size_jitter=0.0, prof=None, aspect=None, name=None):
    scene = context.scene
    _prepare_scene_for_clouds(scene)
    if ctype == "custom":
        H = 2400.0
        W = max(800.0, min(30000.0, H * (aspect or 2.0)))
        size = (W, W * 0.55, H)
        base = 1300
        puff = 0.6
    else:
        t = CLOUD_TYPES[ctype]
        size, base, puff = t["size"], t["base"], t["puff"]
    k = 1.0 + random.uniform(-size_jitter, size_jitter)
    size = (size[0] * k, size[1] * k, size[2] * k)
    if location is None:
        cam = scene.camera
        if cam is not None:
            fwd = cam.matrix_world.to_quaternion() @ Vector((0, 0, -1))
            fwd.z = 0
            fwd = fwd.normalized() if fwd.length > 1e-6 else Vector((0, 1, 0))
            origin = cam.matrix_world.translation
        else:
            fwd, origin = Vector((0, 1, 0)), Vector((0, 0, 0))
        dist = 6000 + max(size[0], size[1]) * 1.2
        location = Vector((origin.x + fwd.x * dist, origin.y + fwd.y * dist, 0))
    me = bpy.data.meshes.new("FaveWeather Cloud")
    obj = bpy.data.objects.new(name or T(TYPE_LABEL[ctype]), me)
    _cloud_collection(scene).objects.link(obj)
    obj.location = (location.x, location.y, base)
    obj.rotation_euler = (0, 0, random.uniform(-0.4, 0.4))
    obj["fw_cloud"] = ctype
    obj["fw_size"] = list(size)
    obj["fw_seed"] = random.uniform(0, 100)
    obj["fw_color"] = [1.0, 1.0, 1.0]
    obj["fw_density"] = 1.0
    obj["fw_puff"] = puff
    if prof:
        obj["fw_prof"] = [v for q in prof for v in q]
    ui = obj.id_properties_ui
    ui("fw_color").update(subtype="COLOR", min=0.0, max=1.0)
    ui("fw_density").update(min=0.0, soft_max=3.0)
    ui("fw_puff").update(min=0.0, max=1.0)
    mod = obj.modifiers.new("FaveWeather Cloud", "NODES")
    mod.node_group = cloud_gn_group()
    rebuild_cloud(obj)
    for o in context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj
    return obj


@bpy.app.handlers.persistent
def _on_depsgraph(scene, depsgraph):
    # keep voxel detail constant in metres when a cloud is scaled with S
    for u in depsgraph.updates:
        if u.is_updated_transform and isinstance(u.id, bpy.types.Object):
            ob = bpy.data.objects.get(u.id.name)
            if ob is not None and "fw_size" in ob.keys():
                sc = round(max(abs(v) for v in ob.scale), 3)
                if ob.get("fw_last_scale") != sc:
                    ob["fw_last_scale"] = sc
                    _apply_voxel(ob)


def _is_cloud(obj):
    return obj is not None and "fw_cloud" in obj.keys()


# ---------------------------------------------------------------------------
#  Render: realistic Cycles settings and a 360° HDRI for skyboxes
# ---------------------------------------------------------------------------
QUALITY = {
    #          samples  volume bounces  step rate
    "draft":  (64,      8,              2.0),
    "high":   (512,     32,             1.0),
    "ultra":  (2048,    128,            0.5),
}


def setup_realistic_render(scene, quality="high"):
    spp, vb, step = QUALITY[quality]
    scene.render.engine = "CYCLES"
    cy = scene.cycles
    cy.samples = spp
    cy.preview_samples = max(16, spp // 16)
    for k, v in (("use_denoising", True), ("use_preview_denoising", True), ("volume_bounces", vb),
                 ("max_bounces", vb + 8), ("transparent_max_bounces", 16), ("volume_step_rate", step),
                 ("volume_preview_step_rate", step * 2), ("volume_max_steps", 2048)):
        try:
            setattr(cy, k, v)
        except Exception:
            pass
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for dev in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
            try:
                prefs.compute_device_type = dev
                prefs.get_devices()
                if any(d.use for d in prefs.devices if d.type != "CPU") or any(d.type != "CPU" for d in prefs.devices):
                    for d in prefs.devices:
                        d.use = True
                    cy.device = "GPU"
                    break
            except Exception:
                continue
    except Exception:
        pass
    vs = scene.view_settings
    for vt in ("AgX", "Filmic"):
        try:
            vs.view_transform = vt
            break
        except Exception:
            pass
    for lk in ("AgX - Medium High Contrast", "Medium High Contrast"):
        try:
            vs.look = lk
            break
        except Exception:
            pass
    draft = quality == "draft"
    for o in bpy.data.objects:
        if "fw_size" in o.keys():
            o["fw_draft"] = draft
            _apply_voxel(o)
    _prepare_scene_for_clouds(scene)


PANO_CAM = "FaveWeather 360 Camera"


def _pano_camera(scene):
    cam = bpy.data.objects.get(PANO_CAM)
    if cam is None:
        cd = bpy.data.cameras.new(PANO_CAM)
        cam = bpy.data.objects.new(PANO_CAM, cd)
        scene.collection.objects.link(cam)
    cd = cam.data
    cd.type = "PANO"
    for target in (cd, getattr(cd, "cycles", None)):
        if target is not None and hasattr(target, "panorama_type"):
            try:
                target.panorama_type = "EQUIRECTANGULAR"
            except Exception:
                pass
    cd.clip_start = 0.5
    cd.clip_end = 200000.0
    src = scene.camera if scene.camera and scene.camera.name != PANO_CAM else None
    loc = src.matrix_world.translation.copy() if src else Vector((0, 0, 2))
    cam.location = loc
    # horizon in the middle of the image, north (+Y) in the centre
    cam.rotation_euler = (math.radians(90), 0, 0)
    return cam


_restore = {}


@bpy.app.handlers.persistent
def _after_render(scene, *args):
    if scene.name in _restore:
        prev = bpy.data.objects.get(_restore.pop(scene.name))
        if prev is not None:
            scene.camera = prev
    for h in (bpy.app.handlers.render_complete, bpy.app.handlers.render_cancel):
        if _after_render in h and not _restore:
            h.remove(_after_render)


def _prepare_scene_for_clouds(scene):
    """Clouds are kilometres away: widen clip ranges and volume ranges."""
    if scene.camera and scene.camera.type == "CAMERA":
        scene.camera.data.clip_end = max(scene.camera.data.clip_end, 200000.0)
    try:
        for win in bpy.context.window_manager.windows:
            for area in win.screen.areas:
                if area.type == "VIEW_3D":
                    for sp in area.spaces:
                        if sp.type == "VIEW_3D":
                            sp.clip_end = max(sp.clip_end, 200000.0)
    except Exception:
        pass
    ee = scene.eevee
    for k, v in (("use_volume_custom_range", True), ("volumetric_end", 60000.0), ("volumetric_start", 1.0), ("use_volumetric_shadows", True)):
        if hasattr(ee, k):
            try:
                setattr(ee, k, max(getattr(ee, k), v) if isinstance(v, float) else v)
            except Exception:
                pass
    try:
        scene.cycles.volume_max_steps = max(scene.cycles.volume_max_steps, 1024)
        scene.cycles.volume_bounces = max(scene.cycles.volume_bounces, 8)
        scene.cycles.max_bounces = max(scene.cycles.max_bounces, 12)
    except Exception:
        pass


def load_app_shapes(path):
    """Cloud shapes exported from the FaveWeather web app (.zip or .json)."""
    if path.lower().endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.lower().endswith(".json"))
            data = json.loads(z.read(name).decode("utf-8"))
    else:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    shapes = data if isinstance(data, list) else data.get("shapes", [])
    out = []
    for sh in shapes:
        prof = sh.get("prof") or []
        if len(prof) < 4:
            continue
        out.append((str(sh.get("name", "shape"))[:20], [(float(a), float(b)) for a, b in prof], float(sh.get("aspect", 2.0))))
    return out


# ---------------------------------------------------------------------------
#  Import from the FaveWeather app (.zip / .hdr)
# ---------------------------------------------------------------------------
SUN_RE = re.compile(r"elevation\s+(-?[\d.]+)\s*deg,\s*azimuth\s+(-?[\d.]+)\s*deg")


def _extract(path):
    if path.lower().endswith(".zip"):
        out_dir = os.path.join(os.path.dirname(path), os.path.splitext(os.path.basename(path))[0])
        os.makedirs(out_dir, exist_ok=True)
        with zipfile.ZipFile(path) as z:
            z.extractall(out_dir)
        hdrs = [f for f in os.listdir(out_dir) if f.lower().endswith(".hdr")]
        if not hdrs:
            raise RuntimeError("No .hdr file inside the zip")
        hdr = os.path.join(out_dir, hdrs[0])
        readme = os.path.join(out_dir, "README.txt")
    else:
        hdr = path
        readme = os.path.join(os.path.dirname(path), "README.txt")
    el = az = None
    if os.path.exists(readme):
        m = SUN_RE.search(open(readme, encoding="utf-8", errors="ignore").read())
        if m:
            el, az = float(m.group(1)), float(m.group(2))
    return hdr, el, az


def setup_world(context, hdr, el, az, strength=1.0, add_sun=True, sun_strength=4.0, north_y=True):
    scene = context.scene
    world = scene.world or bpy.data.worlds.new("FaveWeather")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    coord = nt.nodes.new("ShaderNodeTexCoord"); coord.location = (-900, 0)
    mapping = nt.nodes.new("ShaderNodeMapping"); mapping.location = (-700, 0)
    mapping.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(-90.0) if north_y else 0.0)
    env = nt.nodes.new("ShaderNodeTexEnvironment"); env.location = (-450, 0)
    env.image = bpy.data.images.load(hdr, check_existing=True)
    bg = nt.nodes.new("ShaderNodeBackground"); bg.location = (-150, 0)
    bg.inputs["Strength"].default_value = strength
    out = nt.nodes.new("ShaderNodeOutputWorld"); out.location = (100, 0)
    nt.links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    sun_obj = bpy.data.objects.get(SUN_NAME)
    if add_sun and el is not None and el > -2.0:
        if sun_obj is None:
            light = bpy.data.lights.new(SUN_NAME, type="SUN")
            sun_obj = bpy.data.objects.new(SUN_NAME, light)
            scene.collection.objects.link(sun_obj)
        sun_obj.data.energy = sun_strength
        sun_obj.data.angle = math.radians(0.53)
        d = _sun_vector(el, az) if north_y else Vector((math.cos(math.radians(az)) * math.cos(math.radians(el)), -math.sin(math.radians(az)) * math.cos(math.radians(el)), math.sin(math.radians(el))))
        sun_obj.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
        sun_obj.location = d * 30.0
    return env.image


# ---------------------------------------------------------------------------
#  Operators
# ---------------------------------------------------------------------------
class FW_OT_make_sky(bpy.types.Operator):
    """Set the World to a physical sky with a matching Sun lamp"""
    bl_idname = "faveweather.make_sky"
    bl_label = "Make Sky"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        make_sky(context)
        return {"FINISHED"}


class FW_OT_sky_preset(bpy.types.Operator):
    """Apply a time-of-day preset"""
    bl_idname = "faveweather.sky_preset"
    bl_label = "Sky Preset"
    bl_options = {"REGISTER", "UNDO"}
    preset: StringProperty()

    def execute(self, context):
        if _sky_nodes(context.scene)[0] is None:
            make_sky(context)
        for k, v in SKY_PRESETS[self.preset].items():
            setattr(context.scene.fw_sky, k, v)
        return {"FINISHED"}


class FW_OT_add_cloud(bpy.types.Operator):
    """Add a volumetric cloud in front of the camera. Move and scale it like any object"""
    bl_idname = "faveweather.add_cloud"
    bl_label = "Add Cloud"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        add_cloud(context, context.scene.fw_sky.cloud_type)
        return {"FINISHED"}


class FW_OT_scatter_clouds(bpy.types.Operator):
    """Scatter clouds of the chosen type around the camera"""
    bl_idname = "faveweather.scatter_clouds"
    bl_label = "Scatter Clouds"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        p = context.scene.fw_sky
        cam = context.scene.camera
        origin = cam.matrix_world.translation if cam else Vector((0, 0, 0))
        for _ in range(p.scatter_count):
            a = random.uniform(0, 2 * math.pi)
            d = math.sqrt(random.uniform(0.05, 1.0)) * 22000 + 2500
            add_cloud(context, p.cloud_type, Vector((origin.x + math.cos(a) * d, origin.y + math.sin(a) * d, 0)), size_jitter=0.35)
        return {"FINISHED"}


class FW_OT_new_shape(bpy.types.Operator):
    """Give the selected clouds a new random shape"""
    bl_idname = "faveweather.new_shape"
    bl_label = "New Shape"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        for o in context.selected_objects:
            if _is_cloud(o):
                o["fw_seed"] = random.uniform(0, 100)
                if "fw_size" in o.keys():
                    rebuild_cloud(o)
                o.update_tag()
        return {"FINISHED"}


class FW_OT_delete_clouds(bpy.types.Operator):
    """Delete every FaveWeather cloud"""
    bl_idname = "faveweather.delete_clouds"
    bl_label = "Delete Clouds"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        for o in [o for o in bpy.data.objects if _is_cloud(o)]:
            bpy.data.objects.remove(o, do_unlink=True)
        return {"FINISHED"}


class IMPORT_OT_faveweather(bpy.types.Operator, ImportHelper):
    """Import a FaveWeather sky (.zip from the app, or its .hdr)"""
    bl_idname = "import_scene.faveweather"
    bl_label = "Import FaveWeather Sky"
    bl_options = {"REGISTER", "UNDO"}

    filter_glob: StringProperty(default="*.zip;*.hdr", options={"HIDDEN"})
    strength: FloatProperty(name="Sky Strength", default=1.0, min=0.0, soft_max=5.0)
    add_sun: BoolProperty(name="Add Matching Sun Lamp", default=True)
    sun_strength: FloatProperty(name="Sun Strength", default=4.0, min=0.0, soft_max=20.0)
    north_y: BoolProperty(name="North = +Y", default=True)

    def execute(self, context):
        try:
            hdr, el, az = _extract(self.filepath)
            setup_world(context, hdr, el, az, self.strength, self.add_sun, self.sun_strength, self.north_y)
        except Exception as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        self.report({"INFO"}, "FaveWeather sky imported")
        return {"FINISHED"}


class FW_OT_render_setup(bpy.types.Operator):
    """Cycles with many volume bounces, AgX colour and denoising: the settings real-looking clouds need"""
    bl_idname = "faveweather.render_setup"
    bl_label = "Realistic Render Setup"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        setup_realistic_render(context.scene, context.scene.fw_sky.quality)
        self.report({"INFO"}, "FaveWeather: realistic render settings applied")
        return {"FINISHED"}


class FW_OT_render_hdri(bpy.types.Operator, ExportHelper):
    """Render the whole sky as a 360° equirectangular HDRI (.exr) for game-engine skyboxes"""
    bl_idname = "faveweather.render_hdri"
    bl_label = "Render 360° HDRI"
    filename_ext = ".exr"
    filter_glob: StringProperty(default="*.exr", options={"HIDDEN"})

    def invoke(self, context, event):
        if not self.filepath:
            self.filepath = bpy.path.ensure_ext(bpy.path.abspath("//") + "FaveWeather_sky", ".exr") if bpy.data.filepath else "FaveWeather_sky.exr"
        return super().invoke(context, event)

    def execute(self, context):
        scene = context.scene
        setup_realistic_render(scene, scene.fw_sky.quality)
        prev = scene.camera
        cam = _pano_camera(scene)
        if prev is not None and prev != cam:
            _restore[scene.name] = prev.name
        scene.camera = cam
        w = int(scene.fw_sky.hdri_res)
        r = scene.render
        r.resolution_x, r.resolution_y, r.resolution_percentage = w, w // 2, 100
        r.image_settings.file_format = "OPEN_EXR"
        try:
            r.image_settings.color_depth = "32"
        except Exception:
            pass
        r.filepath = self.filepath
        for h in (bpy.app.handlers.render_complete, bpy.app.handlers.render_cancel):
            if _after_render not in h:
                h.append(_after_render)
        bpy.ops.render.render("INVOKE_DEFAULT", write_still=True)
        return {"FINISHED"}


class IMPORT_OT_faveweather_shapes(bpy.types.Operator, ImportHelper):
    """Turn cloud shapes made in the FaveWeather app (Assets > My shapes > Export) into volumetric clouds"""
    bl_idname = "import_scene.faveweather_shapes"
    bl_label = "Import Cloud Shapes"
    bl_options = {"REGISTER", "UNDO"}
    filter_glob: StringProperty(default="*.zip;*.json", options={"HIDDEN"})

    def execute(self, context):
        try:
            shapes = load_app_shapes(self.filepath)
        except Exception as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        if not shapes:
            self.report({"WARNING"}, "No cloud shapes found")
            return {"CANCELLED"}
        cam = context.scene.camera
        origin = cam.matrix_world.translation if cam else Vector((0, 0, 0))
        fwd = Vector((0, 1, 0))
        if cam:
            f = cam.matrix_world.to_quaternion() @ Vector((0, 0, -1)); f.z = 0
            if f.length > 1e-6:
                fwd = f.normalized()
        side = Vector((fwd.y, -fwd.x, 0))
        for i, (name, prof, aspect) in enumerate(shapes):
            off = (i - (len(shapes) - 1) / 2) * 7000
            loc = origin + fwd * 11000 + side * off
            add_cloud(context, "custom", Vector((loc.x, loc.y, 0)), prof=prof, aspect=aspect, name=name)
        self.report({"INFO"}, f"Imported {len(shapes)} cloud shapes")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
#  Sidebar panel
# ---------------------------------------------------------------------------
class VIEW3D_PT_faveweather(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "FaveWeather"
    bl_label = "FaveWeather"

    def draw(self, context):
        lay = self.layout
        p = context.scene.fw_sky
        box = lay.box(); box.label(text=T("Sky"), icon="WORLD")
        box.operator(FW_OT_make_sky.bl_idname, text=T("Make Sky"))
        row = box.row(align=True)
        for key, label in (("clear", "Clear"), ("morning", "Morning"), ("sunset", "Sunset"), ("twilight", "Twilight")):
            row.operator(FW_OT_sky_preset.bl_idname, text=T(label)).preset = key
        col = box.column(align=True)
        col.prop(p, "sun_elevation", text=T("Sun Elevation"), slider=True)
        col.prop(p, "sun_azimuth", text=T("Sun Azimuth"), slider=True)
        col.prop(p, "haze", text=T("Haze"))
        col.prop(p, "air", text=T("Air"))
        col.prop(p, "ozone", text=T("Ozone"))
        col.prop(p, "sky_strength", text=T("Sky Strength"))
        col.prop(p, "sun_strength", text=T("Sun Strength"))

        box = lay.box(); box.label(text=T("Clouds"), icon="OUTLINER_OB_VOLUME")
        box.prop(p, "cloud_type", text="")
        row = box.row(align=True)
        row.operator(FW_OT_add_cloud.bl_idname, text=T("Add Cloud"), icon="ADD")
        row.operator(FW_OT_scatter_clouds.bl_idname, text=T("Scatter Clouds"))
        box.prop(p, "scatter_count", text=T("Count"))
        box.operator(FW_OT_delete_clouds.bl_idname, text=T("Delete Clouds"), icon="TRASH")

        ob = context.active_object
        if _is_cloud(ob):
            sb = lay.box(); sb.label(text=T("Selected Cloud") + f"：{ob.name}", icon="RESTRICT_SELECT_OFF")
            sb.prop(ob, '["fw_color"]', text=T("Color"))
            sb.prop(ob, '["fw_density"]', text=T("Density"), slider=True)
            sb.prop(ob, '["fw_puff"]', text=T("Detail") if "fw_size" in ob.keys() else T("Puffiness"), slider=True)
            if "fw_flat" in ob.keys():
                sb.prop(ob, '["fw_flat"]', text=T("Flatness"), slider=True)
            sb.operator(FW_OT_new_shape.bl_idname, text=T("New Shape"), icon="FILE_REFRESH")
            sb.label(text=T("Size (m)"))
            sb.prop(ob, "dimensions", text="")
            sb.label(text=T("Tip: move / scale clouds with G / S like any object"), icon="INFO")

        box = lay.box(); box.label(text=T("Render"), icon="RENDER_STILL")
        box.row(align=True).prop(p, "quality", expand=True)
        box.operator(FW_OT_render_setup.bl_idname, text=T("Realistic Render Setup"), icon="SHADING_RENDERED")
        box.label(text=T("Render with F12. Ultra takes time but looks the most real"), icon="INFO")
        row = box.row(align=True)
        row.prop(p, "hdri_res", text=T("Resolution"))
        box.operator(FW_OT_render_hdri.bl_idname, text=T("Render 360° HDRI"), icon="WORLD")
        box.label(text=T("HDRI for Unity / Unreal / Twinmotion skyboxes"))

        box = lay.box(); box.label(text=T("Import from App"), icon="IMPORT")
        box.operator(IMPORT_OT_faveweather.bl_idname, text=T("Import Sky (.zip / .hdr)"))
        box.operator(IMPORT_OT_faveweather_shapes.bl_idname, text=T("Import Cloud Shapes (.zip / .json)"))


def _menu(self, context):
    self.layout.operator(IMPORT_OT_faveweather.bl_idname, text="FaveWeather Sky (.zip / .hdr)")
    self.layout.operator(IMPORT_OT_faveweather_shapes.bl_idname, text="FaveWeather Cloud Shapes (.zip / .json)")


CLASSES = (FWSkyProps, FW_OT_make_sky, FW_OT_sky_preset, FW_OT_add_cloud, FW_OT_scatter_clouds,
           FW_OT_new_shape, FW_OT_delete_clouds, FW_OT_render_setup, FW_OT_render_hdri,
           IMPORT_OT_faveweather, IMPORT_OT_faveweather_shapes, VIEW3D_PT_faveweather)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Scene.fw_sky = PointerProperty(type=FWSkyProps)
    bpy.types.TOPBAR_MT_file_import.append(_menu)
    if _on_depsgraph not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)


def unregister():
    if _on_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph)
    bpy.types.TOPBAR_MT_file_import.remove(_menu)
    del bpy.types.Scene.fw_sky
    for h in (bpy.app.handlers.render_complete, bpy.app.handlers.render_cancel):
        if _after_render in h:
            h.remove(_after_render)
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
