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

def _gh_config(repo_secret="RECORDS_REPO", default_repo="gateofzen/triage-storage"):
    """GitHub保存設定をStreamlit Secretsから取得"""
    try:
        import streamlit as st
        token = st.secrets.get("GITHUB_TOKEN", st.secrets.get("SCHEDULE_TOKEN", ""))
        repo  = st.secrets.get(repo_secret, default_repo)
        return token, repo
    except Exception:
        return "", ""

def _gh_get_sha(token, repo, filename):
    try:
        import urllib.request
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/contents/{filename}",
            headers={"Authorization": f"Bearer {token}",
                     "Accept": "application/vnd.github.v3+json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())["sha"]
    except Exception:
        return None

def _gh_push(token, repo, filename, data):
    if not token: return False
    try:
        import urllib.request, base64 as _b64
        content = _b64.b64encode(
            json.dumps(data, ensure_ascii=False, indent=2).encode()).decode()
        sha = _gh_get_sha(token, repo, filename)
        payload = {"message": f"update {filename}", "content": content}
        if sha: payload["sha"] = sha
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/contents/{filename}",
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {token}",
                     "Accept": "application/vnd.github.v3+json",
                     "Content-Type": "application/json"},
            method="PUT")
        with urllib.request.urlopen(req, timeout=15): pass
        return True
    except Exception:
        return False

def _gh_pull(token, repo, filename):
    if not token: return None
    try:
        import urllib.request, base64 as _b64
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/contents/{filename}",
            headers={"Authorization": f"Bearer {token}",
                     "Accept": "application/vnd.github.v3+json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = json.loads(r.read())
        return json.loads(_b64.b64decode(raw["content"].replace("\n","")).decode())
    except Exception:
        return None

CASES_FILE = "dtd_cases.json"
_DTD_REPO_SECRET = "RECORDS_REPO"
_DTD_DEFAULT_REPO = "gateofzen/triage-storage"

def load_cases():
    token, repo = _gh_config(_DTD_REPO_SECRET, _DTD_DEFAULT_REPO)
    if token:
        data = _gh_pull(token, repo, CASES_FILE)
        if data is not None:
            try:
                with open(CASES_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception: pass
            return data
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
    token, repo = _gh_config(_DTD_REPO_SECRET, _DTD_DEFAULT_REPO)
    if token: _gh_push(token, repo, CASES_FILE, cases)


# ===== 時刻から勤務帯判定 =====
def time_to_shift(time_str):
    """時刻文字列から日勤/夜勤を判定"""
    if not time_str or ":" not in time_str: return ""
    try:
        h, m = map(int, time_str.split(":"))
        mins = h*60 + m
        return "日勤" if 8*60+30 <= mins < 16*60+30 else "夜勤"
    except:
        return ""

def get_shift_date(case_date_str, time_str):
    """症例の時刻が00:00-08:30の場合は前日夜勤扱い"""
    try:
        from datetime import date as _d, timedelta
        h, m = map(int, time_str.split(":"))
        base = _d.fromisoformat(case_date_str)
        if h*60+m < 8*60+30:
            return (base - timedelta(days=1)).isoformat()
        return case_date_str
    except:
        return case_date_str

DTD_TRASH_FILE = "dtd_trash.json"

def load_dtd_trash():
    token, repo = _gh_config(_DTD_REPO_SECRET, _DTD_DEFAULT_REPO)
    if token:
        data = _gh_pull(token, repo, DTD_TRASH_FILE)
        if data is not None:
            try:
                with open(DTD_TRASH_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except: pass
            return data
    if os.path.exists(DTD_TRASH_FILE):
        try:
            with open(DTD_TRASH_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: return []
    return []

def save_dtd_trash(trash):
    try:
        with open(DTD_TRASH_FILE, "w", encoding="utf-8") as f:
            json.dump(trash, f, ensure_ascii=False, indent=2)
    except: pass
    token, repo = _gh_config(_DTD_REPO_SECRET, _DTD_DEFAULT_REPO)
    if token: _gh_push(token, repo, DTD_TRASH_FILE, trash)

def move_dtd_to_trash(cases_list):
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    trash = load_dtd_trash()
    now_str = _dt.now(_tz(_td(hours=9))).isoformat()
    for c in cases_list:
        trash.append({"case": c, "deleted_at": now_str})
    save_dtd_trash(trash)

def purge_dtd_expired_trash():
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    trash = load_dtd_trash()
    now = _dt.now(_tz(_td(hours=9)))
    kept = [t for t in trash if (now - _dt.fromisoformat(t["deleted_at"])).total_seconds() < 86400]
    if len(kept) != len(trash):
        save_dtd_trash(kept)
    return kept

def auto_archive_old_shifts_dtd():
    """現在のシフトと異なる症例を自動的にゴミ箱に移動"""
    from datetime import date as _dcls, timedelta as _tdcls, datetime as _dtcls, timezone as _tzcls
    cases = load_cases()
    if not cases:
        return
    _now = _dtcls.now(_tzcls(_tdcls(hours=9)))
    _now_min = _now.hour * 60 + _now.minute
    _today = _now.date()
    if _now_min < 8*60+30:
        cur_shift_date = (_today - _tdcls(days=1)).isoformat()
        cur_shift = "夜勤"
    elif _now_min < 16*60+30:
        cur_shift_date = _today.isoformat()
        cur_shift = "日勤"
    else:
        cur_shift_date = _today.isoformat()
        cur_shift = "夜勤"
    kept = []
    to_archive = []
    for c in cases:
        c_date = c.get("date", "")
        c_time = c.get("time", "")
        c_shift = time_to_shift(c_time)
        c_shift_date = get_shift_date(c_date, c_time) if c_date else ""
        if c_shift_date == cur_shift_date and c_shift == cur_shift:
            kept.append(c)
        elif c_date == "" or c_time == "":
            kept.append(c)
        else:
            to_archive.append(c)
    if to_archive:
        move_dtd_to_trash(to_archive)
        save_cases(kept)

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
    purge_dtd_expired_trash()
    auto_archive_old_shifts_dtd()
    st.session_state.dtd_cases = load_cases()
if "dtd_images" not in st.session_state:
    st.session_state.dtd_images = []
if "dtd_shift_images" not in st.session_state:
    st.session_state.dtd_shift_images = {}
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
if "dtd_show_form" not in st.session_state:
    st.session_state.dtd_show_form = False

if not st.session_state.dtd_show_form:
    if st.button("➕ 症例を登録する", type="primary", use_container_width=True):
        st.session_state.dtd_show_form = True
        st.rerun()
else:
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
                "満床・満床に準ずる状態", "ICU個室(感染等)満床", "熱傷患者受入不能",
            ], horizontal=True, key="dtd_r1sub")
        elif reason_sel.startswith("2."):
            reason = "2_マンパワー"
            reason2_sub = st.radio("詳細", [
                "他患の処置・手術等で余力なし", "別の救急患者の搬入直前・直後",
            ], horizontal=True, key="dtd_r2sub")
        elif reason_sel.startswith("3."):
            reason = "3_院内専門科"
            reason3_dept = st.text_input("診療科名", placeholder="脳神経外科", key="dtd_r3dept")
            reason3_sub = st.radio("詳細", [
                "当該科手術中", "学会等で不在", "麻酔科対応不能",
            ], horizontal=True, key="dtd_r3sub")

    bc1, bc2 = st.columns(2)
    with bc1:
        if st.button("💾 症例を追加", type="primary", use_container_width=True):
            case = {
                "date": input_date.isoformat(),
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
            st.session_state.dtd_show_form = False
            st.rerun()
    with bc2:
        if st.button("❌ キャンセル", use_container_width=True, key="dtd_cancel"):
            st.session_state.dtd_show_form = False
            st.rerun()

# ===== 登録済み症例リスト =====
if "dtd_editing" not in st.session_state:
    st.session_state.dtd_editing = None

if cases:
    st.divider()
    st.subheader("📋 登録済み症例")
    for idx, c in enumerate(cases):
        t = c.get("time","--:--")
        hosp = c.get("hospital","")
        oc = c.get("outcome","")
        shift = time_to_shift(t)
        icon = "🌕" if shift=="日勤" else "🌑"
        col1, col2, col3 = st.columns([6,1,1])
        with col1:
            st.markdown(
                f"<div style='font-size:14px;padding:2px 0'>"
                f"{icon} {idx+1}. {t} {hosp} {c.get('dept','')} 転帰:{oc}</div>",
                unsafe_allow_html=True)
        with col2:
            if st.button("✏️", key=f"dtd_edit_{idx}", help="編集"):
                st.session_state.dtd_editing = idx
                st.session_state.dtd_show_form = False
                st.rerun()
        with col3:
            if st.button("🗑️", key=f"dtd_del_{idx}", help="削除"):
                move_dtd_to_trash([st.session_state.dtd_cases[idx]])
                st.session_state.dtd_cases.pop(idx)
                save_cases(st.session_state.dtd_cases)
                if st.session_state.dtd_editing == idx:
                    st.session_state.dtd_editing = None
                st.rerun()

# ===== 編集フォーム =====
edit_idx = st.session_state.dtd_editing
if edit_idx is not None and 0 <= edit_idx < len(cases):
    st.divider()
    st.subheader(f"✏️ 症例 {edit_idx+1} を編集")
    ec = cases[edit_idx]
    ecc1, ecc2 = st.columns(2)
    with ecc1:
        e_time = st.selectbox("時刻", TIME_OPTIONS,
            index=TIME_OPTIONS.index(ec.get("time","")) if ec.get("time","") in TIME_OPTIONS else 0,
            key="dtd_e_time")
        e_req = st.selectbox("依頼回数", ["初回","2回目","3回目","4回目以上"],
            index=["初回","2回目","3回目","4回目以上"].index(ec.get("req_count","初回")) if ec.get("req_count","初回") in ["初回","2回目","3回目","4回目以上"] else 0,
            key="dtd_e_req")
    with ecc2:
        e_hospital = st.text_input("依頼元病院", value=ec.get("hospital",""), key="dtd_e_hospital")
        e_dept     = st.text_input("科", value=ec.get("dept",""), key="dtd_e_dept")
        e_doctor   = st.text_input("医師名", value=ec.get("doctor",""), key="dtd_e_doctor")
    e_age    = st.number_input("年齢（才）", min_value=0, max_value=120,
                               value=int(ec.get("age",0)) if ec.get("age","") != "" else 0,
                               step=1, key="dtd_e_age")
    e_gender = st.radio("性別", ["M","F","不明"],
                        index=["M","F","不明"].index(ec.get("gender","M")) if ec.get("gender","M") in ["M","F","不明"] else 0,
                        horizontal=True, key="dtd_e_gender")
    e_summary = st.text_area("概略", value=ec.get("summary",""), height=60, key="dtd_e_summary")
    e_outcome = st.radio("転帰", ["搬入","お断り","院内他科案内","患者都合","その他"],
                         index=["搬入","お断り","院内他科案内","患者都合","その他"].index(ec.get("outcome","搬入")) if ec.get("outcome","搬入") in ["搬入","お断り","院内他科案内","患者都合","その他"] else 0,
                         horizontal=True, key="dtd_e_outcome")
    e_reason = e_reason1_sub = e_reason2_sub = e_reason3_sub = e_reason3_dept = ""
    if e_outcome == "お断り":
        e_reason_opts = ["1. 病床の都合がつかない","2. マンパワーの問題","3. 院内専門科の都合・体制"]
        cur_r = ec.get("reason","")
        cur_r_sel = e_reason_opts[0] if cur_r=="1_満床" else e_reason_opts[1] if cur_r=="2_マンパワー" else e_reason_opts[2] if cur_r=="3_院内専門科" else e_reason_opts[0]
        e_reason_sel = st.radio("お断り理由", e_reason_opts,
                                index=e_reason_opts.index(cur_r_sel), key="dtd_e_reason")
        if e_reason_sel.startswith("1."):
            e_reason = "1_満床"
            e_reason1_sub = st.radio("詳細",["満床・満床に準ずる状態","ICU個室(感染等)満床","熱傷患者受入不能"],
                                     horizontal=True, key="dtd_e_r1sub")
        elif e_reason_sel.startswith("2."):
            e_reason = "2_マンパワー"
            e_reason2_sub = st.radio("詳細",["他患の処置・手術等で余力なし","別の救急患者の搬入直前・直後"],
                                     horizontal=True, key="dtd_e_r2sub")
        elif e_reason_sel.startswith("3."):
            e_reason = "3_院内専門科"
            e_reason3_dept = st.text_input("診療科名", value=ec.get("reason3_dept",""), key="dtd_e_r3dept")
            e_reason3_sub = st.radio("詳細",["当該科手術中","学会等で不在","麻酔科対応不能"],
                                     horizontal=True, key="dtd_e_r3sub")
    ebc1, ebc2 = st.columns(2)
    with ebc1:
        if st.button("💾 保存", type="primary", use_container_width=True, key="dtd_e_save"):
            st.session_state.dtd_cases[edit_idx] = {
                "time": e_time, "req_count": e_req,
                "hospital": e_hospital, "dept": e_dept, "doctor": e_doctor,
                "age": e_age if e_age > 0 else "", "gender": e_gender,
                "summary": e_summary, "outcome": e_outcome,
                "reason": e_reason, "reason1_sub": e_reason1_sub,
                "reason2_sub": e_reason2_sub, "reason3_sub": e_reason3_sub,
                "reason3_dept": e_reason3_dept,
            }
            save_cases(st.session_state.dtd_cases)
            st.session_state.dtd_editing = None
            st.rerun()
    with ebc2:
        if st.button("❌ キャンセル", use_container_width=True, key="dtd_e_cancel"):
            st.session_state.dtd_editing = None
            st.rerun()

# ===== 出力 =====
st.divider()

# 生成済み画像を表示（rerun後も永続）
if st.session_state.get("dtd_shift_images"):
    _stored2 = st.session_state.dtd_shift_images
    from datetime import timezone as _dz2, timedelta as _dtd3
    _d2_now = __import__('datetime').datetime.now(_dz2(_dtd3(hours=9)))
    _d2_min = _d2_now.hour * 60 + _d2_now.minute
    _disp_order2 = ["日勤","夜勤"] if 10 * 60 <= _d2_min < 18 * 60 else ["夜勤","日勤"]
    for _sl2 in _disp_order2:
        _imgs2  = _stored2.get(_sl2, [])
        _hdate2 = _stored2.get(f"{_sl2}_date", input_date.isoformat())
        _hldr2  = _stored2.get(f"{_sl2}_leader","")
        if _imgs2:
            import base64 as _b64d
            _b64_list2 = [_b64d.b64encode(ib).decode() for _, ib in _imgs2]
            _json2 = "[" + ",".join([f'"{p}"' for p in _b64_list2]) + "]"
            _hd2 = __import__('datetime').date.fromisoformat(_hdate2)
            _lbl2 = f"🖨️ {_hd2.month}/{_hd2.day} {_sl2}（{_hldr2}）印刷（{len(_imgs2)}枚）"
            _html2 = f"""<!DOCTYPE html><html><head><style>
@page{{size:A4;margin:0}}
body{{margin:0;padding:0;font-family:sans-serif}}
@media screen{{
.btn{{display:block;width:100%;height:38px;padding:0 14px;box-sizing:border-box;
  background:transparent;color:inherit;border:1px solid rgba(49,51,63,0.2);
  border-radius:4px;font-size:0.875rem;cursor:pointer}}
.btn:hover{{border-color:#f63366;color:#f63366}}
@media(prefers-color-scheme:dark){{.btn{{border-color:rgba(250,250,250,0.2);color:#fff}}}}
.imgs{{display:none}}}}
@media print{{.btn{{display:none}}.imgs{{display:block}}
.page{{page-break-after:always;width:100%;height:100vh;overflow:hidden}}
.page:last-child{{page-break-after:avoid}}
img{{width:100%;height:auto;max-height:100vh;display:block}}}}
</style></head><body>
<div class="imgs" id="cd{_sl2}"></div>
<button class="btn" onclick="window.print()">{_lbl2}</button>
<script>
var pages={_json2};
var c=document.getElementById('cd{_sl2}');
pages.forEach(function(b64){{var div=document.createElement('div');div.className='page';
var img=document.createElement('img');img.src='data:image/jpeg;base64,'+b64;
div.appendChild(img);c.appendChild(div);}});
</script></body></html>"""
            components.html(_html2, height=46)
            st.markdown(f"**📄 {_sl2}（{len(_imgs2)}枚）**")
            for _fn2, _ib2 in _imgs2:
                st.image(_ib2, use_container_width=True)

oc1, oc2 = st.columns(2)
with oc1:
    if st.button("🖨️ 受付対応表を生成", type="primary", use_container_width=True):
        date_str = input_date.strftime('%Y%m%d')
        shift_images2 = {}

        from datetime import timezone as _oz2, timedelta as _otd2
        _o2_now = __import__('datetime').datetime.now(_oz2(_otd2(hours=9)))
        _o2_min = _o2_now.hour * 60 + _o2_now.minute
        if 10 * 60 <= _o2_min < 18 * 60:
            _shift_order2 = [("日勤", nisshin), ("夜勤", yashin)]
        else:
            _shift_order2 = [("夜勤", yashin), ("日勤", nisshin)]
        for shift_label, shift_cases in _shift_order2:
            _sched_leader = get_leader(input_date, shift_label)
            _shift_leader = _sched_leader if _sched_leader else leader
            header_for_render = {"date": input_date.isoformat(),
                                 "shift": shift_label, "leader": _shift_leader}
            shift_imgs2 = []
            if not shift_cases:
                with st.spinner(f"{shift_label} 依頼なしシート生成中..."):
                    result = render_norequest(header_for_render)
                buf = io.BytesIO(); result.save(buf, format="JPEG", quality=95)
                shift_imgs2.append((f"dtd_{date_str}_{shift_label}_依頼なし.jpg", buf.getvalue()))
            else:
                n_sh = max(1, (len(shift_cases)+5)//6)
                for sh in range(n_sh):
                    sheet_cases = shift_cases[sh*6:sh*6+6]
                    with st.spinner(f"{shift_label} No.{sh+1} 生成中..."):
                        result = render_drtodr(header_for_render, sheet_cases, sheet_no=sh+1)
                    buf = io.BytesIO(); result.save(buf, format="JPEG", quality=95)
                    shift_imgs2.append((f"dtd_{date_str}_{shift_label}_No{sh+1}.jpg", buf.getvalue()))

            shift_images2[shift_label] = shift_imgs2
            shift_images2[f"{shift_label}_date"] = input_date.isoformat()
            shift_images2[f"{shift_label}_leader"] = _shift_leader

        st.session_state.dtd_shift_images = shift_images2
        st.session_state.dtd_images = [(f,b) for sl in ["日勤","夜勤"] for f,b in shift_images2.get(sl,[])]
        st.rerun()

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
    if "dtd_confirm_clear" not in st.session_state:
        st.session_state.dtd_confirm_clear = False
    if not st.session_state.dtd_confirm_clear:
        if st.button("🗑️ 全症例をリセット", use_container_width=True):
            st.session_state.dtd_confirm_clear = True
            st.rerun()
    else:
        st.warning("⚠️ 全症例をゴミ箱に移動します。24時間以内なら復元可能です。")
        dc1, dc2 = st.columns(2)
        with dc1:
            if st.button("✅ ゴミ箱に移動", type="primary", use_container_width=True):
                move_dtd_to_trash(st.session_state.dtd_cases)
                st.session_state.dtd_cases = []
                st.session_state.dtd_images = []
                st.session_state.dtd_shift_images = {}
                save_cases([])
                st.session_state.dtd_confirm_clear = False
                st.rerun()
        with dc2:
            if st.button("❌ キャンセル", use_container_width=True, key="dtd_cancel_clear"):
                st.session_state.dtd_confirm_clear = False
                st.rerun()

# ===== ゴミ箱 =====
_dtd_trash = purge_dtd_expired_trash()
if _dtd_trash:
    with st.expander(f"🗑️ ゴミ箱（{len(_dtd_trash)}件・24時間以内なら復元可）", expanded=False):
        from datetime import datetime as _dtdc, timezone as _tzdc, timedelta as _tddc
        _now_dtd_t = _dtdc.now(_tzdc(_tddc(hours=9)))
        for _di, _dt_t in enumerate(_dtd_trash):
            _dc = _dt_t["case"]
            _dname = f"{_dc.get('date','')} {_dc.get('time','')} {_dc.get('hospital','')} {_dc.get('summary','')[:15]}"
            try:
                _ddel = _dtdc.fromisoformat(_dt_t["deleted_at"])
                _dremain = 24 - (_now_dtd_t - _ddel).total_seconds() / 3600
                _dremain_str = f"あと{_dremain:.0f}時間"
            except: _dremain_str = ""
            _dcol1, _dcol2 = st.columns([7, 2])
            with _dcol1:
                st.markdown(f"<div style='font-size:13px'>{_dname}　<span style='color:#888'>（{_dremain_str}で完全削除）</span></div>", unsafe_allow_html=True)
            with _dcol2:
                if st.button("↩️ 復元", key=f"dtd_restore_{_di}", use_container_width=True):
                    full = load_dtd_trash()
                    restored = full.pop(_di)
                    save_dtd_trash(full)
                    st.session_state.dtd_cases.append(restored["case"])
                    save_cases(st.session_state.dtd_cases)
                    st.success("✅ 復元しました")
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
