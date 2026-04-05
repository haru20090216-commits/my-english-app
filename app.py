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
                sheet.append_row([word_dict['en'], word_dict['ja'], 0])
        except: pass

def update_correct_count_in_gs(en_word):
    sheet = get_spreadsheet()
    if not sheet: return False
    try:
        cell = sheet.find(en_word)
        if cell:
            val = sheet.cell(cell.row, 3).value
            current_count = int(val) if val and str(val).isdigit() else 0
            new_count = current_count + 1
            if new_count >= 5:
                sheet.delete_rows(cell.row)
                return True
            else:
                sheet.update_cell(cell.row, 3, new_count)
                return False
    except: pass
    return False

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

def load_wrong_words():
    sheet = get_spreadsheet()
    if sheet:
        try:
            return sheet.get_all_records()
        except: return []
    return []

# --- 初期化 ---
if 'all_words' not in st.session_state:
    st.session_state.all_words = load_base_data()
if 'wrong_words' not in st.session_state:
    st.session_state.wrong_words = load_wrong_words()

# --- サイドバー設定 ---
st.sidebar.title("🔍 メニュー")
mode = st.sidebar.radio("モード切替:", ["クイズ", "辞書"], horizontal=True)

if mode == "クイズ":
    st.sidebar.markdown("---")
    st.sidebar.title("🛠 出題設定")
    if st.session_state.all_words:
        nos = [int(w['no']) for w in st.session_state.all_words]
        start_no = st.sidebar.number_input("開始番号", min(nos), max(nos), min(nos))
        end_no = st.sidebar.number_input("終了番号", min(nos), max(nos), max(nos))
        filtered_words = [w for w in st.session_state.all_words if start_no <= int(w['no']) <= end_no]
        
        current_range = (start_no, end_no)
        if 'last_range' not in st.session_state or st.session_state.last_range != current_range:
            st.session_state.last_range = current_range
            if 'current_question' in st.session_state: del st.session_state.current_question
    else:
        filtered_words = []

    wrong_count = len(st.session_state.wrong_words)
    st.sidebar.metric("現在の復習単語数", f"{wrong_count} 語")
    quiz_mode = st.sidebar.radio("出題対象:", ["全問", "復習"], horizontal=True)
    
    if 'last_quiz_mode' not in st.session_state: st.session_state.last_quiz_mode = quiz_mode
    if st.session_state.last_quiz_mode != quiz_mode:
        st.session_state.last_quiz_mode = quiz_mode
        if 'current_question' in st.session_state: del st.session_state.current_question

# --- 各モードの表示 ---
if mode == "辞書":
    st.title("📖 単語検索辞書")
    search_q = st.text_input("検索 (英単語を入力)", "").strip().lower()
    if search_q:
        results = [w for w in st.session_state.all_words if w['en'].lower().startswith(search_q)]
        for res in results:
            with st.expander(f"📌 {res['en']}"):
                st.write(f"**意味:** {res['ja']} (No.{int(res['no'])})")
    else:
        st.write("