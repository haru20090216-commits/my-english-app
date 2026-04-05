import streamlit as st
import random
import pandas as pd
import os

st.set_page_config(page_title="英単語クイズ", page_icon="⚡")
st.title("⚡ 瞬間採点！英単語アプリ")

# --- データの読み込み ---
@st.cache_data
def load_data():
    # パスを「現在の場所」に変更
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

def next_question():
    target = random.choice(st.session_state.word_list)
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

# --- クイズ画面 ---
q = st.session_state.current_question
st.subheader(f"問題: {q['target']['en']}")

selection = st.radio(
    "意味を選んでください:",
    [opt["ja"] for opt in q["choices"]],
    index=None,
    key="quiz_radio",
    disabled=(q["answered_choice"] is not None)
)

if selection and q["answered_choice"] is None:
    q["answered_choice"] = selection
    st.rerun()

# --- 結果と解説の表示 ---
if q["answered_choice"]:
    if q["answered_choice"] == q["target"]["ja"]:
        st.success(f"🎯 正解！ 「{q['target']['ja']}」")
    else:
        st.error(f"❌ 残念！ 正解は 「{q['target']['ja']}」 でした。")
    
    # 【ここを改造】正解・不正解に関わらず全ての選択肢の訳を出す
    st.write("---")
    st.info("📚 選択肢の単語リスト:")
    
    # 2列に分けて表示すると見やすくなります
    col1, col2 = st.columns(2)
    for i, opt in enumerate(q["choices"]):
        # 左右に振り分け
        target_col = col1 if i % 2 == 0 else col2
        # 正解の単語には目印をつける
        mark = "✅" if opt["ja"] == q["target"]["ja"] else "・"
        target_col.write(f"{mark} **{opt['en']}** : {opt['ja']}")

    if st.button("次の問題へ ➡️"):
        next_question()
        st.rerun()

with st.expander("現在の単語帳を確認"):
    st.table(st.session_state.word_list)