import streamlit as st
import random
import pandas as pd
import os

# ページ設定（コンパクトにするために余白を最小限に）
st.set_page_config(page_title="英単語", page_icon="🎓", layout="centered")

# CSSで上の余白を無理やり消す設定
st.markdown("""
    <style>
    .block-container { padding-top: 1rem; padding-bottom: 0rem; }
    div.stButton > button { width: 100%; margin-top: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- 1. データ読み込み ---
@st.cache_data
def load_data():
    path = "words.csv"
    if not os.path.exists(path): return None
    try: return pd.read_csv(path, encoding='utf-8-sig').to_dict('records')
    except:
        try: return pd.read_csv(path, encoding='shift_jis').to_dict('records')
        except: return None

# --- 2. 初期化 ---
if 'word_list' not in st.session_state:
    data = load_data()
    if data: st.session_state.word_list = data
    else: st.stop()

if 'wrong_words' not in st.session_state: st.session_state.wrong_words = []

# --- 3. 設定（サイドバーへ移動） ---
mode = st.sidebar.radio("モード:", ["全問", "復習"], horizontal=True)

if 'last_mode' not in st.session_state: st.session_state.last_mode = mode
if st.session_state.last_mode != mode:
    st.session_state.last_mode = mode
    if 'current_question' in st.session_state: del st.session_state.current_question

active_list = st.session_state.wrong_words if (mode == "復習" and st.session_state.wrong_words) else st.session_state.word_list

# --- 4. 問題作成 ---
def next_question():
    target = random.choice(active_list)
    others = [w for w in st.session_state.word_list if w != target]
    choices = random.sample(others, min(len(others), 3)) + [target]
    random.shuffle(choices)
    st.session_state.current_question = {"target": target, "choices": choices, "ans": None}

if 'current_question' not in st.session_state: next_question()

# --- 5. メイン画面 ---
q = st.session_state.current_question

# 問題を一行でコンパクトに
st.write(f"**Q: {q['target']['en']}** ({len(st.session_state.wrong_words)}語記録中)")

# 回答の選択
selection = st.radio(
    "選択:", [opt["ja"] for opt in q["choices"]], 
    index=None, key=f"q_{q['target']['en']}", 
    disabled=(q["ans"] is not None),
    label_visibility="collapsed" # ラベルを隠してさらにコンパクトに
)

if selection and q["ans"] is None:
    q["ans"] = selection
    if selection == q["target"]["ja"]:
        st.session_state.wrong_words = [w for w in st.session_state.wrong_words if w['en'] != q['target']['en']]
        st.toast("🎯 正解！") # 画面端に小さく通知
    else:
        if q["target"] not in st.session_state.wrong_words: st.session_state.wrong_words.append(q["target"])
        st.toast("❌ 不正解...")
    st.rerun()

# 回答後の表示
if q["ans"]:
    # 正誤を色付きテキストで
    if q["ans"] == q["target"]["ja"]:
        st.markdown(f"<span style='color:green'>● **正解**: {q['target']['ja']}</span>", unsafe_allow_html=True)
    else:
        st.markdown(f"<span style='color:red'>● **ミス**: 正解は {q['target']['ja']}</span>", unsafe_allow_html=True)
    
    # 選択肢の全訳を1行ずつコンパクトに表示
    with st.expander("詳細"):
        for opt in q["choices"]:
            mark = "✅" if opt["ja"] == q["target"]["ja"] else "・"
            st.write(f"{mark} {opt['en']}: {opt['ja']}")

    if st.button("次へ"):
        del st.session_state.current_question
        st.rerun()