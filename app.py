import streamlit as st
import random
import pandas as pd
import os

st.set_page_config(page_title="最強英単語アプリ", page_icon="🔥", layout="wide") # wideモードで横幅を活用
st.title("🔥 特訓！英単語アプリ")

# --- データの読み込み ---
@st.cache_data
def load_data():
    path = "words.csv"
    if not os.path.exists(path):
        return None
    try:
        return pd.read_csv(path, encoding='utf-8-sig').to_dict('records')
    except:
        try:
            return pd.read_csv(path, encoding='shift_jis').to_dict('records')
        except:
            return None

# --- 初期化 ---
if 'word_list' not in st.session_state:
    data = load_data()
    if data:
        st.session_state.word_list = data
    else:
        st.error("⚠️ words.csv が見つかりません。")
        st.stop()

if 'wrong_words' not in st.session_state:
    st.session_state.wrong_words = []

# --- サイドバー設定 ---
st.sidebar.header("⚙️ 設定")
mode = st.sidebar.radio("出題モード:", ["全単語から出題", "間違えた問題のみ（復習）"])

if mode == "間違えた問題のみ（復習）":
    if not st.session_state.wrong_words:
        st.sidebar.warning("復習リストが空です")
        active_list = st.session_state.word_list
    else:
        active_list = st.session_state.wrong_words
else:
    active_list = st.session_state.word_list

def next_question():
    target = random.choice(active_list)
    others = [w for w in st.session_state.word_list if w != target]
    sample_size = min(len(others), 3)
    choices = random.sample(others, sample_size) + [target]
    random.shuffle(choices)
    st.session_state.current_question = {"target": target, "choices": choices, "answered_choice": None}

if 'current_question' not in st.session_state or st.session_state.get('last_mode') != mode:
    st.session_state.last_mode = mode
    next_question()

# --- クイズ画面レイアウト ---
q = st.session_state.current_question
st.subheader(f"【{mode}】 問題: {q['target']['en']}")

# 2つのカラムを作成 (左: 選択肢, 右: 解説)
col_left, col_right = st.columns([1, 1])

with col_left:
    selection = st.radio(
        "意味を選んでください:",
        [opt["ja"] for opt in q["choices"]],
        index=None,
        key=f"q_{q['target']['en']}",
        disabled=(q["answered_choice"] is not None)
    )

    if selection and q["answered_choice"] is None:
        q["answered_choice"] = selection
        if selection == q["target"]["ja"]:
            st.session_state.wrong_words = [w for w in st.session_state.wrong_words if w['en'] != q['target']['en']]
            st.success("🎯 正解！")
        else:
            if q["target"] not in st.session_state.wrong_words:
                st.session_state.wrong_words.append(q["target"])
            st.error("❌ 残念！")
        
        if st.button("次の問題へ ➡️"):
            next_question()
            st.rerun()

# 回答済みの場合のみ、右側に解説を表示
with col_right:
    if q["answered_choice"]:
        st.info("📚 選択肢の全訳:")
        for opt in q["choices"]:
            # 正解の単語を強調
            if opt["ja"] == q["target"]["ja"]:
                st.markdown(f"✅ **{opt['en']}** : {opt['ja']}")
            else:
                st.write(f"・ **{opt['en']}** : {opt['ja']}")

# --- 復習リスト表示 (折りたたみ) ---
st.write("---")
with st.expander(f"🚩 復習リスト ({len(st.session_state.wrong_words)}個)"):
    if st.session_state.wrong_words:
        st.table(st.session_state.wrong_words)
    else:
        st.write("苦手な単語はありません！")