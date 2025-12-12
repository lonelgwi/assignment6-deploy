import streamlit as st
import torch
import requests
import re
from bs4 import BeautifulSoup
# 호환성을 위해 AutoTokenizer 사용
from transformers import AutoTokenizer, BartForConditionalGeneration

# ==========================================
# [설정] 페이지 제목과 아이콘 설정
# ==========================================
st.set_page_config(page_title="외교부 소식 요약 봇", page_icon="📢", layout="wide")

# ==========================================
# [1] 모델 로드 함수 (인터넷에서 다운로드)
# ==========================================
@st.cache_resource
def load_model():
    # 한국어 뉴스 요약에 특화된 공개 모델 사용
    model_name = "ainize/kobart-news"
    
    try:
        # use_fast=False 옵션으로 호환성 에러 방지
        tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=False)
        model = BartForConditionalGeneration.from_pretrained(model_name)
        return tokenizer, model
    except Exception as e:
        st.error(f"모델 로드 중 에러 발생: {e}")
        return None, None

# 모델 불러오기 (로딩 중 표시)
with st.spinner('인터넷에서 AI 모델(KoBART)을 불러오는 중입니다...'):
    tokenizer, model = load_model()

# ==========================================
# [2] 기능 함수들 (크롤링 & 요약)
# ==========================================

def get_naver_blog_content(url):
    """네이버 블로그 URL에서 본문만 쏙 뽑아오는 함수 (Tab 2용)"""
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        if "m.blog.naver.com" in url:
            url = url.replace("m.blog.naver.com", "blog.naver.com")

        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')

        iframe = soup.select_one('iframe#mainFrame')
        if iframe:
            real_url = "https://blog.naver.com" + iframe['src']
            response = requests.get(real_url, headers=headers)
            soup = BeautifulSoup(response.text, 'html.parser')

        title_elem = soup.select_one('.se-title-text') or soup.select_one('.htitle')
        title = title_elem.text.strip() if title_elem else "제목 없음"

        content_elem = soup.select_one('.se-main-container') or soup.select_one('#postViewArea')
        if content_elem:
            text = content_elem.text
            text = re.sub(r'\n+', ' ', text)
            text = re.sub(r'\s+', ' ', text)
            return title, text.strip()
        return title, None
    except:
        return "에러", None

def get_latest_mofa_news():
    """외교부 블로그 RSS에서 최신글 가져오는 함수"""
    rss_url = "https://rss.blog.naver.com/mofakr.xml"
    try:
        response = requests.get(rss_url)
        soup = BeautifulSoup(response.content, 'xml')
        items = soup.find_all('item')
        
        results = []
        for item in items:
            cat = item.category.text if item.category else ""
            # '소식', '보도', '대변인' 관련 글만 필터링
            if "소식" in cat or "보도" in cat or "대변인" in cat:
                results.append({"title": item.title.text, "link": item.link.text})
                if len(results) >= 3: break 
        
        if not results:
            results = [{"title": i.title.text, "link": i.link.text} for i in items[:3]]
        return results
    except:
        return []

def summarize(text):
    """모델에게 요약을 시키는 함수"""
    if tokenizer is None: return "모델이 준비되지 않았습니다."
    
    # 입력 문장 토큰화 (길면 자르기)
    inputs = tokenizer(text, return_tensors="pt", max_length=1024, truncation=True)
    
    # 요약 생성
    with torch.no_grad():
        summary_ids = model.generate(
            inputs["input_ids"],
            max_length=128,      
            min_length=30,
            length_penalty=1.0, # 패널티 조정
            num_beams=4,
            early_stopping=True
        )
    
    result = tokenizer.decode(summary_ids[0], skip_special_tokens=True)
    return result

# ==========================================
# [3] 화면 꾸미기 (UI)
# ==========================================

st.title("🏛️ 외교부 소식 자동 요약 봇")
st.markdown("Assignment 6: **KoBART 모델**을 활용한 뉴스 요약 서비스")

if tokenizer is None:
    st.error("⚠️ 모델을 불러오지 못했습니다. `pip install protobuf sentencepiece`를 확인하세요.")
    st.stop()
else:
    st.success("✅ AI 모델 준비 완료 (ainize/kobart-news)")

# 탭 만들기
tab1, tab2 = st.tabs(["📝 텍스트 직접 입력", "📡 외교부 소식 자동 수집"])

# [Tab 1] 직접 입력해서 요약하기 (URL 입력 X -> 텍스트 입력 O)
with tab1:
    st.header("기사 본문 요약")
    st.caption("요약하고 싶은 긴 글을 아래에 복사해서 붙여넣으세요.")
    
    input_text = st.text_area("여기에 내용을 입력하세요", height=300)
    
    if st.button("요약하기", key="btn_manual"):
        if len(input_text) > 50:
            with st.spinner("AI가 내용을 읽고 요약 중입니다..."):
                summary_text = summarize(input_text)
                st.subheader("📄 요약 결과")
                st.info(summary_text)
        else:
            st.warning("내용이 너무 짧습니다. 50자 이상 입력해주세요.")

# [Tab 2] 외교부 소식 자동 가져오기 (기존 기능 유지)
with tab2:
    st.header("오늘의 외교부 브리핑")
    st.caption("버튼을 누르면 외교부 공식 블로그에서 최신 글을 가져와 요약합니다.")
    
    if st.button("최신 소식 가져오기", type="primary", key="btn_auto"):
        with st.spinner("외교부 블로그 스캔 중..."):
            news_items = get_latest_mofa_news()
            
            if news_items:
                st.success(f"총 {len(news_items)}개의 최신 소식을 찾았습니다.")
                for idx, item in enumerate(news_items):
                    st.markdown(f"### {idx+1}. [{item['title']}]({item['link']})")
                    
                    # 각 글 내용 가져오기 & 요약
                    title, content = get_naver_blog_content(item['link'])
                    
                    if content:
                        summary_text = summarize(content)
                        st.info(f"**AI 요약**: {summary_text}")
                        with st.expander("원문 보기"):
                            st.write(content)
                    else:
                        st.error("본문 접근 불가 (보안 설정 등)")
                    
                    st.divider()
            else:
                st.warning("새로운 소식을 찾을 수 없습니다.")
