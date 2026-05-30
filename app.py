import streamlit as st
from leader_schedule import get_leader, schedule_editor_widget
import streamlit.components.v1 as components
from PIL import Image, ImageDraw, ImageFont
import io, os, json
from datetime import date, datetime

st.set_page_config(page_title="Dr to Dr 受付対応表", layout="centered")
st.title("🏥 Dr to Dr 受付対応表")

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
]
_FONT_PATH = None
for _p in FONT_CANDIDATES:
    if os.path.exists(_p):
        _FONT_PATH = _p; break

def get_font(size):
    if _FONT_PATH:
        return ImageFont.truetype(_FONT_PATH, max(10, size))
    return ImageFont.load_default()

# ===== ファイル永続化 =====
CASES_FILE = "dtd_cases.json"

def load_cases():
    if os.path.exists(CASES_FILE):
        try:
            with open(CASES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: return []
    return []

def save_cases(cases):
    try:
        with open(CASES_FILE, "w", encoding="utf-8") as f:
            json.dump(cases, f, ensure_ascii=False, indent=2)
    except: pass

# ===== 時刻から勤務帯判定 =====
def time_to_shift(time_str):
    try:
        h, m = map(int, time_str.split(":"))
        minutes = h * 60 + m
        if 8*60+30 <= minutes < 16*60+30:
            return "日勤"
        return "夜勤"
    except:
        return "夜勤"

LEADERS  = ["前川","中嶋","森木","小舘","遠藤","提嶋"]
WEEKDAYS = ["月","火","水","木","金","土","日"]

# drtodr.png: 1240x1754 (PDF 150dpi)
# ブロックトップ（各症例ヘッダー行Y座標）
BLOCK_TOPS = [146, 400, 654, 908, 1162, 1416]

TIME_OPTIONS = [""] + [f"{h:02d}:{m:02d}" for h in range(24) for m in range(0,60,5)]

# ===== 印刷ウィジェット =====
def dtd_make_print_widget(pil_img, key="print"):
    import base64
    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=95)
    b64 = base64.b64encode(buf.getvalue()).decode()
    html = f"""<!DOCTYPE html>
<html><head><style>
  body{{margin:0;padding:0;background:transparent;font-family:sans-serif}}
  @media screen{{
    .img-wrap{{display:none}}
    .btn{{display:block;width:100%;height:38px;padding:0 14px;box-sizing:border-box;
      background:transparent;color:inherit;border:1px solid rgba(49,51,63,0.2);
      border-radius:4px;font-size:0.875rem;cursor:pointer}}
    .btn:hover{{border-color:#f63366;color:#f63366}}
    @media(prefers-color-scheme:dark){{.btn{{border-color:rgba(250,250,250,0.2);color:#fff}}}}
  }}
  @media print{{
    .btn{{display:none}}
    .img-wrap{{display:block}}
    @page{{size:A4;margin:0}}
    html,body{{height:100%;overflow:hidden;margin:0;padding:0}}
    img{{width:100%;height:auto;max-height:100vh;display:block}}
  }}
</style></head><body>
<div class="img-wrap"><img src="data:image/jpeg;base64,{b64}"></div>
<button class="btn" onclick="window.print()">🖨️ 印刷</button>
</body></html>"""
    return html

# ===== 依頼なしシート =====
def render_norequest(header):
    base = Image.open("drtodr.png").convert("RGB")
    W, H = base.size
    import numpy as np
    arr = np.array(base).astype(float)
    arr[145:, :] = arr[145:, :] * 0.35 + 255 * 0.65
    base = Image.fromarray(arr.astype(np.uint8))
    d = ImageDraw.Draw(base)
    _render_header(d, header, W, H)
    f_big = get_font(100)
    msg = "依頼なし"
    bb = d.textbbox((0,0), msg, font=f_big)
    tw = bb[2]-bb[0]
    d.text(((W-tw)//2, 280), msg, font=f_big, fill=(60,60,60))
    return base

# ===== ヘッダー描画 =====
def _render_header(d, header, W, H):
    f30 = get_font(26)
    f34 = get_font(30)

    dt = header["date"] if isinstance(header["date"], date) else date.fromisoformat(str(header["date"]))
    wd = WEEKDAYS[dt.weekday()]

    # 年・月・日・曜日 (Y≈120の行)
    d.text((210, 100), str(dt.year),  font=f30, fill="black")
    d.text((350, 100), str(dt.month), font=f30, fill="black")
    d.text((415, 100), str(dt.day),   font=f30, fill="black")
    d.text((520, 100), wd,            font=f30, fill="black")

    # 日勤◯/夜勤◯
    def dm(cx, cy, r=14):
        d.ellipse([cx-r, cy-r, cx+r, cy+r], outline="black", width=3)

    if header["shift"] == "日勤":
        dm(610, 120, r=15)
    else:
        dm(685, 120, r=15)

    # リーダー医師名
    d.text((950, 95), header["leader"], font=f34, fill="black")

# ===== メイン描画 =====
def render_drtodr(header, cases, sheet_no=1):
    base = Image.open("drtodr.png").convert("RGB")
    W, H = base.size
    d = ImageDraw.Draw(base)

    f26 = get_font(22)
    f22 = get_font(19)
    f18 = get_font(16)

    def dm(cx, cy, r=12):
        d.ellipse([cx-r, cy-r, cx+r, cy+r], outline="black", width=3)

    def draw_check(cx, cy, size=9):
        d.line([(cx-size, cy), (cx-size//3, cy+size), (cx+size, cy-size)],
               fill="black", width=2)

    # No.（シート番号）
    f_no = get_font(38)
    no_str = str(sheet_no)
    bb = d.textbbox((0,0), no_str, font=f_no)
    tw = bb[2]-bb[0]
    d.text((90 + (85-tw)//2, 98), no_str, font=f_no, fill="black")

    # ヘッダー
    _render_header(d, header, W, H)

    for i, case in enumerate(cases):
        if i >= 6: break
        b = BLOCK_TOPS[i]

        # --- 1行目: 時刻・依頼回数・依頼先（病院/科/医師）---
        y1 = b + 10   # 時刻行のY

        # 時刻
        if case.get("time"):
            d.text((257, y1-15), case["time"], font=f26, fill="black")

        # 依頼回数
        if case.get("req_count") == "初回":
            dm(545, y1+10, r=13)
        else:
            num = (case.get("req_count") or "").replace("回目","").replace("回","")
            if num:
                d.text((620, y1-15), num, font=f26, fill="black")

        # 依頼先: 病院・科・医師
        if case.get("hospital"):
            d.text((760, y1-15), case["hospital"], font=f22, fill="black")
        if case.get("dept"):
            d.text((920, y1-15), case["dept"], font=f22, fill="black")
        if case.get("doctor"):
            d.text((1040, y1-15), case["doctor"], font=f22, fill="black")

        # --- 2行目: 症例（年齢・性別）---
        y2 = b + 40
        if case.get("age"):
            d.text((210, y2-21), str(case["age"]), font=f26, fill="black")
        if case.get("gender") == "M":
            dm(380, y2, r=12)
        elif case.get("gender") == "F":
            dm(445, y2, r=12)

        # --- 概略（自由記載）---
        y3 = b + 80
        f16s = get_font(15)  # 概略用の小さいフォント
        summary = case.get("summary", "")
        if summary:
            lines = []
            line = ""
            for ch in summary:
                line += ch
                if len(line) >= 45:
                    lines.append(line); line = ""
            if line: lines.append(line)
            for li, ln in enumerate(lines[:3]):
                d.text((150, y3-21 + li*20), ln, font=f16s, fill="black")

        # --- 転帰行 ---
        y4 = b + 148
        outcome = case.get("outcome", "")
        outcome_map = {
            "搬入":         (150, y4-34),
            "お断り":       (230, y4-34),
            "院内他科案内": (435, y4-34),
            "患者都合":     (585, y4-34),
            "その他":       (150, y4-7),
        }
        if outcome in outcome_map:
            draw_check(*outcome_map[outcome])

        # --- お断り理由 ---
        if outcome == "お断り":
            yr1 = b + 188
            yr2 = b + 210
            yr3 = b + 232

            reason = case.get("reason", "")
            if reason == "1_満床":
                dm(250, yr1+6, r=10)
                sub_map = {
                    "満床・満床に準ずる状態": (445, yr1+6),
                    "ICU個室(感染等)満床":   (637, yr1+6),
                    "熱傷患者受入不能":       (820, yr1+6),
                }
                if case.get("reason1_sub") in sub_map:
                    dm(*sub_map[case["reason1_sub"]], r=10)
            elif reason == "2_マンパワー":
                dm(250, yr2+7, r=10)
                sub_map2 = {
                    "他患の処置・手術等で余力なし":   (410, yr2+7),
                    "別の救急患者の搬入直前・直後": (648, yr2+7),
                }
                if case.get("reason2_sub") in sub_map2:
                    dm(*sub_map2[case["reason2_sub"]], r=10)
            elif reason == "3_院内専門科":
                dm(250, yr3+6, r=10)
                sub_map3 = {
                    "当該科手術中":   (583, yr3+6),
                    "学会等で不在":   (720, yr3+6),
                    "麻酔科対応不能": (838, yr3+6),
                }
                if case.get("reason3_sub") in sub_map3:
                    dm(*sub_map3[case["reason3_sub"]], r=10)
                if case.get("reason3_dept"):
                    d.text((364, yr3-5), case["reason3_dept"], font=f18, fill="black")

    return base

# ===== セッション初期化 =====
if "dtd_cases" not in st.session_state:
    st.session_state.dtd_cases = load_cases()
if "dtd_images" not in st.session_state:
    st.session_state.dtd_images = []
if "dtd_header" not in st.session_state:
    st.session_state.dtd_header = {"date": date.today().isoformat(), "leader": "前川"}
if "dtd_date_set" not in st.session_state:
    st.session_state.dtd_date_set = False

cases = st.session_state.dtd_cases

# ===== ヘッダー入力 =====
st.subheader("📋 基本情報")
c1, c2 = st.columns(2)
with c1:
    _today = date.today()
    saved_date = st.session_state.dtd_header.get("date", _today.isoformat())
    if saved_date != _today.isoformat() and not st.session_state.dtd_date_set:
        saved_date = _today.isoformat()
    st.session_state.dtd_date_set = True
    input_date = st.date_input("日付", value=date.fromisoformat(str(saved_date)))
with c2:
    from datetime import timezone, timedelta
    _jst = timezone(timedelta(hours=9))
    _now = datetime.now(_jst)
    _sh = "日勤" if 8*60+30 <= _now.hour*60+_now.minute < 16*60+30 else "夜勤"
    _ld = get_leader(input_date, _sh)
    _def_idx = LEADERS.index(_ld) if _ld in LEADERS else \
               LEADERS.index(st.session_state.dtd_header.get("leader","前川")) if \
               st.session_state.dtd_header.get("leader") in LEADERS else 0
    leader = st.selectbox("リーダー医師名", LEADERS, index=_def_idx)

st.session_state.dtd_header = {"date": input_date.isoformat(), "leader": leader}

# 日勤/夜勤の分類
nisshin = [c for c in cases if time_to_shift(c.get("time","")) == "日勤"]
yashin  = [c for c in cases if time_to_shift(c.get("time","")) == "夜勤"]
n = len(cases)
st.markdown(f"**📞 登録済み: {n}件（日勤 {len(nisshin)}件 / 夜勤 {len(yashin)}件）**")

# ===== 症例登録フォーム =====
st.divider()
st.subheader("➕ 症例登録")

from datetime import timezone as _tz, timedelta as _td
_jst_now = datetime.now(_tz(_td(hours=9)))
cc1, cc2 = st.columns(2)
with cc1:
    _rounded = f"{_jst_now.hour:02d}:{(_jst_now.minute // 5) * 5:02d}"
    _nearest_idx = TIME_OPTIONS.index(_rounded) if _rounded in TIME_OPTIONS else 0
    sel_time = st.selectbox("時刻", TIME_OPTIONS, index=_nearest_idx, key="dtd_inp_time")
    if sel_time:
        st.caption(f"→ **{time_to_shift(sel_time)}**")
    req_count = st.selectbox("依頼回数", ["初回","2回目","3回目","4回目以上"], key="dtd_req")
with cc2:
    hospital = st.text_input("依頼元病院", placeholder="○○病院", key="dtd_hospital")
    dept     = st.text_input("科", placeholder="循環器内科", key="dtd_dept")
    doctor   = st.text_input("医師名", placeholder="山田先生", key="dtd_doctor")

age    = st.number_input("年齢（才）", min_value=0, max_value=120, value=0, step=1, key="dtd_age")
gender = st.radio("性別", ["M","F","不明"], horizontal=True, key="dtd_gender")
summary = st.text_area("概略", height=60, placeholder="主訴・病態など", key="dtd_summary")

# 転帰
outcome = st.radio("転帰", ["搬入","お断り","院内他科案内","患者都合","その他"],
                   horizontal=True, key="dtd_outcome")

reason = reason1_sub = reason2_sub = reason3_sub = reason3_dept = ""
if outcome == "お断り":
    reason_sel = st.radio("お断り理由", [
        "1. 病床の都合がつかない",
        "2. マンパワーの問題",
        "3. 院内専門科の都合・体制",
    ], key="dtd_reason")

    if reason_sel.startswith("1."):
        reason = "1_満床"
        reason1_sub = st.radio("詳細", [
            "満床・満床に準ずる状態",
            "ICU個室(感染等)満床",
            "熱傷患者受入不能",
        ], horizontal=True, key="dtd_r1sub")
    elif reason_sel.startswith("2."):
        reason = "2_マンパワー"
        reason2_sub = st.radio("詳細", [
            "他患の処置・手術等で余力なし",
            "別の救急患者の搬入直前・直後",
        ], horizontal=True, key="dtd_r2sub")
    elif reason_sel.startswith("3."):
        reason = "3_院内専門科"
        reason3_dept = st.text_input("診療科名", placeholder="脳神経外科", key="dtd_r3dept")
        reason3_sub = st.radio("詳細", [
            "当該科手術中", "学会等で不在", "麻酔科対応不能",
        ], horizontal=True, key="dtd_r3sub")

if st.button("💾 症例を追加", type="primary", use_container_width=True):
    case = {
        "time": sel_time, "req_count": req_count,
        "hospital": hospital, "dept": dept, "doctor": doctor,
        "age": age if age > 0 else "", "gender": gender,
        "summary": summary, "outcome": outcome,
        "reason": reason, "reason1_sub": reason1_sub,
        "reason2_sub": reason2_sub, "reason3_sub": reason3_sub,
        "reason3_dept": reason3_dept,
    }
    st.session_state.dtd_cases.append(case)
    save_cases(st.session_state.dtd_cases)
    st.success(f"✅ 追加しました（合計{len(st.session_state.dtd_cases)}件）")
    st.rerun()

# ===== 登録済み症例リスト =====
if cases:
    st.divider()
    st.subheader("📋 登録済み症例")
    for idx, c in enumerate(cases):
        t = c.get("time","--:--")
        hosp = c.get("hospital","")
        oc = c.get("outcome","")
        shift = time_to_shift(t)
        icon = "🌕" if shift=="日勤" else "🌑"
        col1, col2 = st.columns([7,1])
        with col1:
            st.markdown(
                f"<div style='font-size:14px;padding:2px 0'>"
                f"{icon} {idx+1}. {t} {hosp} {c.get('dept','')} 転帰:{oc}</div>",
                unsafe_allow_html=True)
        with col2:
            if st.button("🗑️", key=f"dtd_del_{idx}"):
                st.session_state.dtd_cases.pop(idx)
                save_cases(st.session_state.dtd_cases)
                st.rerun()

# ===== 出力 =====
st.divider()
oc1, oc2 = st.columns(2)
with oc1:
    if st.button("🖨️ 受付対応表を生成", type="primary", use_container_width=True):
        date_str = input_date.strftime('%Y%m%d')
        all_images = []

        for shift_label, shift_cases in [("日勤", nisshin), ("夜勤", yashin)]:
            header_for_render = {"date": input_date.isoformat(),
                                 "shift": shift_label, "leader": leader}
            if not shift_cases:
                st.write(f"### 📄 {shift_label}（0件）")
                with st.spinner(f"{shift_label} 依頼なしシート生成中..."):
                    result = render_norequest(header_for_render)
                st.image(result, use_container_width=True)
                buf = io.BytesIO(); result.save(buf, format="JPEG", quality=95)
                all_images.append((f"dtd_{date_str}_{shift_label}_依頼なし.jpg",
                                   buf.getvalue()))
                components.html(dtd_make_print_widget(result, f"dtd_print_{shift_label}_none"), height=38)
                continue

            st.write(f"### 📄 {shift_label}（{len(shift_cases)}件）")
            n_sh = max(1, (len(shift_cases)+5)//6)
            for sh in range(n_sh):
                sheet_cases = shift_cases[sh*6:sh*6+6]
                with st.spinner(f"{shift_label} No.{sh+1} 生成中..."):
                    result = render_drtodr(header_for_render, sheet_cases, sheet_no=sh+1)
                st.write(f"**{shift_label} No.{sh+1}**（症例{sh*6+1}〜{min(sh*6+len(sheet_cases),len(shift_cases))}）")
                st.image(result, use_container_width=True)
                buf = io.BytesIO(); result.save(buf, format="JPEG", quality=95)
                fname = f"dtd_{date_str}_{shift_label}_No{sh+1}.jpg"
                all_images.append((fname, buf.getvalue()))
                components.html(dtd_make_print_widget(result, f"dtd_print_{shift_label}_{sh}"), height=38)

        st.session_state.dtd_images = all_images
        st.success(f"✅ {len(all_images)}枚を生成しました。")

    # PDF一括保存
    if st.session_state.get("dtd_images"):
        try:
            from reportlab.pdfgen import canvas as rl_canvas
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.utils import ImageReader
            from PIL import Image as PILImage

            A4_W, A4_H = A4
            MARGIN = 28
            avail_w = A4_W - 2*MARGIN; avail_h = A4_H - 2*MARGIN

            pdf_buf = io.BytesIO()
            c = rl_canvas.Canvas(pdf_buf, pagesize=A4)
            for _, img_bytes in st.session_state.dtd_images:
                img = PILImage.open(io.BytesIO(img_bytes)).convert("RGB")
                iw, ih = img.size
                scale = min(avail_w/iw, avail_h/ih)
                pw, ph = iw*scale, ih*scale
                x = MARGIN + (avail_w-pw)/2; y = MARGIN + (avail_h-ph)/2
                ib = io.BytesIO(); img.save(ib, format="JPEG", quality=95); ib.seek(0)
                c.drawImage(ImageReader(ib), x, y, width=pw, height=ph)
                c.showPage()
            c.save(); pdf_buf.seek(0)
            pdf_name = f"dtd_{input_date.strftime('%Y%m%d')}.pdf"
            st.download_button(
                "📄 全受付対応表をPDFで保存（A4印刷用）",
                pdf_buf.getvalue(), pdf_name, "application/pdf",
                use_container_width=True, type="primary", key="dtd_pdf_dl"
            )
        except Exception as e:
            st.error(f"PDF生成エラー: {e}")

with oc2:
    if st.button("🗑️ 全症例をリセット", use_container_width=True):
        st.session_state.dtd_cases = []
        st.session_state.dtd_images = []
        save_cases([])
        st.rerun()

# ===== 勤務表リーダー設定 =====
st.divider()
with st.expander("📅 勤務表リーダー設定", expanded=False):
    from datetime import timezone as _stz2, timedelta as _std2
    _now_dtd = datetime.now(_stz2(_std2(hours=9)))
    _sh_dtd = "日勤" if 8*60+30 <= _now_dtd.hour*60+_now_dtd.minute < 16*60+30 else "夜勤"
    _ld_dtd = get_leader(input_date, _sh_dtd)
    if _ld_dtd:
        st.info(f"👤 {input_date.month}/{input_date.day} {_sh_dtd}のリーダー: **{_ld_dtd}**")
    else:
        st.warning(f"⚠️ {input_date.month}/{input_date.day} {_sh_dtd}のリーダーが未設定です")
    schedule_editor_widget("dtd_sched")
