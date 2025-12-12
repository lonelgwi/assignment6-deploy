import streamlit as st
import torch
from transformers import PreTrainedTokenizerFast, BartForConditionalGeneration
import requests
from bs4 import BeautifulSoup

# --- 1. 페이지 기본 설정 ---
st.set_page_config(page_title="외교부 소식 요약 서비스", page_icon="📰")

st.title("📰 AI 뉴스 요약 서비스")
st.write("Assignment 6: Pre-trained Model(KoBART) 활용")
st.markdown("---")

# --- 2. 모델 불러오기 (인터넷에서 다운로드) ---
# @st.cache_resource는 모델을 한 번만 다운받고 계속 재사용하게 해줍니다.
@st.cache_resource
def load_model():
    # 한국어 뉴스 요약 성능이 좋은 'ainize/kobart-news' 모델을 사용합니다.
    model_name = "ainize/kobart-news"
    
    try:
        tokenizer = PreTrainedTokenizerFast.from_pretrained(model_name)
        model = BartForConditionalGeneration.from_pretrained(model_name)
        return tokenizer, model
    except Exception as e:
        return None, None

# 로딩 애니메이션
with st.spinner('인터넷에서 AI 모델을 다운로드 중입니다... (최초 1회만 오래 걸림)'):
    tokenizer, model = load_model()

if model is None:
    st.error("⚠️ 모델을 불러오는데 실패했습니다. 인터넷 연결을 확인하세요.")
    st.stop()
else:
    st.success("✅ AI 모델 준비 완료! (ainize/kobart-news)")

# --- 3. 요약 함수 정의 ---
def summarize_text(text):
    # 모델이 이해할 수 있게 변환
    input_ids = tokenizer.encode(text, return_tensors="pt")
    
    # 요약문 생성 (뉴스 기사에 적합한 파라미터 설정)
    summary_text_ids = model.generate(
        input_ids=input_ids,
        bos_token_id=model.config.bos_token_id,
        eos_token_id=model.config.eos_token_id,
        length_penalty=2.0,
        max_length=128,
        min_length=32,
        num_beams=4,
    )
    
    # 숫자로 된 결과를 다시 글자로 변환
    return tokenizer.decode(summary_text_ids[0], skip_special_tokens=True)

# --- 4. 스크레이핑 함수 (차단 방지 적용) ---
def scrape_website(url):
    try:
        # 봇이 아닌 척 브라우저 정보(User-Agent) 보내기
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            return f"접속 실패 (상태 코드: {response.status_code})"
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 본문 추출 시도 (뉴스나 블로그의 일반적인 태그 패턴)
        content = ""
        
        # 1순위: article 태그 찾기
        article = soup.find('article')
        if article:
            content = article.get_text()
        else:
            # 2순위: id나 class에 'content', 'article', 'news'가 들어가는 부분 찾기
            paragraphs = soup.find_all('p')
            content = " ".join([p.get_text() for p in paragraphs])
        
        # 공백 정리
        content = content.replace('\n', ' ').strip()
        
        if len(content) < 50: 
            return "내용을 제대로 가져오지 못했습니다. (보안이 강한 사이트)"
            
        return content
    except Exception as e:
        return f"에러 발생: {e}"

# --- 5. 화면 구성 (탭 기능) ---
tab1, tab2 = st.tabs(["🌐 URL로 요약하기", "📝 직접 입력해서 요약하기"])

# [Tab 1] URL 스크레이핑 방식
with tab1:
    st.info("💡 팁: 네이버 뉴스나 일반 언론사 기사 URL이 잘 작동합니다.")
    url_input = st.text_input("기사 URL 입력")
    
    if st.button("URL 요약 시작", key='btn_url'):
        if url_input:
            with st.spinner('사이트 내용을 가져오는 중...'):
                scraped_text = scrape_website(url_input)
                
            if "에러" in scraped_text or "못했습니다" in scraped_text:
                st.warning("⚠️ 스크레이핑에 실패했습니다. 아래 내용을 확인하거나 '직접 입력' 탭을 이용하세요.")
                st.code(scraped_text)
            else:
                st.success(f"글자 수: {len(scraped_text)}자 가져오기 성공!")
                with st.expander("원문 보기"):
                    st.write(scraped_text[:1000] + "...") 
                
                # 요약 수행
                with st.spinner('AI가 요약 중입니다...'):
                    result = summarize_text(scraped_text)
                    st.markdown("### 📄 요약 결과")
                    st.success(result)
        else:
            st.warning("URL을 입력해주세요.")

# [Tab 2] 텍스트 직접 입력 방식 (안전장치)
with tab2:
    st.subheader("기사 본문 직접 붙여넣기")
    st.caption("※ URL 요약이 안 될 경우, 기사 내용을 복사해서 여기에 붙여넣으세요.")
    text_input = st.text_area("텍스트 입력", height=300)
    
    if st.button("텍스트 요약 시작", key='btn_text'):
        if len(text_input) > 30:
            with st.spinner('AI가 요약 중...'):
                try:
                    # 너무 긴 텍스트는 잘라서 처리 (오류 방지)
                    input_text = text_input[:1024] 
                    result = summarize_text(input_text)
                    st.markdown("### 📄 요약 결과")
                    st.success(result)
                except Exception as e:
                    st.error(f"요약 중 오류가 발생했습니다: {e}")
        else:
            st.warning("내용이 너무 짧습니다.")

# --- 6. 사이드바 ---
with st.sidebar:
    st.header("About Service")
    st.write("이 서비스는 `ainize/kobart-news` 모델을 활용하여 제작되었습니다.")
    st.markdown("[Streamlit Docs](https://docs.streamlit.io)")
