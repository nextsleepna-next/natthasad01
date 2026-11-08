#!/usr/bin/env python3
"""ส่งออกโมเดล GLB เป็นหน้าเว็บดู 3 มิติไฟล์เดียว (หมุน/ซูม/เลื่อนด้วยนิ้ว) สำหรับเผยแพร่ด้วยเครื่องมือ Artifact · ใช้บน iPad ได้
ถอดรหัส GLB ในหน้าด้วย three.js r128 (หน้า Artifact ห้าม fetch data:/blob: ดังนั้นห้ามใช้ model-viewer แบบ src=data:)

    python scripts/export_web_viewer.py model.glb viewer.html "ชื่อโมเดล"
แล้วเผยแพร่ viewer.html ด้วย Artifact (icon "cube") · GLB ใหญ่เกิน GLB_MAX_BYTES จะลดจำนวนหน้าอัตโนมัติ
(ต้องมี trimesh + fast-simplification) ให้ HTML รวมไม่เกิน 15 MB
"""
import base64
import html
import sys
from pathlib import Path

GLB_MAX_BYTES = 11 * 1024 * 1024
HTML_MAX_BYTES = 15 * 1024 * 1024
MIN_FACE_FRACTION = 0.02          # ไม่ลดต่ำกว่านี้ (แจ้งผิดพลาดแทน)

TEMPLATE = r'''<title>Yotathai Model Viewer</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Kanit:wght@400;600&family=Sarabun:wght@400;600&display=swap">
<style>
/* layout: the model fills the page; a slim caption above and gesture hints below */
:root{--bg:#f3f1ec;--fg:#1d2340;--muted:#5d6482;--line:#d9d6cc;--stage:#e9e6dd;--display:'Kanit',system-ui,sans-serif;--body:'Sarabun',system-ui,sans-serif}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#14172b;--fg:#e8e9f5;--muted:#9aa0c4;--line:#2b3052;--stage:#1b1f3a;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#14172b;--fg:#e8e9f5;--muted:#9aa0c4;--line:#2b3052;--stage:#1b1f3a;color-scheme:dark}
html,body{height:100%}
body{background:var(--bg);color:var(--fg);font-family:var(--body);font-size:16px;display:flex;flex-direction:column;gap:10px;padding-block:12px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
header{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 14px}
h1{font-family:var(--display);font-weight:600;font-size:1.25rem;margin:0;text-wrap:balance}
#meta{margin:0;color:var(--muted);font-size:.95rem}
.stage{position:relative;flex:1;min-height:320px;border:1px solid var(--line);background:var(--stage);border-radius:6px;overflow:hidden}
#cv{position:absolute;inset:0;width:100%;height:100%;display:block;touch-action:none}
footer{color:var(--muted);font-size:.9rem;display:flex;flex-wrap:wrap;gap:4px 16px}
footer b{color:var(--fg);font-weight:600}
</style>
<header><h1>__TITLE__</h1><p id="meta">กำลังโหลดโมเดล…</p></header>
<div class="stage"><canvas id="cv"></canvas></div>
<footer><span><b>หมุน</b> ลากนิ้วเดียว</span><span><b>ซูม</b> บีบหรือถ่างสองนิ้ว</span><span><b>เลื่อน</b> ลากสองนิ้ว</span></footer>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/GLTFLoader.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
<script>
var GLB_B64="__B64__";
var meta=document.getElementById('meta');
function fail(m){meta.textContent='โหลดโมเดลไม่สำเร็จ: '+m}
try{
  var cv=document.getElementById('cv'),stage=cv.parentElement;
  var renderer=new THREE.WebGLRenderer({canvas:cv,antialias:true,alpha:true});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));
  var scene=new THREE.Scene();
  scene.add(new THREE.HemisphereLight(0xffffff,0x8a8f9f,0.5));
  var sun=new THREE.DirectionalLight(0xffffff,0.6);sun.position.set(6,10,8);scene.add(sun);
  var camera=new THREE.PerspectiveCamera(40,1,0.01,10000);
  var controls=new THREE.OrbitControls(camera,cv);
  controls.enableDamping=true;controls.autoRotate=true;controls.autoRotateSpeed=1.2;
  controls.addEventListener('start',function(){controls.autoRotate=false});
  function resize(){var w=stage.clientWidth,h=stage.clientHeight;renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix()}
  new ResizeObserver(resize).observe(stage);resize();
  (function loop(){requestAnimationFrame(loop);controls.update();renderer.render(scene,camera)})();
  var bin=atob(GLB_B64),buf=new Uint8Array(bin.length);
  for(var i=0;i<bin.length;i++)buf[i]=bin.charCodeAt(i);
  new THREE.GLTFLoader().parse(buf.buffer,'',function(g){
    var m=g.scene;scene.add(m);
    var box=new THREE.Box3().setFromObject(m),c=box.getCenter(new THREE.Vector3()),s=box.getSize(new THREE.Vector3());
    var r=Math.max(s.x,s.y,s.z)||1;
    controls.target.copy(c);
    camera.position.set(c.x+r*1.1,c.y+r*0.8,c.z+r*1.4);
    camera.near=r/100;camera.far=r*50;camera.updateProjectionMatrix();controls.update();
    var grid=new THREE.GridHelper(Math.ceil(r*2),Math.ceil(r*2),0x888899,0xaaaabb);grid.position.set(c.x,box.min.y,c.z);scene.add(grid);
    meta.textContent='ขนาด '+s.x.toFixed(1)+' × '+s.y.toFixed(1)+' × '+s.z.toFixed(1)+' ม.';
  },function(e){fail(e&&e.message||e)});
}catch(e){fail(e.message)}
</script>
'''


def _decimate(src: Path, ratio: float) -> bytes:
    """โหลด GLB แล้วลดหน้าของทุกเมชลงเหลือสัดส่วน ratio คืนค่าเป็นไบต์ GLB ใหม่"""
    import trimesh

    scene = trimesh.load(str(src), force="scene")
    for name, geom in list(scene.geometry.items()):
        if not isinstance(geom, trimesh.Trimesh) or len(geom.faces) < 200:
            continue
        target = max(100, int(len(geom.faces) * ratio))
        scene.geometry[name] = geom.simplify_quadric_decimation(face_count=target)
    return scene.export(file_type="glb")


def fit_glb(src: Path) -> bytes:
    data = src.read_bytes()
    if len(data) <= GLB_MAX_BYTES:
        return data
    ratio = GLB_MAX_BYTES / len(data) * 0.85
    while ratio >= MIN_FACE_FRACTION:
        out = _decimate(src, ratio)
        print(f"ลดความละเอียด ratio={ratio:.3f} -> {len(out)/1e6:.2f} MB", file=sys.stderr)
        if len(out) <= GLB_MAX_BYTES:
            return out
        ratio *= 0.7
    raise SystemExit("ลดความละเอียดแล้วยังใหญ่เกิน (อาจเป็นเพราะเท็กซ์เจอร์) — ลดภาพเท็กซ์เจอร์ก่อน")


def build(src: Path, dst: Path, title: str) -> None:
    glb = fit_glb(src)
    page = (TEMPLATE.replace("__TITLE__", html.escape(title))
            .replace("__B64__", base64.b64encode(glb).decode("ascii")))
    size = len(page.encode("utf-8"))
    if size > HTML_MAX_BYTES:
        raise SystemExit(f"HTML {size/1e6:.1f} MB เกินเพดาน {HTML_MAX_BYTES/1e6:.0f} MB")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(page, encoding="utf-8")
    print(f"GLB {len(glb)/1e6:.2f} MB -> HTML {size/1e6:.2f} MB : {dst}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    build(Path(sys.argv[1]), Path(sys.argv[2]),
          sys.argv[3] if len(sys.argv) > 3 else Path(sys.argv[1]).stem)
