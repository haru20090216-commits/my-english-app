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
        info = json.loads(st.secrets["json_key"].strip().lstrip('.'))
        if "private_key" in info:
            info["private_key"] = info["private_key"].replace("\\n", "\n")
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        client = gspread.authorize(creds)
        return client.open_by_key(st.secrets["spreadsheet_id"]).sheet1
    except Exception as e:
        return None

def load_wrong_words_from_gs():
    sheet = get_spreadsheet()
    if sheet:
        try:
            return sheet.get_all_records()
        except:
            return []
    return []

# --- データ読み込み（words.csv） ---
@st.cache_data
def load_base_data():
    path = "words.csv"
    if not os.path.exists(path):
        return []
    for enc in ['utf-8-sig', 'shift_jis', 'cp932']:
        try:
            df = pd.read_csv(path, encoding=enc)
            # 列名(en, ja)の空白を削除
            df.columns = df.columns.str.strip()
            return df.to_dict('records')
        except:
            continue
    return []

# --- 初期化 ---
if 'word_list' not in st.session_state:
    st.session_state.word_list = load_base_data()

if 'wrong_words' not in st.session_state:
    st.session_state.wrong_words = load_wrong_words_from_gs()

# もし単語リストが空なら警告を出して止める
if not st.session_state.word_list:
    st.error("⚠️ words.csv の読み込みに失敗しました。ファイル名や列名(en, ja)を確認してください。")
    st.stop()

# --- モード選択 ---
mode = st.sidebar.radio("モード:", ["全問", "復習"], horizontal=True)
if 'last_mode' not in st.session_state: st.session_state.last_mode = mode
if st.session_state.last_mode != mode:
    st.session_state.last_mode = mode
    if 'current_question' in st.session_state: del st.session_state.current_question

# 出題リストの決定
if mode == "復習" and st.session_state.wrong_words:
    active_list = st.session_state.wrong_words
else:
    active_list = st.session_state.word_list

# --- 問題作成 ---
def next_question():
    if not active_list:
        st.session_state.current_question = None
        return
    target = random.choice(active_list)
    # 選択肢作り
    others = [w for w in st.session_state.word_list if w['en'] != target['en']]
    sample_size = min(len(others), 3)
    choices = random.sample(others, sample_size) + [target]
    random.shuffle(choices)
    st.session_state.current_question = {"target": target, "choices": choices, "ans": None}

if 'current_question' not in st.session_state:
    next_question()

# --- クイズ表示 ---
if st.session_state.current_question is None:
    st.info("出題できる単語がありません。")
else:
    q = st.session_state.current_question
    # 【ここが重要】英語を大きく表示
    st.markdown(f"## **{q['target']['en']}**")
    
    selection = st.radio("意味は？", [opt["ja"] for opt in q["choices"]], index=None, key=f"q_{q['target']['en']}", disabled=(q["ans"] is not None))

    if selection and q["ans"] is None:
        q["ans"] = selection
        if selection == q["target"]["ja"]:
            st.success("正解！")
        else:
            st.error(f"不正解... 正解は: {q['target']['ja']}")
        
        if st.button("次へ"):
            del st.session_state.current_question
            st.rerun()