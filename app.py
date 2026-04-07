import streamlit as st
import streamlit.components.v1 as components
import random
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import os

# --- 1. ページ設定 ---
st.set_page_config(page_title="英単語マスター", page_icon="🎓", layout="centered")

# --- 2. 音声再生用JavaScript ---
def text_to_speech(text):
    if text:
        js_code = f"""
            <script>
            (function() {{
                window.speechSynthesis.cancel();
                var msg = new SpeechSynthesisUtterance();
                msg.text = "{text}";
                msg.lang = "en-US";
                msg.rate = 1.0;
                window.speechSynthesis.speak(msg);
            }})();
            </script>
        """
        components.html(js_code, height=0)

# --- 3. スタイル設定（問題文をさらに大きく） ---
def set_ui_style():
    st.markdown("""
        <style>
        /* 問題文ボタンのスタイル：以前のレイアウトを維持しつつ巨大化 */
        .stButton > button[kind="secondary"] {
            border: none !important;
            background-color: transparent !important;
            padding: 20px 0 !important;
            color: #31333F !important;
            text-align: center !important; /* 中央寄せでインパクトを出す */
            font-size: 3.5rem !important;  /* さらに大きく */
            font-weight: 800 !important;
            display: block !important;
            width: 100% !important;
            line-height: 1.1 !important;
        }
        .stButton > button[kind="secondary"]:active {
            opacity: 0.7;
        }
        /* ステータス情報の微調整 */
        .status-text {
            font-size: 0.9rem;
            color: #666;
            text-align: center;
            margin-bottom: 5px;
        }
        </style>
    """, unsafe_allow_html=True)

# --- 4. スプレッドシート連携 ---
@st.cache_resource
def get_sheet():
    try:
        raw_key = st.secrets["json_key"].strip().lstrip('.')
        info = json.loads(raw_key)
        if "private_key" in info:
            info["private_key"] = info["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        return gspread.authorize(creds).open_by_key(st.secrets["spreadsheet_id"]).sheet1
    except: return None

@st.cache_data(ttl=5)
def load_gs_data():
    sheet = get_sheet()
    if not sheet: return []
    try:
        data = sheet.get_all_values()
        if len(data) < 2: return []
        return [{'en': r[0], 'ja': r[1], 'count': r[2], 'no': r[3], 'total_shown': r[4], 'is_done': r[5]} for r in data[1:] if len(r) >= 2]
    except: return []

def sync_result(word_dict, res_type):
    sheet = get_sheet()
    if not sheet: return
    try:
        en_target = str(word_dict['en']).strip()
        all_col1 = [str(x).strip() for x in sheet.col_values(1)]
        if en_target in all_col1:
            row_idx = all_col1.index(en_target) + 1
            row_data = sheet.row_values(row_idx)
            try: old_s = int(float(str(row_data[4]))) if len(row_data) > 4 else 0
            except: old_s = 0
            sheet.update_cell(row_idx, 5, old_s + 1)
            if res_type == 'ok':
                try: old_c = int(float(str(row_data[2]))) if len(row_data) > 2 else 0
                except: old_c = 0
                new_c = old_c + 1
                sheet.update_cell(row_idx, 3, 5 if new_c >= 5 else new_c)
                if new_c >= 5: sheet.update_cell(row_idx, 6, 1)
            else:
                sheet.update_cell(row_idx, 3, 0); sheet.update_cell(row_idx, 6, 0)
    except: pass
    st.cache_data.clear()

# --- 5. データロードと開始画面 ---
set_ui_style()

if 'all_words' not in st.session_state:
    df = pd.read_csv("words.csv")
    df['no'] = pd.to_numeric(df['no'], errors='coerce').fillna(0)
    st.session_state.all_words = df.to_dict('records')

if 'started' not in st.session_state:
    st.session_state.started = False

if not st.session_state.started:
    st.title("🎓 英単語マスター")
    if st.button("🚀 学習を始める (音声を許可)", use_container_width=True):
        st.session_state.started = True
        st.rerun()
    st.stop()

# --- 6. データ管理とサイドバー ---
gs_rows = load_gs_data()
pending_words = [d for d in gs_rows if d.get('en') and str(d.get('is_done', 0)) != '1']
gs_dict = {str(d.get('en')).strip(): d for d in gs_rows if d.get('en')}

st.sidebar.title("🎓 学習メニュー")
mode = st.sidebar.selectbox("モード", ["英→日クイズ", "日→英クイズ", "単語帳"])
st.sidebar.divider()
st.sidebar.metric("復習が必要な単語数", f"{len(pending_words)} 語")

if mode != "単語帳":
    nos = [int(w['no']) for w in st.session_state.all_words] or [0]
    col1, col2 = st.sidebar.columns(2)
    with col1: s_no = st.number_input("開始No.", min(nos), max(nos), min(nos))
    with col2: e_no = st.number_input("終了No.", min(nos), max(nos), max(nos))
    quiz_target = st.sidebar.radio("出題対象", ["全問", "復習のみ"], horizontal=True)

    if st.sidebar.button("🔄 出題頻度のみリセット", use_container_width=True):
        sheet = get_sheet()
        if sheet:
            rows = len(sheet.get_all_values())
            if rows > 1:
                cell_list = sheet.range(2, 5, rows, 5); [setattr(c, 'value', 0) for c in cell_list]
                sheet.update_cells(cell_list)
            st.cache_data.clear(); st.session_state.reset_q = True; st.rerun()

# --- 7. クイズ表示ロジック ---
if mode == "単語帳":
    st.title("📖 単語帳")
    st.dataframe(pd.DataFrame(st.session_state.all_words)[['no', 'en', 'ja']], hide_index=True)
else:
    active_list = pending_words if quiz_target == "復習のみ" else [w for w in st.session_state.all_words if s_no <= w['no'] <= e_no]
    
    if 'q' not in st.session_state or st.session_state.get('reset_q'):
        if not active_list: st.warning("対象なし"); st.stop()
        target = random.choice(active_list)
        others = random.sample([w for w in st.session_state.all_words if w['en'] != target['en']], 3)
        choices = others + [target]; random.shuffle(choices)
        st.session_state.q = {"t": target, "c": choices, "ans": False}
        st.session_state.reset_q = False
        text_to_speech(target['en'])

    q = st.session_state.q
    match = gs_dict.get(str(q['t']['en']).strip(), {})
    
    # --- ステータス表示の強化 ---
    display_no = int(float(q['t'].get('no', 0)))
    try: curr_ok = int(float(str(match.get('count', 0)).strip())) if match else 0
    except: curr_ok = 0
    
    # 画面上部に情報を集約
    st.markdown(f"""
        <p class="status-text">
            No.{display_no} | 🔄 復習残り: {len(pending_words)}語 | 🔥 あと {max(0, 5 - curr_ok)} 回正解で完了
        </p>
    """, unsafe_allow_html=True)

    # --- 巨大化した問題文ボタン ---
    display_text = q['t']['en'] if mode == '英→日クイズ' else q['t']['ja']
    if st.button(display_text, key="q_text_btn"):
        text_to_speech(q['t']['en'])

    # 選択肢
    if not q["ans"]:
        st.write("") 
        cols = st.columns(2)
        for i, c in enumerate(q["c"]):
            label = c['ja'] if mode == "英→日クイズ" else c['en']
            with cols[i % 2]:
                if st.button(label, key=f"b{i}", use_container_width=True):
                    q["ans"] = True
                    st.session_state.res_type = "ok" if c['en'] == q['t']['en'] else "ng"
                    sync_result(q['t'], st.session_state.res_type)
                    st.rerun()
        if st.button("❓ わからない", use_container_width=True):
            q["ans"] = True; st.session_state.res_type = "unknown"; sync_result(q['t'], "unknown"); st.rerun()
    else:
        res = st.session_state.res_type
        if res == "ok":
            st.success(f"🎯 正解！ {q['t']['en']} : {q['t']['ja']}")
        else:
            st.error(f"答え: {q['t']['en']} : {q['t']['ja']}")
        
        if st.button("次の問題へ ➡️", use_container_width=True):
            st.session_state.reset_q = True; st.rerun()

        st.divider()
        for choice in q["c"]:
            mark = "✅" if choice['en'] == q['t']['en'] else "・"
            st.write(f"{mark} **{choice['en']}** : {choice['ja']}")