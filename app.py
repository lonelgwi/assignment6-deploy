import streamlit as st
import torch
from transformers import PreTrainedTokenizerFast, BartForConditionalGeneration
import requests
from bs4 import BeautifulSoup
import re

# 1. 페이지 기본 설정
st.set_page_config(page_title="외교부 소식 요약 봇", page_icon="🤖")

# 2. 모델 불러오기 (파일 없어도 됨! 인터넷에서 받아옴)
@st.cache_resource
def load_model():
    try:
        # 깃허브 용량 문제 해결을 위해 공개된 'KoBART 요약 모델'을 사용합니다.
        model_name = "gogamza/kobart-summarization" 
        tokenizer = PreTrainedTokenizerFast.from_pretrained(model_name)
        model = BartForConditionalGeneration.from_pretrained(model_name)
        return tokenizer, model
    except Exception as e:
        st.error(f"모델 로딩 중 오류가 발생했습니다: {e}")
        return None, None

tokenizer, model = load_model()

# 3. 텍스트 요약 함수
def summarize_text(text):
    if not text or len(text) < 50:
        return "요약할 내용이 너무 짧습니다."
    
    # 모델이 읽기 좋게 입력 데이터로 변환
    input_ids = tokenizer.encode(text, return_tensors="pt")

    # 모델이 요약문 생성 (옵션 조절로 품질 향상)
    summary_text_ids = model.generate(
        input_ids=input_ids,
        bos_token_id=model.config.bos_token_id,
        eos_token_id=model.config.eos_token_id,
        length_penalty=2.0,
        max_length=128,
        min_length=32,
        num_beams=4,
    )
    
    return tokenizer.decode(summary_text_ids[0], skip_special_tokens=True)

# 4. 네이버 블로그 본문 크롤링 함수 (Iframe 해결)
def get_naver_blog_content(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        
        # 모바일 주소 대응
        if "m.blog.naver.com" in url:
            url = url.replace("m.blog.naver.com", "blog.naver.com")

        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')

        # 네이버 블로그는 iframe 안에 진짜 내용이 숨어있음
        iframe = soup.select_one("iframe#mainFrame")
        if iframe:
            real_url = "https://blog.naver.com" + iframe["src"]
            response = requests.get(real_url, headers=headers)
            soup = BeautifulSoup(response.text, 'html.parser')

        # 본문 추출 (제목과 본문)
        title_elem = soup.select_one('.se-title-text') or soup.select_one('.htitle')
        title = title_elem.text.strip() if title_elem else "제목 없음"

        content_elem = soup.select_one('.se-main-container') or soup.select_one('#postViewArea')
        
        if content_elem:
            text = content_elem.text
            text = re.sub(r'\n+', ' ', text) # 줄바꿈 정리
            return title, text.strip()[:2000] # 너무 길면 자름
        else:
            return title, None

    except Exception as e:
        return "에러", f"크롤링 실패: {e}"

# 5. [업그레이드] 외교부 RSS에서 최신 글 5개 가져오기
def get_latest_mofa_news():
    rss_url = "https://rss.blog.naver.com/mofakr.xml"
    try:
        response = requests.get(rss_url)
        # 'xml' 파서 대신 'html.parser'를 사용하여 별도의 lxml 설치 없이도 동작하게 수정
        soup = BeautifulSoup(response.content, 'html.parser')
        items = soup.find_all('item')
        
        news_list = []
        count = 0
        
        for item in items:
            # 제목과 링크 추출
            title = item.title.text
            link = item.link.text
            
            # 5개까지만 담기
            news_list.append({"title": title, "link": link})
            count += 1
            if count >= 5:
                break
                
        return news_list
    except Exception as e:
        return []

# --- 메인 화면 구성 (UI) ---

st.title("📰 외교부 소식 자동 요약 봇")
st.write("인공지능이 외교부의 긴 소식을 3줄로 핵심만 요약해 드립니다.")

if model is None:
    st.error("⚠️ 모델을 불러오지 못했습니다. 잠시 후 다시 시도해주세요.")
else:
    st.success("AI 모델 준비 완료! (Ready)")

# 탭 구성
tab1, tab2 = st.tabs(["🔗 URL 직접 입력", "📢 외교부 최신 소식 (자동)"])

# [Tab 1] URL 요약
with tab1:
    st.subheader("뉴스/블로그 주소 입력")
    input_url = st.text_input("요약하고 싶은 네이버 블로그 URL을 입력하세요:")
    
    if st.button("요약 시작", key="btn1"):
        if input_url:
            with st.spinner('내용을 가져와서 요약 중입니다...'):
                title, raw_text = get_naver_blog_content(input_url)
                
                if raw_text:
                    summary = summarize_text(raw_text)
                    st.markdown(f"### 📄 {title}")
                    st.info(summary) # 요약 결과 출력
                    with st.expander("원본 내용 보기"):
                        st.write(raw_text)
                else:
                    st.error("본문을 가져오지 못했습니다. 접근 권한이 없거나 삭제된 글일 수 있습니다.")

# [Tab 2] 외교부 최신 소식 (요청하신 기능!)
with tab2:
    st.subheader("외교부 최신 소식 (Top 5)")
    st.write("버튼을 누르면 외교부 블로그의 최신 글 5개를 가져와서 자동으로 요약합니다.")
    
    if st.button("최신 소식 가져오기", key="btn2"):
        with st.spinner('외교부 블로그를 방문해서 최신 글을 읽고 있습니다... (약 10~20초 소요)'):
            # 1. RSS에서 최신 글 리스트 가져오기
            news_items = get_latest_mofa_news()
            
            if not news_items:
                st.error("외교부 소식을 가져오는데 실패했습니다.")
            
            # 2. 각 글마다 크롤링 + 요약 실행
            for i, item in enumerate(news_items):
                st.markdown(f"---") # 구분선
                st.markdown(f"### {i+1}. {item['title']}") # 제목 출력
                
                # 본문 긁어오기
                _, content = get_naver_blog_content(item['link'])
                
                if content:
                    # 요약하기
                    summary = summarize_text(content)
                    st.success(summary) # 요약 결과 (초록색 박스)
                else:
                    st.warning("본문을 읽을 수 없는 게시글입니다.")
