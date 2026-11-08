#!/usr/bin/env bash
# ติดตั้งเบราว์เซอร์แบบไม่มีหน้าจอ ไว้พิมพ์ HTML/SVG เป็น PDF (ใช้เมื่อจำเป็นเท่านั้น) — ต้องมีอินเทอร์เน็ตออกไปโหลดได้
set -u
cd "$(cd "$(dirname "$0")/.." && pwd)"
for b in google-chrome chromium chromium-browser; do command -v $b >/dev/null && { echo "มี $b อยู่แล้ว: $(command -v $b)"; exit 0; }; done
export PATH="$HOME/.local/bin:$PATH"
uv pip install -q --python venv/bin/python playwright && venv/bin/python -m playwright install --with-deps chromium \
  && echo "ติดตั้ง Chromium ของ Playwright แล้ว (พิมพ์ PDF ผ่าน venv/bin/python -m playwright …)" \
  || echo "ติดตั้งไม่สำเร็จ (เครือข่ายอาจถูกจำกัด) — แจ้งผู้สอน หรือให้ AI ส่งเป็น HTML แล้วท่านพิมพ์ PDF จากเบราว์เซอร์เอง"
