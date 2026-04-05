import streamlit as st
import random
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json

# --- ページ設定 ---
st.set_page_config(page_title="英単語マスター", page_icon="🎓", layout="centered")

# --- Googleスプレッドシート連携関数 ---
@st.cache_resource
def get_spreadsheet():
    # Secretsから鍵を読み込む
    info = json.loads(st.secrets["json_key"])
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    client = gspread.authorize(creds)
    # Secretsに保存したスプレッドシートIDを使用
    return client.open_by_key(st.secrets["spreadsheet_id"]).sheet1

def load_wrong_words_from_gs():
    sheet = get_spreadsheet()
    records = sheet.get_all_records()
    return records

def add_wrong_word_to_gs(word_dict):
    sheet = get_spreadsheet()
    # 重複チェック（すでにある場合は追加しない）
    existing = sheet.col_values(1) # A列(en)を取得
    if word_dict['en'] not in existing:
        sheet.append_row([word_dict['en'], word_dict['ja']])

def remove_wrong_word_from_gs(en_word):
    sheet = get_spreadsheet()
    cell = sheet.find(en_word)
    if cell:
        sheet.delete_rows(cell.row)

# --- データ読み込み（元のwords.csv） ---
@st.cache_data
def load_base_data():
    try:
        return pd.read_csv("words.csv", encoding='utf-8-sig').to_dict('records')
    except:
        return pd.read_csv("words.csv", encoding='shift_jis').to_dict('records')

# --- 初期化 ---
if 'word_list' not in st.session_state:
    st.session_state.word_list = load_base_data()

# 起動時にスプレッドシートから「間違えたリスト」を読み込む
if 'wrong_words' not in st.session_state:
    try:
        st.session_state.wrong_words = load_wrong_words_from_gs()
    except:
        st.session_state.wrong_words = []

# --- モード選択 ---
mode = st.sidebar.radio("モード:", ["全問", "復習"], horizontal=True)

if 'last_mode' not in st.session_state: st.session_state.last_mode = mode
if st.session_state.last_mode != mode:
    st.session_state.last_mode = mode
    if 'current_question' in st.session_state: del st.session_state.current_question

active_list = st.session_state.wrong_words if (mode == "復習" and st.session_state.wrong_words) else st.session_state.word_list

# --- 問題作成 ---
def next_question():
    target = random.choice(active_list)
    others = [w for w in st.session_state.word_list if w != target]
    choices = random.sample(others, min(len(others), 3)) + [target]
    random.shuffle(choices)
    st.session_state.current_question = {"target": target, "choices": choices, "ans": None}

if 'current_question' not in st.session_state: next_question()

# --- クイズ画面 ---
q = st.session_state.current_question
st.write(f"**Q: {q['target']['en']}** (苦手:{len(st.session_state.wrong_words)}語)")

selection = st.radio("選択:", [opt["ja"] for opt in q["choices"]], index=None, key=f"q_{q['target']['en']}", disabled=(q["ans"] is not None), label_visibility="collapsed")

if selection and q["ans"] is None:
    q["ans"] = selection
    if selection == q["target"]["ja"]:
        # 正解：スプレッドシートとセッション両方から消す
        st.session_state.wrong_words = [w for w in st.session_state.wrong_words if w['en'] != q['target']['en']]
        try: remove_wrong_word_from_gs(q['target']['en']) 
        except: pass
        st.toast("🎯 正解！(リストから削除)")
    else:
        # 不正解：スプレッドシートとセッション両方に追加
        if not any(w['en'] == q['target']['en'] for w in st.session_state.wrong_words):
            st.session_state.wrong_words.append(q['target'])
            try: add_wrong_word_to_gs(q['target'])
            except: pass
        st.toast("❌ 記録しました")
    st.rerun()

if q["ans"]:
    if q["ans"] == q["target"]["ja"]:
        st.markdown(f"<span style='color:green'>● **正解**: {q['target']['ja']}</span>", unsafe_allow_html=True)
    else:
        st.markdown(f"<span style='color:red'>● **ミス**: 正解は {q['target']['ja']}</span>", unsafe_allow_html=True)
    
    if st.button("次へ"):
        del st.session_state.current_question
        st.rerun()