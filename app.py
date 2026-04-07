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

# --- 2. 究極の音声再生関数 (ブラウザの制限を回避) ---
def text_to_speech(text):
    if text:
        # 以前のiframe方式ではなく、ページに直接JSを注入して即座に実行
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
        # 毎回ユニークなKeyを持たせることで再描画・再実行を強制
        components.html(js_code, height=0)

# --- 3. スタイル設定 ---
st.markdown("""
    <style>
    /* 📢ボタンを押しやすく */
    .stButton button {
        border-radius: 20px;
    }
    </style>
""", unsafe_allow_html=True)

# --- 4. Googleスプレッドシート連携 (変更なし) ---
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

# --- 5. データの読み込み ---
if 'all_words' not in st.session_state:
    path = "words.csv"
    df = pd.read_csv(path); df['no'] = pd.to_numeric(df['no'], errors='coerce').fillna(0)
    st.session_state.all_words = df.to_dict('records')

if 'started' not in st.session_state:
    st.session_state.started = False

# --- 6. 開始画面 (スマホの音声権限取得用) ---
if not st.session_state.started:
    st.title("🎓 英単語マスター")
    st.info("スマホの方は【消音モード】を解除し、音量を上げてから開始してください。")
    if st.button("🔊 音声を許可して学習を始める", use_container_width=True):
        # このクリックでブラウザの音声ロックを解除するダミー音声を流す
        text_to_speech("Welcome") 
        st.session_state.started = True
        st.rerun()
    st.stop()

# --- 7. クイズロジック ---
gs_rows = load_gs_data()
gs_dict = {str(d['en']).strip(): d for d in gs_rows}
mode = st.sidebar.selectbox("モード", ["英→日クイズ", "日→英クイズ"])

# クイズ生成
if 'q' not in st.session_state or st.session_state.get('reset_q'):
    active_list = st.session_state.all_words # 簡易化のため全件対象
    target = random.choice(active_list)
    others = random.sample([w for w in active_list if w['en'] != target['en']], 3)
    choices = others + [target]; random.shuffle(choices)
    st.session_state.q = {"t": target, "c": choices, "ans": False}
    st.session_state.reset_q = False
    # 出題時の自動再生
    text_to_speech(target['en'])

q = st.session_state.q

# --- 8. 画面表示 ---
col_q, col_v = st.columns([0.8, 0.2])
with col_q:
    st.markdown(f"## {q['t']['en'] if mode == '英→日クイズ' else q['t']['ja']}")
with col_v:
    if st.button("📢", key="manual_v"):
        text_to_speech(q['t']['en'])

if not q["ans"]:
    cols = st.columns(2)
    for i, c in enumerate(q["c"]):
        with cols[i % 2]:
            if st.button(c['ja'] if mode == "英→日クイズ" else c['en'], key=f"b{i}", use_container_width=True):
                q["ans"] = True
                # 回答した瞬間に音を鳴らす（ユーザー操作に紐付ける）
                text_to_speech(q['t']['en'])
                st.rerun()
else:
    if st.button("次の問題へ ➡️", use_container_width=True):
        st.session_state.reset_q = True
        st.rerun()
    
    st.success(f"正解: {q['t']['en']} 【{q['t']['ja']}】")
    for choice in q["c"]:
        st.write(f"・ **{choice['en']}** : {choice['ja']}")