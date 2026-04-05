import streamlit as st
import random
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import os

# --- ページ設定 ---
st.set_page_config(page_title="英単語マスター", page_icon="🎓", layout="centered")

# --- Googleスプレッドシート連携 ---
@st.cache_resource
def get_spreadsheet():
    try:
        raw_key = st.secrets["json_key"].strip().lstrip('.')
        info = json.loads(raw_key)
        if "private_key" in info:
            info["private_key"] = info["private_key"].replace("\\n", "\n")
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        client = gspread.authorize(creds)
        return client.open_by_key(st.secrets["spreadsheet_id"]).sheet1
    except:
        return None

def add_wrong_word_to_gs(word_dict):
    sheet = get_spreadsheet()
    if sheet:
        try:
            existing = sheet.col_values(1)
            if word_dict['en'] not in existing:
                sheet.append_row([word_dict['en'], word_dict['ja']])
        except: pass

def remove_wrong_word_from_gs(en_word):
    sheet = get_spreadsheet()
    if sheet:
        try:
            cell = sheet.find(en_word)
            if cell: sheet.delete_rows(cell.row)
        except: pass

# --- データ読み込み ---
@st.cache_data
def load_base_data():
    path = "words.csv"
    if not os.path.exists(path): return []
    for enc in ['utf-8-sig', 'shift_jis', 'cp932']:
        try:
            df = pd.read_csv(path, encoding=enc)
            df.columns = df.columns.str.strip()
            if 'no' in df.columns:
                df['no'] = pd.to_numeric(df['no'], errors='coerce')
            return df.dropna(subset=['en', 'ja', 'no']).to_dict('records')
        except: continue
    return []

# --- 初期化 ---
if 'all_words' not in st.session_state:
    st.session_state.all_words = load_base_data()

if 'wrong_words' not in st.session_state:
    from_gs = []
    try:
        sheet = get_spreadsheet()
        if sheet: from_gs = sheet.get_all_records()
    except: pass
    st.session_state.wrong_words = from_gs

# --- サイドバー：設定 ---
st.sidebar.title("🛠 出題設定")

if st.session_state.all_words:
    nos = [int(w['no']) for w in st.session_state.all_words]
    min_val, max_val = min(nos), max(nos)
    
    start_no = st.sidebar.number_input("開始番号", min_value=min_val, max_value=max_val, value=min_val)
    end_no = st.sidebar.number_input("終了番号", min_value=min_val, max_value=max_val, value=max_val)
    
    if start_no > end_no:
        st.sidebar.warning("開始番号を確認してください")
        filtered_words = []
    else:
        filtered_words = [w for w in st.session_state.all_words if start_no <= int(w['no']) <= end_no]
    
    # 範囲変更を検知
    current_range = (start_no, end_no)
    if 'last_range' not in st.session_state or st.session_state.last_range != current_range:
        st.session_state.last_range = current_range
        if 'current_question' in st.session_state:
            del st.session_state.current_question
else:
    filtered_words = []

wrong_count = len(st.session_state.wrong_words)
st.sidebar.metric("現在の復習単語数", f"{wrong_count} 語")
mode = st.sidebar.radio("モード:", ["全問", "復習"], horizontal=True)

if 'last_mode' not in st.session_state: st.session_state.last_mode = mode
if st.session_state.last_mode != mode:
    st.session_state.last_mode = mode
    if 'current_question' in st.session_state: del st.session_state.current_question

# --- 出題リスト決定 ---
active_list = st.session_state.wrong_words if (mode == "復習" and st.session_state.wrong_words) else filtered_words

def next_question():
    if not active_list:
        st.session_state.current_question = None
    else:
        target = random.choice(active_list)
        others = [w for w in st.session_state.all_words if w['en'] != target['en']]
        choices = random.sample(others, min(len(others), 3)) + [target]
        random.shuffle(choices)
        st.session_state.current_question = {"target": target, "choices": choices, "answered": False}

if 'current_question' not in st.session_state:
    next_question()

# --- メイン画面 ---
if not st.session_state.all_words:
    st.error("words.csvが正しく読み込めていません。")
elif st.session_state.current_question is None:
    st.warning("選択された範囲に単語がありません。")
else:
    q = st.session_state.current_question
    st.markdown(f"### No.{int(q['target']['no'])}")
    st.markdown(f"# **{q['target']['en']}**")

    if not q["answered"]:
        cols = st.columns(2)
        for i, choice in enumerate(q["choices"]):
            with cols[i % 2]:
                if st.button(choice["ja"], key=f"btn_{i}", use_container_width=True):
                    q["answered"] = True
                    if choice["ja"] == q["target"]["ja"]:
                        st.session_state.result_type = "correct"
                        st.session_state.wrong_words = [w for w in st.session_state.wrong_words if w['en'] != q['target']['en']]
                        remove_wrong_word_from_gs(q['target']['en'])
                    else:
                        st.session_state.result_type = "wrong"
                        if not any(w['en'] == q['target']['en'] for w in st.session_state.wrong_words):
                            st.session_state.wrong_words.append(q['target'])
                            add_wrong_word_to_gs(q['target'])
                    st.rerun()
        
        st.write("")
        if st.button("❓ わからない", key="dont_know", use_container_width=True):
            q["answered"] = True
            st.session_state.result_type = "unknown"
            if not any(w['en'] == q['target']['en'] for w in st.session_state.wrong_words):
                st.session_state.wrong_words.append(q['target'])
                add_wrong_word_to_gs(q['target'])
            st.rerun()
    else:
        if st.session_state.result_type == "correct":
            st.success(f"🎯 正解！: {q['target']['ja']}")
        elif st.session_state.result_type == "unknown":
            st.warning(f"💡 覚えておきましょう: {q['target']['ja']}")
        else:
            st.error(f"❌ 不正解... 正解は: {q['target']['ja']}")
        
        st.write("---")
        st.write("💡 **今回の復習:**")
        for c in q["choices"]:
            mark = "✅" if c['en'] == q['target']['en'] else "・"
            st.write(f"{mark} **{c['en']}** : {c['ja']}")
        
        if st.button("次の問題へ ➡️", use_container_width=True):
            del st.session_state.current_question
            st.rerun()