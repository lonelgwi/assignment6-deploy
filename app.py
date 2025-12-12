import streamlit as st
import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import requests
from bs4 import BeautifulSoup
import re

# --- 1. 페이지 기본 설정 ---
st.set_page_config(page_title="외교부 소식 요약 서비스", page_icon="🤖")

st.title("🤖 인공지능 뉴스 요약 봇")
st.write("Assignment 6: ML 모델 서비스화 프로젝트")
st.markdown("---")

# --- 2. 모델 불러오기 (캐싱 기능으로 속도 향상) ---
@st.cache_resource
def load_model():
    # 로컬 폴더 경로 (폴더 이름이 정확해야 합니다)
    model_path = "./final_model" 
    
    try:
        # 모델과 토크나이저 로드
        tokenizer = AutoTokenizer.from_pretrained(model_path)
        model = AutoModelForSeq2SeqLM.from_pretrained(model_path)
        return tokenizer, model
    except Exception as e:
        return None, None

# 모델 로딩 상태 표시
with st.spinner('AI 모델을 깨우는 중입니다... (잠시만 기다려주세요)'):
    tokenizer, model = load_model()

if model is None:
    st.error("⚠️ 'final_model' 폴더를 찾을 수 없습니다! 폴더 위치를 확인해주세요.")
    st.stop()
else:
    st.success("✅ AI 모델 준비 완료!")

# --- 3. 요약 함수 정의 ---
def summarize_text(text):
    inputs = tokenizer(
        text, 
        return_tensors="pt", 
        max_length=1024, 
        truncation=True, 
        padding="max_length"
    )
    
    summary_ids = model.generate(
        inputs["input_ids"], 
        max_length=150, 
        min_length=30, 
        length_penalty=2.0, 
        num_beams=4, 
        early_stopping=True
    )
    
    summary = tokenizer.decode(summary_ids[0], skip_special_tokens=True)
    return summary

# --- 4. 스크레이핑 함수 (차단 방지 적용) ---
def scrape_website(url):
    try:
        # 로봇이 아닌 척 브라우저 정보(User-Agent) 보내기
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers)
        response.raise_for_status() # 404 등 에러 체크
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 본문 추출 시도 (p 태그 위주)
        paragraphs = soup.find_all('p')
        content = " ".join([p.get_text() for p in paragraphs])
        
        if len(content) < 50: # 내용이 너무 짧으면 실패로 간주
            return "내용을 찾을 수 없습니다. (보안이 강한 사이트일 수 있습니다)"
            
        return content
    except Exception as e:
        return f"에러 발생: {e}"

# --- 5. 화면 구성 (탭 기능) ---
tab1, tab2 = st.tabs(["🌐 URL로 요약하기", "📝 직접 입력해서 요약하기"])

# [Tab 1] URL 스크레이핑 방식
with tab1:
    st.subheader("뉴스 기사 주소를 입력하세요")
    url_input = st.text_input("URL 입력", placeholder="https://www.mofa.go.kr/...")
    
    if st.button("URL 요약 시작", key='btn_url'):
        if url_input:
            with st.spinner('사이트에 접속해서 글을 읽는 중...'):
                scraped_text = scrape_website(url_input)
                
            if "에러 발생" in scraped_text or len(scraped_text) < 50:
                st.warning("⚠️ 이 사이트는 보안 때문에 봇 접근을 막고 있습니다. 옆의 '직접 입력' 탭을 이용해주세요!")
                st.write(f"상세 메시지: {scraped_text}")
            else:
                st.info(f"수집된 글자 수: {len(scraped_text)}자")
                with st.expander("원문 보기 (접기/펼치기)"):
                    st.write(scraped_text[:1000] + "...") # 너무 기니까 앞부분만
                
                # 요약 수행
                with st.spinner('AI가 요약 중입니다...'):
                    result = summarize_text(scraped_text)
                    st.markdown("### 📄 요약 결과")
                    st.success(result)
        else:
            st.warning("주소를 입력해주세요.")

# [Tab 2] 텍스트 직접 입력 방식 (플랜 B)
with tab2:
    st.subheader("본문 내용을 직접 붙여넣으세요")
    st.caption("※ 스크레이핑이 안 되는 사이트는 여기서 해결하세요!")
    text_input = st.text_area("기사 본문 붙여넣기", height=300)
    
    if st.button("텍스트 요약 시작", key='btn_text'):
        if len(text_input) > 50:
            with st.spinner('AI가 열심히 요약 중...'):
                result = summarize_text(text_input)
                st.markdown("### 📄 요약 결과")
                st.success(result)
        else:
            st.warning("내용이 너무 짧습니다. 50자 이상 입력해주세요.")

# --- 6. 사이드바 (정보 표시) ---
with st.sidebar:
    st.header("프로젝트 정보")
    st.write("**작성자:** 홍길동 (본인이름)")
    st.write("**사용 모델:** T5 / Bart (학습시킨 모델명)")
    st.write("**버전:** 1.0.0")
    st.info("이 서비스는 Assignment 6 과제 제출용입니다.")
