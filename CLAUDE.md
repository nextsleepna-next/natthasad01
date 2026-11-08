# Yotathai Plan — ฉบับใช้ผ่าน Claude บนเว็บ (สำหรับผู้เข้าอบรม)

> เซสชันนี้ทำงานบนเครื่องคลาวด์ Linux ไม่มีหน้าจอ · ผู้ใช้คือผู้เข้าอบรม Yotathai Plan รุ่นบุกเบิก ใช้ Claude บนเว็บแทน Windows

## กติกา
- ตอบเป็นภาษาไทย แบบช่าง กระชับ ประหยัดโควตา (ขั้นละ 1–2 คำสั่ง อ่านไฟล์เฉพาะส่วนที่ใช้ ไม่พิมพ์ไฟล์ใหญ่ออกจอ)
- **แฟ้ม `AI-yotathai/`** (ถ้ามีในโฟลเดอร์นี้) คือชุดทักษะและความรู้ส่วนตัวของผู้ใช้ — เมื่อผู้ใช้สั่ง "อ่านแฟ้ม AI-yotathai ก่อนเริ่มงาน" ให้เปิด `AI-yotathai/00-อ่านก่อน-สำหรับ-AI.md` แล้วทำตาม · ถ้าไม่มีแฟ้มนี้ ให้บอกผู้ใช้ให้อัปโหลดไว้ที่ราก repo นี้ (ดู `README.md`) แล้วหยุดรอ
- ห้ามเดาราคา ปริมาณ ตัวเลขกฎหมาย · เอกสารที่ร่างเป็นร่าง ผู้มีหน้าที่ต้องตรวจและลงนาม
- **ห้ามแก้** `src/` `ingecad-src/` `yotathai/` (ตัวโปรแกรม) · งานของผู้ใช้เก็บใน `work/` เท่านั้น
- **repo นี้ต้องเป็น private** — `AI-yotathai/` เป็นของส่วนตัว ห้ามเผยแพร่ ห้าม push ไปที่อื่น ถ้า repo เป็น public ให้เตือนผู้ใช้ทันที

## ตารางแปลงคำสั่งในใบงาน (เขียนไว้สำหรับ Windows) → เซสชันนี้
| ในใบงาน/ทักษะ | ในเซสชันนี้ |
|---|---|
| `yotathai-ai.bat <คำสั่ง>` | `QT_QPA_PLATFORM=offscreen venv/bin/python scripts/yotathai_ai <คำสั่ง>` |
| `yotathai-python.bat <ไฟล์>` | `venv/bin/python <ไฟล์>` |
| `C:\Yotathai-Work\…` (เช่น `H`) | `work/…` (เช่น `work/house/`) |
| `C:\Yotathai-Work\AI-yotathai` | `AI-yotathai/` |
| `open <ไฟล์>` เปิดโปรแกรม | ไม่มีหน้าจอ → ส่งออก `.glb` แล้วทำหน้าดู 3 มิติ (ด้านล่าง) |
| เมนู ไฟล์ ▸ ส่งออก ▸ รูปภาพ | ทำไม่ได้ในเซสชันนี้ → ใช้หน้าดู 3 มิติ แล้วให้ผู้ใช้แคปภาพจากหน้าจอ |
| พิมพ์ PDF ด้วย Chrome/Edge | ถ้ามี `google-chrome`/`chromium` ใช้ headless ได้ · ไม่มี → `bash cloud/install-chromium.sh` · ยังไม่ได้ → ส่งเป็น HTML ให้ผู้ใช้พิมพ์เอง |

## คำสั่งเครื่องยนต์
```bash
export QT_QPA_PLATFORM=offscreen
venv/bin/python scripts/yotathai_ai check        # ตรวจความพร้อม (เริ่มที่นี่)
venv/bin/python scripts/yotathai_ai recipes      # ฟังก์ชันสร้างโมเดล 3D
venv/bin/python scripts/yotathai_ai build-3d RECIPE.py work/x.igz --glb work/x.glb   # สร้างโมเดล + ส่งออก .glb
venv/bin/python scripts/yotathai_ai model-to-2d work/x.igz work/x.dxf     # ผังพื้น+หลังคา+รูปด้าน
venv/bin/python scripts/yotathai_ai plan-to-3d PLAN.dxf work/x.igz        # ยกแปลน 2D เป็น 3D
venv/bin/python scripts/yotathai_ai draw-2d SCRIPT.py work/x.dxf          # วาด DXF ด้วย ezdxf
venv/bin/python scripts/export_web_viewer.py work/x.glb work/x-view.html "ชื่อ"   # หน้าดู 3 มิติหมุนได้
```
- ถ้า `venv/` ยังไม่มี หรือ `check` ไม่ผ่าน: `bash cloud/setup.sh` (ครั้งแรกใช้เวลาหลายนาที)
- แพ็กเกจ Python ที่มี: numpy ezdxf shapely trimesh Pillow pyproj PySide6 — ห้ามติดตั้งเพิ่มโดยไม่ถามผู้ใช้
- ฟอนต์ไทย: Kanit Sarabun YotathaiDrafting (ติดตั้งโดย setup)

## ส่งผลงานให้ผู้ใช้
- บันทึกเป็นไฟล์ใน `work/` แล้ว commit + push ขึ้น branch ที่ผู้ใช้ใช้อยู่ · ผู้ใช้ดาวน์โหลดจาก GitHub (ปุ่ม Download raw file) หรือจากหน้าเซสชัน
- ถ้ามีเครื่องมือ Artifact ให้เผยแพร่หน้าดู 3 มิติ (HTML) เป็นลิงก์ส่วนตัว · ไม่มี → บอกผู้ใช้ให้ดาวน์โหลด `.html` ไปเปิดในเบราว์เซอร์
- ทุกเซสชันจบด้วย `work/HANDOFF.md` สั้นๆ (ทำอะไร ไฟล์อยู่ไหน ขั้นต่อไป) เพื่อเริ่มห้องใหม่ได้
