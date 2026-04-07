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

# --- 2. 発音用JavaScript関数 ---
def text_to_speech(text):
    if text:
        js_code = f"""
            <script>
            window.speechSynthesis.cancel();
            var msg = new SpeechSynthesisUtterance();
            msg.text = "{text}";
            msg.lang = "en-US";
            msg.rate = 1.0;
            window.speechSynthesis.speak(msg);
            </script>
        """
        components.html(js_code, height=0)

# --- 3. スタイル設定 ---
st.markdown("""
    <style>
    div.stButton > button:first-child {
        border-radius: 10px;
    }
    /* 📢ボタン用のコンパクト設定 */
    .stButton button {
        padding: 0.2rem 0.5rem !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- 4. Googleスプレッドシート連携 ---
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
            # 出題数更新
            try: old_s = int(float(str(row_data[4]))) if len(row_data) > 4 else 0
            except: old_s = 0
            sheet.update_cell(row_idx, 5, old_s + 1)
            # 正解数更新
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

# --- 5. データロードと開始判定 ---
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

# --- 6. クイズ生成 ---
gs_rows = load_gs_data()
gs_dict = {str(d['en']).strip(): d for d in gs_rows}
mode = st.sidebar.selectbox("モード", ["英→日クイズ", "日→英クイズ"])

if 'q' not in st.session_state or st.session_state.get('reset_q'):
    target = random.choice(st.session_state.all_words)
    others = random.sample([w for w in st.session_state.all_words if w['en'] != target['en']], 3)
    choices = others + [target]; random.shuffle(choices)
    st.session_state.q = {"t": target, "c": choices, "ans": False}
    st.session_state.reset_q = False
    text_to_speech(target['en']) # 出題時に自動再生

q = st.session_state.q

# --- 7. 画面表示 ---
st.write(f"No.{int(float(q['t']['no']))}")

col_txt, col_btn = st.columns([0.85, 0.15])
with col_txt:
    st.markdown(f"## {q['t']['en'] if mode == '英→日クイズ' else q['t']['ja']}")
with col_btn:
    if st.button("📢", key="speech"):
        text_to_speech(q['t']['en'])

if not q["ans"]:
    cols = st.columns(2)
    for i, c in enumerate(q["c"]):
        with cols[i % 2]:
            if st.button(c['ja'] if mode == "英→日クイズ" else c['en'], key=f"b{i}", use_container_width=True):
                q["ans"] = True
                is_correct = (str(c['en']).strip() == str(q['t']['en']).strip())
                st.session_state.res_type = "ok" if is_correct else "ng"
                sync_result(q['t'], st.session_state.res_type)
                st.rerun()
    if st.button("❓ わからない", use_container_width=True):
        q["ans"] = True; st.session_state.res_type = "unknown"
        sync_result(q['t'], "unknown"); st.rerun()
else:
    if st.session_state.res_type == "ok":
        st.success(f"🎯 正解！ {q['t']['en']} : {q['t']['ja']}")
    else:
        st.error(f"答え: {q['t']['en']} : {q['t']['ja']}")
    
    if st.button("次の問題へ ➡️", use_container_width=True):
        st.session_state.reset_q = True
        st.rerun()
    
    # 選択肢のまとめ
    for choice in q["c"]:
        mark = "✅" if choice['en'] == q['t']['en'] else "・"
        st.write(f"{mark} **{choice['en']}** : {choice['ja']}")