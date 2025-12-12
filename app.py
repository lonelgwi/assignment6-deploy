import streamlit as st
import torch
import requests
import re
from bs4 import BeautifulSoup
from transformers import PreTrainedTokenizerFast, BartForConditionalGeneration

# ==========================================
# [설정] 페이지 설정
# ==========================================
st.set_page_config(page_title="외교부 소식 요약 봇", page_icon="📢", layout="wide")

# ==========================================
# [1] 모델 로드 (모델 교체: ainize -> gogamza)
# ==========================================
@st.cache_resource
def load_model():
    # [중요 변경] 에러가 나는 'ainize' 모델을 버리고, 원조인 'gogamza' 모델로 교체합니다.
    # 이 모델은 최신 환경에서도 에러 없이 잘 돌아갑니다.
    model_name = "gogamza/kobart-summarization"
    
    try:
        tokenizer = PreTrainedTokenizerFast.from_pretrained(model_name)
        model = BartForConditionalGeneration.from_pretrained(model_name)
        return tokenizer, model, None
    except Exception as e:
        return None, None, str(e)

st.title("📢 외교부 소식 자동 요약 봇")
st.markdown("Assignment 6: KoBART 뉴스 요약 서비스")

# 로딩 표시
with st.spinner('정상적인 AI 모델(gogamza)을 다운로드 중입니다...'):
    tokenizer, model, error_msg = load_model()

if tokenizer is None:
    st.error("⚠️ 모델 로딩 실패")
    st.error(f"에러 내용: {error_msg}")
    st.stop()
else:
    st.success("✅ 모델 준비 완료!")

# ==========================================
# [2] 기능 함수들
# ==========================================

def summarize(text):
    """요약 실행 함수"""
    if len(text) < 10: return "내용이 너무 짧습니다."
    
    # 텍스트를 모델이 이해하는 숫자로 변환
    input_ids = tokenizer.encode(text, return_tensors="pt")
    
    # 너무 길면 자르기 (1024 토큰 제한)
    if input_ids.shape[1] > 1024:
        input_ids = input_ids[:, :1024]

    # 요약 생성
    summary_ids = model.generate(
        input_ids,
        num_beams=4,
        max_length=128,
        min_length=30,
        no_repeat_ngram_size=3,
        early_stopping=True,
        eos_token_id=375 # 문장 끝 알림
    )
    
    result = tokenizer.decode(summary_ids[0], skip_special_tokens=True)
    return result

def get_latest_mofa_news():
    """RSS 크롤링"""
    try:
        url = "https://rss.blog.naver.com/mofakr.xml"
        res = requests.get(url, timeout=5)
        soup = BeautifulSoup(res.content, "xml")
        items = soup.find_all("item")
        
        results = []
        for item in items:
            cat = item.category.text if item.category else ""
            if any(x in cat for x in ["소식", "보도", "대변인"]):
                results.append({"title": item.title.text, "link": item.link.text})
                if len(results) >= 3: break
        
        if not results: # 없으면 최신글 3개
            return [{"title": i.title.text, "link": i.link.text} for i in items[:3]]
            
        return results
    except:
        return []

def get_blog_content(url):
    """본문 크롤링"""
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
        
        if body:
            return body.text.strip().replace("\n", " ")
        return None
    except:
        return None

# ==========================================
# [3] UI 화면
# ==========================================
tab1, tab2 = st.tabs(["📝 직접 입력", "📡 자동 수집"])

# 탭 1: 직접 입력
with tab1:
    st.subheader("뉴스 기사 입력")
    txt = st.text_area("요약할 글을 붙여넣으세요", height=200)
    if st.button("요약하기", key="b1"):
        if txt:
            with st.spinner("요약 중..."):
                st.info(summarize(txt))
        else:
            st.warning("내용을 입력하세요.")

# 탭 2: 자동 수집
with tab2:
    st.subheader("외교부 소식 자동 수집")
    if st.button("최신 소식 가져오기", key="b2"):
        with st.spinner("불러오는 중..."):
            items = get_latest_mofa_news()
            if not items:
                st.error("뉴스를 찾을 수 없습니다.")
            else:
                for i in items:
                    st.markdown(f"**{i['title']}**")
                    st.caption(f"[원문 링크]({i['link']})")
                    
                    content = get_blog_content(i['link'])
                    if content:
                        result = summarize(content)
                        st.success(f"요약: {result}")
                        with st.expander("원문 보기"):
                            st.write(content)
                    else:
                        st.error("본문을 가져오지 못했습니다.")
                    st.divider()
