import streamlit as st
import torch
import requests
import re
from bs4 import BeautifulSoup
from transformers import BartForConditionalGeneration, PreTrainedTokenizerFast

# ==========================================
# 페이지 설정
# ==========================================
st.set_page_config(page_title="외교부 소식 요약 봇", page_icon="📢", layout="wide")

# ==========================================
# [1] 모델 로드 (에러 원천 봉쇄 버전)
# ==========================================
@st.cache_resource
def load_model():
    model_name = "ainize/kobart-news"
    try:
        # [수정] 토크나이저 로딩 방식 변경
        tokenizer = PreTrainedTokenizerFast.from_pretrained(model_name)
        model = BartForConditionalGeneration.from_pretrained(model_name)
        return tokenizer, model, None
    except Exception as e:
        return None, None, str(e)

# 화면 표시
st.title("📢 외교부 소식 자동 요약 봇")
st.markdown("Assignment 6: KoBART 뉴스 요약")

with st.spinner('모델 로딩 중... (protobuf 버전 확인 필요)'):
    tokenizer, model, error_msg = load_model()

if tokenizer is None:
    st.error("⚠️ 모델 로딩 실패")
    st.error(f"에러 메시지: {error_msg}")
    st.warning("👉 터미널에 'pip install protobuf==3.20.3' 을 입력하고 다시 실행해보세요!")
    st.stop()
else:
    st.success("✅ 모델 준비 완료")

# ==========================================
# [2] 기능 함수들
# ==========================================
def summarize(text):
    if len(text) < 10: return "내용이 너무 짧습니다."
    
    input_ids = tokenizer.encode(text, return_tensors="pt")
    # 길이 제한 안전장치
    if input_ids.shape[1] > 1024: input_ids = input_ids[:, :1024]

    summary_ids = model.generate(
        input_ids,
        max_length=128,
        min_length=30,
        length_penalty=1.0,
        num_beams=4,
        early_stopping=True
    )
    return tokenizer.decode(summary_ids[0], skip_special_tokens=True)

def get_latest_mofa_news():
    # RSS 크롤링
    try:
        url = "https://rss.blog.naver.com/mofakr.xml"
        res = requests.get(url)
        soup = BeautifulSoup(res.content, "xml")
        items = soup.find_all("item")
        results = []
        for item in items:
            if any(x in (item.category.text if item.category else "") for x in ["소식", "보도", "대변인"]):
                results.append({"title": item.title.text, "link": item.link.text})
                if len(results) >= 3: break
        return results if results else [{"title": i.title.text, "link": i.link.text} for i in items[:3]]
    except:
        return []

def get_blog_content(url):
    # 본문 크롤링
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        if "m.blog" in url: url = url.replace("m.blog", "blog")
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, "html.parser")
        iframe = soup.select_one("iframe#mainFrame")
        if iframe:
            res = requests.get("https://blog.naver.com" + iframe["src"], headers=headers)
            soup = BeautifulSoup(res.text, "html.parser")
        
        body = soup.select_one(".se-main-container") or soup.select_one("#postViewArea")
        return body.text.strip().replace("\n", " ") if body else None
    except:
        return None

# ==========================================
# [3] UI 탭
# ==========================================
tab1, tab2 = st.tabs(["📝 직접 입력", "📡 자동 수집"])

with tab1:
    txt = st.text_area("텍스트 입력", height=200)
    if st.button("요약", key="b1") and txt:
        st.info(summarize(txt))

with tab2:
    if st.button("최신 소식 가져오기", key="b2"):
        items = get_latest_mofa_news()
        for i in items:
            st.markdown(f"**{i['title']}** [링크]({i['link']})")
            content = get_blog_content(i['link'])
            if content:
                st.success(f"요약: {summarize(content)}")
            st.divider()
