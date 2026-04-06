import streamlit as st
import random
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import os

# --- ページ設定 ---
st.set_page_config(page_title="英単語", layout="centered")

# --- CSSカスタマイズ (さらに凝縮) ---
st.markdown("""
    <style>
    .main .block-container { padding: 0.3rem 1rem !important; }
    /* 問題文のフォントサイズを2サイズアップ */
    .mondai-text { font-size: 2.2rem !important; font-weight: bold; margin: 0.2rem 0 !important; line-height: 1.2; }
    h3 { font-size: 0.8rem !important; margin: 0 !important; opacity: 0.7; }
    .stButton > button { height: 2.4rem !important; margin-bottom: -12px !important; font-size: 0.9rem !important; }
    hr { margin: 0.4rem 0 !important; }
    /* 選択肢まとめのテキストサイズ */
    .matome-text { font-size: 0.75rem !important; line-height: 1.1; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_resource
def get_spreadsheet():
    try:
        raw_key = st.secrets["json_key"].strip().lstrip('.')
        info = json.loads(raw_key)
        if "private_key" in info:
            info["private_key"] = info["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        sheet = gspread.authorize(creds).open_by_key(st.secrets["spreadsheet_id"]).sheet1
        if not sheet.get_all_values():
            sheet.append_row(["en", "ja", "count", "no"])
        return sheet
    except: return None

def load_wrong_words():
    sheet = get_spreadsheet()
    if sheet:
        try:
            data = sheet.get_all_records()
            return [d for d in data if d.get('en')]
        except: return []
    return []

def add_wrong_word_to_gs(word_dict):
    sheet = get_spreadsheet()
    if sheet:
        try:
            existing = sheet.col_values(1)
            if word_dict['en'] not in existing:
                sheet.append_row([word_dict['en'], word_dict['ja'], 0, int(word_dict.get('no', 0))])
        except: pass

def update_correct_count_in_gs(en_word):
    sheet = get_spreadsheet()
    if not sheet: return
    try:
        cell = sheet.find(en_word)
        if cell:
            val = sheet.cell(cell.row, 3).value
            count = int(val) if val and str(val).isdigit() else 0
            if count + 1 >= 5: sheet.delete_rows(cell.row)
            else: sheet.update_cell(cell.row, 3, count + 1)
    except: pass

@st.cache_data
def load_csv_data():
    path = "words.csv"
    if not os.path.exists(path): return []
    for enc in ['utf-8-sig', 'shift_jis', 'cp932']:
        try:
            df = pd.read_csv(path, encoding=enc)
            df.columns = df.columns.str.strip()
            return df.dropna(subset=['en', 'ja', 'no']).to_dict('records')
        except: continue
    return []

if 'all_words' not in st.session_state: st.session_state.all_words = load_csv_data()
st.session_state.wrong_words = load_wrong_words()

# --- サイドバー ---
main_mode = st.sidebar.radio("モード", ["クイズ", "単語帳"], horizontal=True)
if st.session_state.all_words:
    nos = [int(w['no']) for w in st.session_state.all_words]
    start_no = st.sidebar.number_input("開始", min(nos), max(nos), min(nos))
    end_no = st.sidebar.number_input("終了", min(nos), max(nos), max(nos))
    filtered = [w for w in st.session_state.all_words if start_no <= int(w['no']) <= end_no]
else: filtered = []

if main_mode == "クイズ":
    direction = st.sidebar.radio("方向", ["英→日", "日→英"], horizontal=True)
    st.sidebar.metric("復習中", f"{len(st.session_state.wrong_words)}語")
    q_target = st.sidebar.radio("対象", ["全問", "復習"], horizontal=True)
    if 'last_c' not in st.session_state or st.session_state.last_c != (direction, q_target, start_no, end_no):
        st.session_state.last_c = (direction, q_target, start_no, end_no)
        if 'current_q' in st.session_state: del st.session_state.current_q

# --- メイン ---
if main_mode == "単語帳":
    for w in filtered:
        st.write(f"{int(w['no'])}. **{w['en']}**: {w['ja']}")
        st.divider()

elif main_mode == "クイズ":
    active_list = st.session_state.wrong_words if (q_target == "復習" and st.session_state.wrong_words) else filtered
    if 'current_q' not in st.session_state:
        if not active_list: st.session_state.current_q = None
        else:
            target = random.choice(active_list)
            others = [w for w in st.session_state.all_words if w['en'] != target['en']]
            choices = random.sample(others, min(len(others), 3)) + [target]
            random.shuffle(choices)
            st.session_state.current_q = {"target": target, "choices": choices, "answered": False}

    if st.session_state.current_q is None:
        st.write("単語なし")
    else:
        q = st.session_state.current_q
        t = q['target']
        st.write(f"No.{t.get('no', '?')}")
        # 問題文を大きく表示
        q_label = t['en'] if direction=='英→日' else t['ja']
        st.markdown(f'<div class="mondai-text">{q_label}</div>', unsafe_allow_html=True)

        if not q["answered"]:
            cols = st.columns(2)
            for i, c in enumerate(q["choices"]):
                label = c['ja'] if direction == "英→日" else c['en']
                with cols[i % 2]:
                    if st.button(label, key=f"b{i}", use_container_width=True):
                        q["answered"] = True
                        if c['en'] == t['en']:
                            st.session_state.res = "⭕"
                            update_correct_count_in_gs(t['en'])
                        else:
                            st.session_state.res = "❌"
                            add_wrong_word_to_gs(t)
                        st.rerun()
            if st.button("わからない", use_container_width=True):
                q["answered"] = True
                st.session_state.res = "❓"
                add_wrong_word_to_gs(t)
                st.rerun()
        else:
            # 回答直後に「次へ」ボタンを配置（押しやすさ重視）
            st.write(f"### {st.session_state.res} {t['en']} = {t['ja']}")
            if st.button("次へ ➡️", use_container_width=True, type="primary"):
                del st.session_state.current_q
                st.rerun()
            
            # その下に他の回答（選択肢）を配置
            st.markdown("---")
            m_cols = st.columns(4)
            for i, c in enumerate(q["choices"]):
                with m_cols[i]:
                    mark = "✅" if c['en'] == t['en'] else ""
                    st.markdown(f'<div class="matome-text">{mark}<b>{c["en"]}</b><br>{c["ja"]}</div>', unsafe_allow_html=True)