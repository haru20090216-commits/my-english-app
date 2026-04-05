import streamlit as st
import random
import pandas as pd
import os

# --- ページ設定 ---
st.set_page_config(page_title="最強英単語アプリ", page_icon="🔥", layout="wide")
st.title("🔥 特訓！英単語アプリ")

# --- 1. データの読み込み ---
@st.cache_data
def load_data():
    path = "words.csv"
    if not os.path.exists(path):
        return None
    try:
        # GitHub/Streamlit Cloud環境では utf-8-sig が標準的です
        return pd.read_csv(path, encoding='utf-8-sig').to_dict('records')
    except:
        try:
            return pd.read_csv(path, encoding='shift_jis').to_dict('records')
        except:
            return None

# --- 2. 初期化 ---
if 'word_list' not in st.session_state:
    data = load_data()
    if data:
        st.session_state.word_list = data
    else:
        st.error("⚠️ words.csv が見つかりません。GitHubにアップロードされているか確認してください。")
        st.stop()

if 'wrong_words' not in st.session_state:
    st.session_state.wrong_words = []

# --- 3. サイドバー設定 ---
st.sidebar.header("⚙️ 設定")
mode = st.sidebar.radio("出題モード:", ["全単語から出題", "間違えた問題のみ（復習）"])

# モード切替時のリセット処理
if 'last_mode' not in st.session_state:
    st.session_state.last_mode = mode

if st.session_state.last_mode != mode:
    st.session_state.last_mode = mode
    if 'current_question' in st.session_state:
        del st.session_state.current_question

# 出題リストの決定
if mode == "間違えた問題のみ（復習）" and st.session_state.wrong_words:
    active_list = st.session_state.wrong_words
else:
    active_list = st.session_state.word_list

# --- 4. 問題作成関数 ---
def next_question():
    target = random.choice(active_list)
    others = [w for w in st.session_state.word_list if w != target]
    sample_size = min(len(others), 3)
    choices = random.sample(others, sample_size) + [target]
    random.shuffle(choices)
    st.session_state.current_question = {
        "target": target, 
        "choices": choices, 
        "answered_choice": None
    }

if 'current_question' not in st.session_state:
    next_question()

# --- 5. クイズ画面レイアウト ---
q = st.session_state.current_question
st.subheader(f"【{mode}】 問題: {q['target']['en']}")

col_left, col_right = st.columns([1, 1])

with col_left:
    selection = st.radio(
        "意味を選んでください:",
        [opt["ja"] for opt in q["choices"]],
        index=None,
        key=f"q_{q['target']['en']}",
        disabled=(q["answered_choice"] is not None)
    )

    # 回答した瞬間の判定
    if selection and q["answered_choice"] is None:
        q["answered_choice"] = selection
        if selection == q["target"]["ja"]:
            # 正解なら復習リストから削除
            st.session_state.wrong_words = [w for w in st.session_state.wrong_words if w['en'] != q['target']['en']]
            st.success("🎯 正解！")
        else:
            # 不正解なら復習リストに追加
            if q["target"] not in st.session_state.wrong_words:
                st.session_state.wrong_words.append(q["target"])
            st.error("❌ 残念！")
        st.rerun()

    # 「次の問題へ」ボタン
    if q["answered_choice"] is not None:
        if st.button("次の問題へ ➡️", use_container_width=True):
            if 'current_question' in st.session_state:
                del st.session_state.current_question
            st.rerun()

with col_right:
    if q["answered_choice"]:
        st.info("📚 選択肢の全訳:")
        for opt in q["choices"]:
            if opt["ja"] == q["target"]["ja"]:
                st.markdown(f"✅ **{opt['en']}** : {opt['ja']}")
            else:
                st.write(f"・ **{opt['en']}** : {opt['ja']}")

# --- 6. 復習リスト表示 ---
st.write("---")
with st.expander(f"🚩 復習リスト ({len(st.session_state.wrong_words)}個)"):
    if st.session_state.wrong_words:
        st.table(st.session_state.wrong_words)
    else:
        st.write("苦手な単語はありません！")