import streamlit as st
import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import requests
from bs4 import BeautifulSoup
import re
import os

# ==========================================
# [설정] 페이지 제목과 아이콘 설정
# ==========================================
st.set_page_config(page_title="외교부 소식 요약 봇", page_icon="📢")

# ==========================================
# [1] 모델 로드 함수 (캐싱 사용)
# ==========================================
# 매번 모델을 새로 로딩하면 느리니까, 한 번만 로딩하고 기억해두는(@st.cache_resource) 기능입니다.
MODEL_DIR = "./final_model"

@st.cache_resource
def load_model():
    # 모델 폴더가 없으면 경고
    if not os.path.exists(MODEL_DIR):
        return None, None
    
    try:
        tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
        model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_DIR)
        return tokenizer, model
    except:
        return None, None

# 모델 불러오기
tokenizer, model = load_model()

# ==========================================
# [2] 기능 함수들 (크롤링 & 요약)
# ==========================================
# (Assignment 5에서 썼던 코드들을 함수로 정리한 것입니다)

def get_naver_blog_content(url):
    """네이버 블로그 URL에서 본문만 쏙 뽑아오는 함수"""
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        # 모바일 주소면 PC 주소로 변환
        if "m.blog.naver.com" in url:
            url = url.replace("m.blog.naver.com", "blog.naver.com")

        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')

        # 네이버 블로그의 진짜 본문(iframe) 주소 찾기
        iframe = soup.select_one('iframe#mainFrame')
        if iframe:
            real_url = "https://blog.naver.com" + iframe['src']
            response = requests.get(real_url, headers=headers)
            soup = BeautifulSoup(response.text, 'html.parser')

        # 제목 찾기
        title_elem = soup.select_one('.se-title-text') or soup.select_one('.htitle')
        title = title_elem.text.strip() if title_elem else "제목 없음"

        # 본문 찾기
        content_elem = soup.select_one('.se-main-container') or soup.select_one('#postViewArea')
        if content_elem:
            text = content_elem.text
            text = re.sub(r'\n+', ' ', text) # 줄바꿈 정리
            return title, text.strip()
        return None, None
    except:
        return None, None

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
            # '소식' 관련 글만 필터링
            if "소식" in cat or "보도" in cat or "대변인" in cat:
                results.append({"title": item.title.text, "link": item.link.text})
                if len(results) >= 3: break # 3개까지만
        
        # 없으면 최신글 3개
        if not results:
            results = [{"title": i.title.text, "link": i.link.text} for i in items[:3]]
        return results
    except:
        return []

def summarize(text):
    """모델에게 요약을 시키는 함수"""
    if tokenizer is None: return "모델 로드 실패! 폴더 위치를 확인하세요."
    
    # 입력 문장 정리
    inputs = tokenizer(text, return_tensors="pt", max_length=1024, truncation=True)
    
    # 요약 생성
    with torch.no_grad():
        summary_ids = model.generate(
            inputs["input_ids"],
            max_length=256,       # 넉넉하게
            min_length=30,
            length_penalty=1.2,
            num_beams=4,
            early_stopping=True,
            no_repeat_ngram_size=3
        )
    
    result = tokenizer.decode(summary_ids[0], skip_special_tokens=True)
    
    # 문장 끝맺음 보정 (마침표로 안 끝나면 자르기)
    if result and result[-1] not in ['.', '!', '?']:
        last_punctuation = max(result.rfind('.'), result.rfind('!'), result.rfind('?'))
        if last_punctuation != -1:
            result = result[:last_punctuation+1]
            
    return result

# ==========================================
# [3] 화면 꾸미기 (UI) - 여기서부터 웹사이트 화면입니다
# ==========================================

# 1. 제목 보여주기
st.title("🏛️ 외교부 소식 자동 요약 봇")
st.markdown("Assignment 5에서 학습시킨 **KoBART 모델**이 긴 글을 3줄로 요약해줍니다.")

# 모델 로드 상태 표시
if tokenizer is None:
    st.error("⚠️ `final_model` 폴더가 없습니다. 모델을 다운로드해서 넣어주세요.")
else:
    st.success("✅ AI 모델 준비 완료")

# 2. 탭 만들기 (기능 분리)
tab1, tab2 = st.tabs(["🔗 URL 직접 입력", "📡 외교부 최신 소식"])

# [Tab 1] URL 입력해서 요약하기
with tab1:
    st.header("뉴스/블로그 URL 요약")
    url_input = st.text_input("네이버 블로그 또는 뉴스 URL을 입력하세요:")
    
    # 버튼을 누르면 실행
    if st.button("요약 시작", key="btn1"):
        if url_input:
            with st.spinner("열심히 읽고 요약하는 중입니다..."):
                title, content = get_naver_blog_content(url_input)
                
                if content:
                    st.subheader(f"📄 {title}")
                    
                    # 요약 실행
                    summary_text = summarize(content)
                    
                    # 결과 보여주기
                    st.info(summary_text)
                    
                    # 원문 접었다 펴기
                    with st.expander("원문 보기"):
                        st.write(content)
                else:
                    st.error("본문을 가져올 수 없습니다. 링크를 확인해주세요.")
        else:
            st.warning("URL을 입력해주세요!")

# [Tab 2] 외교부 소식 자동 가져오기
with tab2:
    st.header("오늘의 외교부 브리핑")
    
    if st.button("최신 소식 가져오기", type="primary", key="btn2"):
        with st.spinner("외교부 블로그 스캔 중..."):
            news_items = get_latest_mofa_news()
            
            if news_items:
                for idx, item in enumerate(news_items):
                    st.markdown(f"### {idx+1}. [{item['title']}]({item['link']})")
                    
                    # 각 글 크롤링 및 요약
                    _, content = get_naver_blog_content(item['link'])
                    
                    if content:
                        summary_text = summarize(content)
                        st.success(f"💡 **AI 요약**: {summary_text}")
                    else:
                        st.error("본문 접근 불가")
                    
                    st.divider() # 구분선
            else:
                st.warning("새로운 소식을 찾을 수 없습니다.")
