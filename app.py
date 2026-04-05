import streamlit as st
import random
import pandas as pd
import os

st.set_page_config(page_title="最強英単語アプリ", page_icon="🔥")
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

# --- サイドバーでモード切り替え ---
st.sidebar.header("⚙️ 設定")
mode = st.sidebar.radio("出題モードを選択:", ["全単語から出題", "間違えた問題のみ（復習）"])

# モードに応じたリストの作成
if mode == "間違えた問題のみ（復習）":
    if not st.session_state.wrong_words:
        st.warning("まだ間違えた問題がありません。「全単語モード」で解いてみましょう！")
        active_list = st.session_state.word_list
    else:
        active_list = st.session_state.wrong_words
else:
    active_list = st.session_state.word_list

def next_question():
    # 選択したモードのリストから出題
    target = random.choice(active_list)
    
    # 選択肢は常に「全単語」から作ると難易度が維持されて良いです
    others = [w for w in st.session_state.word_list if w != target]
    sample_size = min(len(others), 3)
    choices = random.sample(others, sample_size) + [target]
    random.shuffle(choices)
    
    st.session_state.current_question = {
        "target": target,
        "choices": choices,
        "answered_choice": None 
    }

# 最初に起動したとき、またはモードを切り替えたときに問題をリセット
if 'current_question' not in st.session_state or 'last_mode' not in st.session_state or st.session_state.last_mode != mode:
    st.session_state.last_mode = mode
    next_question()

# --- クイズ画面 ---
q = st.session_state.current_question
st.subheader(f"【{mode}】 問題: {q['target']['en']}")

selection = st.radio(
    "意味を選んでください:",
    [opt["ja"] for opt in q["choices"]],
    index=None,
    key=f"quiz_{mode}_{q['target']['en']}", # モードごとにキーを変えてエラー防止
    disabled=(q["answered_choice"] is not None)
)

if selection and q["answered_choice"] is None:
    q["answered_choice"] = selection
    
    # 正解・不正解の判定
    if selection == q["target"]["ja"]:
        # 正解したら「間違えたリスト」から削除する（克服した証！）
        st.session_state.wrong_words = [w for w in st.session_state.wrong_words if w['en'] != q['target']['en']]
    else:
        # 間違えたらリストに追加
        if q["target"] not in st.session_state.wrong_words:
            st.session_state.wrong_words.append(q["target"])
    st.rerun()

# --- 結果と解説 ---
if q["answered_choice"]:
    if q["answered_choice"] == q["target"]["ja"]:
        st.success(f"🎯 正解！ 「{q['target']['ja']}」")
    else:
        st.error(f"❌ 残念！ 正解は 「{q['target']['ja']}」 でした。")
    
    st.write("---")
    st.info("📚 解説:")
    col1, col2 = st.columns(2)
    for i, opt in enumerate(q["choices"]):
        target_col = col1 if i % 2 == 0 else col2
        mark = "✅" if opt["ja"] == q["target"]["ja"] else "・"
        target_col.write(f"{mark} **{opt['en']}** : {opt['ja']}")

    if st.button("次の問題へ ➡️"):
        next_question()
        st.rerun()

# --- 復習リストの表示 ---
st.write("---")
with st.expander(f"🚩 現在の復習リスト ({len(st.session_state.wrong_words)}個)"):
    if st.session_state.wrong_words:
        st.table(st.session_state.wrong_words)
        if st.button("リストをすべて消去"):
            st.session_state.wrong_words = []
            st.rerun()
    else:
        st.write("苦手な単語はありません！")