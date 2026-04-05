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

# --- サイドバー：数値入力による範囲設定 ---
st.sidebar.title("🛠 出題設定")

if st.session_state.all_words:
    nos = [int(w['no']) for w in st.session_state.all_words]
    min_val, max_val = min(nos), max(nos)
    
    st.sidebar.write(f"データ範囲: No.{min_val} 〜 {max_val}")
    
    # 数値入力ボックス (number_input)
    start_no = st.sidebar.number_input("開始番号", min_value=min_val, max_value=max_val, value=min_val)
    end_no = st.sidebar.number_input("終了番号", min_value=min_val, max_value=max_val, value=max_val)
    
    # 範囲が逆転しないようにガード
    if start_no > end_no:
        st.sidebar.warning("開始番号が終了番号より大きくなっています")
        filtered_words = []
    else:
        filtered_words = [w for w in st.session_state.all_words if start_no <= int(w['no']) <= end_no]
    
    # 範囲の変更を検知して問題をリセット
    current_range = (start_no, end_no)
    if 'last_range' not in st.session_state or st.session_state.last_range != current_range:
        st.session_state.last_range = current_range
        if 'current_question' in st.session_state:
            del st.session_state.current_question
else:
    filtered_words = []

# モード選択
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
        st.session_state.current_question = {"target": target, "