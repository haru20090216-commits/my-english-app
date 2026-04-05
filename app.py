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
    except Exception as e:
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
            return df.to_dict('records')
        except: continue
    return []

# --- 初期化 ---
if 'word_list' not in st.session_state:
    st.session_state.word_list = load_base_data()
if 'wrong_words' not in st.session_state:
    st.session_state.wrong_words = [] # 最初は空。必要ならここでスプレッドシートから読み込む

# --- モード選択 ---
mode = st.sidebar.radio("モード:", ["全問", "復習"], horizontal=True)
if 'last_mode' not in st.session_state: st.session_state.last_mode = mode
if st.session_state.last_mode != mode:
    st.session_state.last_mode = mode
    if 'current_question' in st.session_state: del st.session_state.current_question

# 出題リスト
active_list = st.session_state.wrong_words if (mode == "復習" and st.session_state.wrong_words) else st.session_state.word_list

# --- 問題作成関数 ---
def next_question():
    if not active_list:
        st.session_state.current_question = None
    else:
        target = random.choice(active_list)
        others = [w for w in st.session_state.word_list if w['en'] != target['en']]
        sample_size = min(len(others), 3)
        choices = random.sample(others, sample_size) + [target]
        random.shuffle(choices)
        st.session_state.current_question = {"target": target, "choices": choices, "answered": False, "selected": None}

# 初回問題作成
if 'current_question' not in st.session_state:
    next_question()

# --- クイズ画面表示 ---
if not st.session_state.word_list:
    st.error("words.csvが読み込めません。")
elif st.session_state.current_question is None:
    st.info("出題できる単語がありません。")
else:
    q = st.session_state.current_question
    st.markdown(f"## **{q['target']['en']}**")
    
    # 選択肢ボタン
    for choice in q["choices"]:
        btn_label = choice["ja"]
        if st.button(btn_label, key=f"btn_{choice['en']}_{q['target']['en']}", disabled=q["answered"]):
            q["answered"] = True
            q["selected"] = choice["ja"]
            
            if choice["ja"] == q["target"]["ja"]:
                st.session_state.last_result = "🎯 正解！"
                # 正解なら復習リストから削除
                st.session_state.wrong_words = [w for w in st.session_state.wrong_words if w['en'] != q['target']['en']]
                remove_wrong_word_from_gs(q['target']['en'])
            else:
                st.session_state.last_result = f"❌ 不正解（正解は: {q['target']['ja']}）"
                # 不正解なら復習リストに追加
                if not any(w['en'] == q['target']['en'] for w in st.session_state.wrong_words):
                    st.session_state.wrong_words.append(q['target'])
                    add_wrong_word_to_gs(q['target'])
            st.rerun()

    # 回答後の表示
    if q["answered"]:
        st.markdown(f"### {st.session_state.last_result}")
        if st.button("次の問題へ ➡️"):
            next_question()
            st.rerun()