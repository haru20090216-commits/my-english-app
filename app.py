import streamlit as st
import random
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import os

st.set_page_config(page_title="英単語マスター", page_icon="🎓", layout="centered")

# --- Googleスプレッドシート連携 (キャッシュを1分間保持) ---
@st.cache_resource
def get_client():
    raw_key = st.secrets["json_key"].strip().lstrip('.')
    info = json.loads(raw_key)
    if "private_key" in info:
        info["private_key"] = info["private_key"].replace("\\n", "\n")
    creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return gspread.authorize(creds)

@st.cache_data(ttl=60) # 60秒間はスプレッドシートを再読み込みしない
def load_wrong_words_cached():
    try:
        client = get_client()
        sheet = client.open_by_key(st.secrets["spreadsheet_id"]).sheet1
        data = sheet.get_all_records()
        return [d for d in data if d.get('en')]
    except:
        return []

def add_wrong_word_to_gs(word_dict):
    try:
        client = get_client()
        sheet = client.open_by_key(st.secrets["spreadsheet_id"]).sheet1
        existing = sheet.col_values(1)
        if word_dict['en'] not in existing:
            sheet.append_row([word_dict['en'], word_dict['ja'], 0, int(float(word_dict.get('no', 0)))])
        st.cache_data.clear() # データが変わったのでキャッシュを消す
    except: pass

def update_correct_count_in_gs(en_word):
    try:
        client = get_client()
        sheet = client.open_by_key(st.secrets["spreadsheet_id"]).sheet1
        cell = sheet.find(en_word)
        if cell:
            val = sheet.cell(cell.row, 3).value
            count = int(val) if val and str(val).isdigit() else 0
            if count + 1 >= 5:
                sheet.delete_rows(cell.row)
            else:
                sheet.update_cell(cell.row, 3, count + 1)
        st.cache_data.clear() # キャッシュをクリア
    except: pass

@st.cache_data
def load_base_data():
    path = "words.csv"
    if not os.path.exists(path): return []
    for enc in ['utf-8-sig', 'shift_jis', 'cp932']:
        try:
            df = pd.read_csv(path, encoding=enc)
            df.columns = df.columns.str.strip()
            df['no'] = pd.to_numeric(df.get('no', range(1, len(df)+1)), errors='coerce').fillna(0)
            return df.dropna(subset=['en', 'ja']).to_dict('records')
        except: continue
    return []

# --- データの初期化 ---
if 'all_words' not in st.session_state:
    st.session_state.all_words = load_base_data()

# キャッシュを利用して取得
st.session_state.wrong_words = load_wrong_words_cached()

# --- サイドバー・メイン処理 ---
# (以前のコードと同様のため中略。クイズのロジック部分はそのまま維持されます)