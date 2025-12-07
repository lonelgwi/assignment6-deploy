import streamlit as st
import torch
from transformers import PreTrainedTokenizerFast, BartForConditionalGeneration
import requests
from bs4 import BeautifulSoup
import re

# ==========================================
# 1. 페이지 및 모델 설정
# ==========================================
st.set_page_config(page_title="외교부 소식 요약 봇", page_icon="🤖")

@st.cache_resource
def load_model():
    try:
        # 깃허브 용량 제한 없이 실행되도록 공개된 KoBART 모델 사용
        # (제공해주신 코드의 로직을 그대로 사용하되, 모델 파일만 온라인에서 가져옵니다)
        model_name = "gogamza/kobart-summarization" 
        tokenizer = PreTrainedTokenizerFast.from_pretrained(model_name)
        model = BartForConditionalGeneration.from_pretrained(model_name)
        return tokenizer, model
    except Exception as e:
        st.error(f"모델 로딩 중 오류가 발생했습니다: {e}")
        return None, None

tokenizer, model = load_model()

# ==========================================
# 2. 크롤링 함수 (제공해주신 로직 적용)
# ==========================================
def get_naver_blog_content(url):
    """
    네이버 블로그 URL -> 제목, 본문 추출 (Iframe 구조 대응)
    """
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        # 모바일 주소 변환
        if "m.blog.naver.com" in url:
            url = url.replace("m.blog.naver.com", "blog.naver.com")

        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Iframe 대응
        iframe = soup.select_one('iframe#mainFrame')
        if iframe:
            real_url = "https://blog.naver.com" + iframe['src']
            response = requests.get(real_url, headers=headers)
            soup = BeautifulSoup(response.text, 'html.parser')

        # 제목 추출 (.se-title-text 또는 .htitle)
        title_elem = soup.select_one('.se-title-text') or soup.select_one('.htitle')
        title = title_elem.text.strip() if title_elem else "제목 없음"

        # 본문 추출 (.se-main-container 또는 #postViewArea)
        content_elem = soup.select_one('.se-main-container') or soup.select_one('#postViewArea')

        if content_elem:
            text = content_elem.text
            # 불필요한 줄바꿈 및 공백 정리
            text = re.sub(r'\n+', ' ', text)
            text = re.sub(r'\s+', ' ', text)
            return title, text.strip()
        else:
            return title, None

    except Exception as e:
        return "에러", f"크롤링 에러: {e}"

# ==========================================
# 3. RSS 파싱 함수 (카테고리 필터링 추가)
# ==========================================
def get_latest_mofa_news():
    """
    외교부 블로그 RSS를 뒤져서 '소식/보도/대변인' 관련 글만 가져옴
    """
    rss_url = "https://rss.blog.naver.com/mofakr.xml"
    
    try:
        response = requests.get(rss_url)
        # lxml이 설치되어 있지 않을 경우를 대비해 xml 파싱 시도
        try:
            soup = BeautifulSoup(response.content, 'xml')
        except:
            soup = BeautifulSoup(response.content, 'html.parser')
            
        items = soup.find_all('item')
        
        target_links = []
        
        for item in items:
            # 카테고리 태그 확인
            category = item.category.text if item.category else ""
            title = item.title.text
            link = item.link.text
            
            # [필터링 로직] 사용자가 원한 '외교부 소식' 관련 키워드
            if "소식" in category or "보도" in category or "대변인" in category or "외교부" in category:
                target_links.append({"title": title, "link": link})
                
                # 최신 5개만 수집하면 중단
                if len(target_links) >= 5: 
                    break
        
        # 만약 타겟 카테고리 글이 하나도 없으면 최신글 3개라도 가져오기 (비상용)
        if not target_links and items:
            target_links = [{"title": i.title.text, "link": i.link.text} for i in items[:3]]
            
        return target_links

    except Exception as e:
        st.error(f"RSS 파싱 실패: {e}")
        return []

# ==========================================
# 4. 요약 함수 (후처리 로직 적용)
# ==========================================
def predict_summary(text):
    if not text or len(text) < 50:
        return "요약할 내용이 너무 짧거나 본문을 가져오지 못했습니다."

    # 입력 길이 제한 (Truncation)
    input_ids = tokenizer.encode(text, return_tensors="pt", max_length=1024, truncation=True)

    # 모델 생성 옵션 (제공해주신 파라미터 적용)
    summary_text_ids = model.generate(
        input_ids=input_ids,
        bos_token_id=model.config.bos_token_id,
        eos_token_id=model.config.eos_token_id,
        length_penalty=1.2,   # 자연스러운 길이 유도
        max_length=256,       # 길이 확장
        min_length=30,
        num_beams=4,
        early_stopping=True,
        no_repeat_ngram_size=3
    )
    
    summary = tokenizer.decode(summary_text_ids[0], skip_special_tokens=True)

    # [후처리] 문장 끊김 방지
    if summary and summary[-1] not in ['.', '!', '?']:
        last_punctuation = max(summary.rfind('.'), summary.rfind('!'), summary.rfind('?'))
        if last_punctuation != -1:
            summary = summary[:last_punctuation+1]

    return summary

# ==========================================
# 5. 메인 UI 화면 구성
# ==========================================

st.title("📰 외교부 소식 자동 요약 봇")
st.write("인공지능이 외교부 블로그의 주요 소식을 3줄로 요약해 드립니다.")

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
            with st.spinner('크롤링 및 요약 중입니다...'):
                title, raw_text = get_naver_blog_content(input_url)
                
                if raw_text:
                    summary = predict_summary(raw_text)
                    st.markdown(f"### 📄 {title}")
                    st.info(summary)
                    with st.expander("원본 내용 보기"):
                        st.write(raw_text)
                else:
                    st.error("본문을 가져오지 못했습니다. (접근 권한 혹은 삭제된 글)")

# [Tab 2] 외교부 최신 소식 (자동 수집)
with tab2:
    st.subheader("외교부 주요 소식 (Top 5)")
    st.write("아래 버튼을 누르면 '외교부 소식/보도' 카테고리의 최신 글을 가져옵니다.")
    
    if st.button("최신 소식 가져오기", key="btn2"):
        with st.spinner('외교부 블로그를 스캔하는 중입니다...'):
            # 1. RSS 리스트 확보
            news_items = get_latest_mofa_news()
            
            if not news_items:
                st.warning("가져올 소식이 없거나 연결에 실패했습니다.")
            else:
                st.success(f"총 {len(news_items)}개의 최신 소식을 발견했습니다!")
                
                # 2. 각 게시글 순회하며 크롤링 & 요약
                for i, item in enumerate(news_items):
                    st.markdown("---")
                    st.markdown(f"**[{i+1}] {item['title']}**")
                    
                    # 상세 내용 크롤링
                    _, content = get_naver_blog_content(item['link'])
                    
                    if content:
                        # 요약 실행
                        summary = predict_summary(content)
                        st.success(summary)
                    else:
                        st.caption("본문 내용을 불러올 수 없습니다.")
