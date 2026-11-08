#!/usr/bin/env bash
# เตรียมเครื่องคลาวด์ (Linux) ให้รันโปรแกรม Yotathai Plan 2D/3D แบบไม่เปิดหน้าจอ
# รันซ้ำได้ ไม่เสียหาย · เรียกอัตโนมัติตอนเปิดเซสชันบนเว็บ (.claude/settings.json) · ใช้เอง: bash cloud/setup.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
log() { echo "[setup] $*"; }
SUDO=""; [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null && SUDO="sudo"

# 1) ไลบรารีระบบที่ Qt ต้องใช้แม้ไม่เปิดหน้าจอ
if command -v apt-get >/dev/null && ! ldconfig -p 2>/dev/null | grep -q libEGL.so.1; then
  log "ติดตั้งไลบรารีระบบสำหรับ Qt"
  $SUDO apt-get update -qq >/dev/null 2>&1
  $SUDO apt-get install -y -qq libgl1 libegl1 libxkbcommon0 libfontconfig1 libdbus-1-3 \
    libglib2.0-0 fontconfig poppler-utils qpdf >/dev/null 2>&1 || log "คำเตือน: ติดตั้งไลบรารีระบบไม่ครบ"
fi

# 2) Python 3.14 + ไลบรารี (venv/ ที่โฟลเดอร์โปรเจกต์)
if [ ! -x venv/bin/python ]; then
  log "สร้าง venv (Python 3.14)"
  command -v uv >/dev/null || python3 -m pip install -q --user uv >/dev/null 2>&1 || pip install -q uv >/dev/null 2>&1
  export PATH="$HOME/.local/bin:$PATH"
  uv venv -q --python 3.14 venv || { log "ผิดพลาด: สร้าง venv ไม่ได้"; exit 1; }
fi
if [ ! -f venv/.req-ok ] || [ requirements-cloud.txt -nt venv/.req-ok ]; then
  log "ติดตั้งไลบรารี Python (ครั้งแรกใช้เวลาหลายนาที)"
  export PATH="$HOME/.local/bin:$PATH"
  uv pip install -q --python venv/bin/python -r requirements-cloud.txt && touch venv/.req-ok \
    || log "ผิดพลาด: ติดตั้งไลบรารี Python ไม่ครบ"
fi

# 3) ฟอนต์ไทย (Kanit / Sarabun แจกต่อได้ OFL) + ฟอนต์เขียนแบบของโปรแกรม
FD="$HOME/Library/Fonts"; mkdir -p "$FD"
GF="https://raw.githubusercontent.com/google/fonts/main/ofl"
for f in kanit/Kanit-Regular kanit/Kanit-Medium kanit/Kanit-Bold sarabun/Sarabun-Regular sarabun/Sarabun-Bold; do
  n="$(basename "$f").ttf"
  [ -s "$FD/$n" ] || curl -fsSL "$GF/$f.ttf" -o "$FD/$n" || log "คำเตือน: โหลดฟอนต์ $n ไม่ได้"
done
cp -n fonts/*.ttf "$FD/" 2>/dev/null
mkdir -p "$HOME/.local/share/fonts" && cp -n "$FD"/*.ttf "$HOME/.local/share/fonts/" 2>/dev/null
command -v fc-cache >/dev/null && fc-cache -f >/dev/null 2>&1

# 4) LibreDWG (แปลง DWG <-> DXF) — คอมไพล์จากซอร์สทางการครั้งแรกใช้เวลาไม่กี่นาที แล้วเก็บไว้ใช้ซ้ำ
LV="0.14.8612"; LSHA="ac2d65b8b6d16df41b0909b8a629932fe27aedd2630fbb6047c4197194efad8b"
LB="ingecad-src/vendor/libredwg/bin"
if [ ! -x "$LB/dxf2dwg" ] && command -v gcc >/dev/null && command -v make >/dev/null; then
  LC="$HOME/.cache/libredwg"; mkdir -p "$LC"
  if [ ! -x "$LC/prefix/bin/dxf2dwg" ]; then
    log "คอมไพล์ LibreDWG $LV (ครั้งแรก ไม่กี่นาที)"
    ( curl -fsSL -o "$LC/src.tar.gz" "https://github.com/LibreDWG/libredwg/releases/download/$LV/libredwg-$LV.tar.gz" \
      && echo "$LSHA  $LC/src.tar.gz" | sha256sum -c --status - \
      && tar xzf "$LC/src.tar.gz" -C "$LC" \
      && cd "$LC/libredwg-$LV" \
      && ./configure --prefix="$LC/prefix" --disable-bindings --disable-python --disable-shared --disable-dependency-tracking >/dev/null 2>&1 \
      && make -j"$(nproc)" >/dev/null 2>&1 && make install >/dev/null 2>&1 ) \
      || log "คำเตือน: คอมไพล์ LibreDWG ไม่สำเร็จ (ใช้ DXF/PDF แทนได้)"
  fi
  if [ -x "$LC/prefix/bin/dxf2dwg" ]; then
    mkdir -p "$LB"
    for n in dwg2dxf dxf2dwg; do
      strip -o "$LB/$n" "$LC/prefix/bin/$n" 2>/dev/null || cp "$LC/prefix/bin/$n" "$LB/$n"
      chmod +x "$LB/$n"
    done
  fi
fi

# 5) Qt แบบไม่มีหน้าจอ
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo 'export QT_QPA_PLATFORM=offscreen' >> "$CLAUDE_ENV_FILE"
fi
mkdir -p work
log "ตรวจเครื่องยนต์"
QT_QPA_PLATFORM=offscreen venv/bin/python scripts/yotathai_ai check 2>&1 | tail -5
log "เสร็จ — ถ้าต้องทำ PDF จากหน้าเว็บ และยังไม่มี Chrome ให้รัน: bash cloud/install-chromium.sh"
