import streamlit as st
import torch
import requests
import re
from bs4 import BeautifulSoup
from transformers import PreTrainedTokenizerFast, BartForConditionalGeneration

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="외교부 소식 요약 서비스", page_icon="📢", layout="wide")

st.title("📢 외교부 소식 자동 3줄 요약기")
st.markdown("Assignment 6: 네이버 블로그 크롤링 및 KoBART 요약 서비스")
st.markdown("---")

# --- 2. 모델 불러오기 (에러 추적 기능 포함) ---
@st.cache_resource
def load_model():
    model_name = "ainize/kobart-news"
    try:
        # 모델과 토크나이저 다운로드
        tokenizer = PreTrainedTokenizerFast.from_pretrained(model_name)
        model = BartForConditionalGeneration.from_pretrained(model_name)
        return tokenizer, model, None # 성공 시 에러 메시지 없음
    except Exception as e:
        return None, None, str(e) # 실패 시 에러 메시지 반환

with st.spinner('AI 모델(KoBART)을 깨우는 중입니다... (최초 1회 다운로드)'):
    tokenizer, model, error_msg = load_model()

# 모델 로딩 실패 시 상세 이유 출력
if model is None:
    st.error("⚠️ 치명적 오류: 모델을 불러오지 못했습니다.")
    st.error(f"🔍 에러 상세: {error_msg}")
    st.warning("💡 팁: 'ImportError'나 'protobuf' 관련 에러라면 터미널에 `pip install protobuf sentencepiece`를 입력하세요.")
    st.stop() # 여기서 코드 실행 중단

# --- 3. 크롤링 함수 (RSS & Iframe 대응) ---
def get_naver_blog_content(url):
    """네이버 블로그의 Iframe을 뚫고 실제 본문을 가져옵니다."""
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        # 모바일 링크 복구
        if "m.blog.naver.com" in url:
            url = url.replace("m.blog.naver.com", "blog.naver.com")

        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Iframe src 찾기
        iframe = soup.select_one('iframe#mainFrame')
        if iframe:
            real_url = "https://blog.naver.com" + iframe['src']
            response = requests.get(real_url, headers=headers)
            soup = BeautifulSoup(response.text, 'html.parser')

        # 제목 추출
        title_elem = soup.select_one('.se-title-text') or soup.select_one('.htitle')
        title = title_elem.text.strip() if title_elem else "제목 없음"

        # 본문 추출
        content_elem = soup.select_one('.se-main-container') or soup.select_one('#postViewArea')

        if content_elem:
            text = content_elem.text
            text = re.sub(r'\n+', ' ', text) # 줄바꿈 정리
            text = re.sub(r'\s+', ' ', text) # 공백 정리
            return title, text.strip()
        else:
            return title, None
    except Exception as e:
        return "에러 발생", None

def get_latest_mofa_news():
    """외교부 블로그 RSS에서 최신 뉴스 링크를 가져옵니다."""
    rss_url = "https://rss.blog.naver.com/mofakr.xml"
    
    try:
        response = requests.get(rss_url)
        soup = BeautifulSoup(response.content, 'xml')
        items = soup.find_all('item')

        target_links = []
        for item in items:
            category = item.category.text if item.category else ""
            title = item.title.text
            link = item.link.text

            # 키워드 필터링
            if any(keyword in category for keyword in ["소식", "보도", "대변인"]):
                target_links.append({"title": title, "link": link})
                if len(target_links) >= 3: break # 3개만 수집
        
        # 필터링 된 게 없으면 그냥 최신글 3개
        if not target_links:
             target_links = [{"title": i.title.text, "link": i.link.text} for i in items[:3]]

        return target_links
    except Exception as e:
        return []

# --- 4. 요약 및 후처리 함수 ---
def predict_summary(text):
    # 입력 길이 자르기 (오류 방지)
    input_ids = tokenizer.encode(text, return_tensors="pt")
    if input_ids.shape[1] > 1024:
        input_ids = input_ids[:, :1024]

    # 모델 생성 (요청하신 파라미터 적용)
    summary_ids = model.generate(
        input_ids,
        max_length=120,       
        min_length=50,
        length_penalty=1.5,
        num_beams=4,
        early_stopping=True,
        no_repeat_ngram_size=3
    )
    
    summary = tokenizer.decode(summary_ids[0], skip_special_tokens=True)

    # [3줄 포맷팅 후처리]
    sentences = re.split(r'(?<!\d\.)(?<=[.!?])\s*', summary)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    formatted = sentences[:3] # 최대 3문장
    
    # 3줄 리스트로 변환 (화면 출력용)
    return formatted

# --- 5. UI 구성 ---
tab1, tab2 = st.tabs(["🏛️ 외교부 소식 자동 수집", "📝 직접 입력 요약"])

# [Tab 1] 자동 수집
with tab1:
    st.header("네이버 블로그 RSS 기반 자동 크롤링")
    st.info("버튼을 누르면 '외교부 서포터즈' 블로그의 최신 글을 가져와 요약합니다.")

    if st.button("🚀 최신 소식 가져오기", key="btn_auto"):
        with st.spinner("RSS 검색 중..."):
            news_items = get_latest_mofa_news()
        
        if not news_items:
            st.error("RSS 연결 실패. 잠시 후 다시 시도해주세요.")
        else:
            st.success(f"총 {len(news_items)}개의 최신 글을 발견했습니다.")
            
            for i, item in enumerate(news_items):
                st.markdown(f"### {i+1}. {item['title']}")
                st.caption(f"[원문 보러가기]({item['link']})")
                
                with st.spinner("본문 읽고 요약 중..."):
                    title, content = get_naver_blog_content(item['link'])
                    
                    if content and len(content) > 50:
                        summary_list = predict_summary(content)
                        st.markdown("**[AI 3줄 요약]**")
                        for s in summary_list:
                            st.write(f"- {s}")
                    else:
                        st.warning("⚠️ 본문 내용을 가져오지 못했습니다. (보안 설정 등)")
                st.markdown("---")

# [Tab 2] 직접 입력
with tab2:
    st.subheader("뉴스 본문을 붙여넣으세요")
    input_text = st.text_area("텍스트 입력", height=200)
    
    if st.button("요약하기", key="btn_manual"):
        if len(input_text) > 30:
            with st.spinner("요약 중..."):
                summary_list = predict_summary(input_text)
                st.success("✅ 요약 완료")
                for s in summary_list:
                    st.write(f"- {s}")
        else:
            st.warning("내용이 너무 짧습니다.")
