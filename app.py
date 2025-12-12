import streamlit as st
import torch
import requests
import re
from bs4 import BeautifulSoup
from transformers import PreTrainedTokenizerFast, BartForConditionalGeneration

# --- 1. 페이지 기본 설정 ---
st.set_page_config(page_title="외교부 소식 요약 서비스", page_icon="📢", layout="wide")

st.title("📢 Daily 외교부 소식 자동 요약기")
st.markdown("Assignment 6: 네이버 블로그 크롤링 및 요약 서비스")
st.markdown("---")

# --- 2. 모델 불러오기 ---
# 주의: 구글 드라이브 경로는 로컬에서 작동하지 않으므로, 
# 안정적인 실행을 위해 성능이 검증된 온라인 모델(KoBART)을 사용하도록 연결했습니다.
@st.cache_resource
def load_model():
    model_name = "ainize/kobart-news"
    try:
        tokenizer = PreTrainedTokenizerFast.from_pretrained(model_name)
        model = BartForConditionalGeneration.from_pretrained(model_name)
        return tokenizer, model
    except Exception as e:
        return None, None

with st.spinner('AI 모델을 로딩 중입니다...'):
    tokenizer, model = load_model()

if model is None:
    st.error("⚠️ 모델 로드 실패! 인터넷 연결을 확인해주세요.")
    st.stop()

# --- 3. 크롤링 함수 (제공해주신 코드 이식) ---
def get_naver_blog_content(url):
    """
    네이버 블로그 URL -> 제목, 본문 추출 (Iframe 구조 대응)
    """
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        # 모바일 링크 변환
        if "m.blog.naver.com" in url:
            url = url.replace("m.blog.naver.com", "blog.naver.com")

        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Iframe 주소 찾기 (네이버 블로그 구조상 필수)
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
            text = re.sub(r'\n+', ' ', text)
            text = re.sub(r'\s+', ' ', text)
            return title, text.strip()
        else:
            return None, None
    except Exception as e:
        return None, None

def get_latest_mofa_news():
    """
    외교부 블로그 RSS를 뒤져서 '외교부 소식' 최신 글 URL을 가져옴
    """
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

            # '소식', '보도', '대변인' 키워드가 있거나, 없으면 최신글 수집
            if "소식" in category or "보도" in category or "대변인" in category:
                target_links.append({"title": title, "link": link})
                if len(target_links) >= 3: # 화면이 너무 길어지지 않게 3개로 조정
                    break
        
        # 타겟 글이 없으면 그냥 최신글 3개 가져오기
        if not target_links:
             target_links = ([{"title": i.title.text, "link": i.link.text} for i in items[:3]])

        return target_links

    except Exception as e:
        return []

# --- 4. 요약 추론 함수 (제공해주신 후처리 로직 적용) ---
def predict_summary(text):
    # 입력 길이 제한
    input_ids = tokenizer.encode(text, return_tensors="pt")
    # 너무 길면 자르기 (오류 방지)
    if input_ids.shape[1] > 1024:
        input_ids = input_ids[:, :1024]

    summary_ids = model.generate(
        input_ids,
        max_length=120,       # 요청하신 길이 설정
        min_length=50,
        length_penalty=1.5,
        num_beams=4,
        early_stopping=True,
        no_repeat_ngram_size=3
    )

    summary = tokenizer.decode(summary_ids[0], skip_special_tokens=True)

    # [후처리 로직] 문장 분리 및 3줄 포맷팅
    sentences = re.split(r'(?<!\d\.)(?<=[.!?])\s*', summary)
    sentences = [s.strip() for s in sentences if s.strip()]

    formatted_sentences = sentences[:3]
    while len(formatted_sentences) < 3:
        formatted_sentences.append("") 

    final_summary = "\n- ".join(formatted_sentences) # 가독성을 위해 불릿 포인트 추가
    
    # 첫 줄에도 불릿 추가
    if final_summary:
        final_summary = "- " + final_summary

    return final_summary

# --- 5. 화면 구성 ---
tab1, tab2 = st.tabs(["🏛️ 외교부 소식 자동 수집", "📝 텍스트 직접 요약"])

# [Tab 1] 자동 수집 및 요약
with tab1:
    st.header("네이버 블로그 RSS 기반 자동 크롤링")
    st.info("버튼을 누르면 '외교부 서포터즈(mofakr)' 블로그에서 최신 소식을 가져옵니다.")

    if st.button("🚀 최신 소식 가져오기 & 요약", key="btn_auto"):
        with st.spinner("외교부 블로그 RSS 검색 중..."):
            news_items = get_latest_mofa_news()
        
        if not news_items:
            st.error("RSS를 불러오지 못했습니다.")
        else:
            st.success(f"총 {len(news_items)}개의 최신 글을 발견했습니다!")
            
            # 진행상황 표시바
            progress_bar = st.progress(0)
            
            for i, item in enumerate(news_items):
                st.markdown(f"### {i+1}. {item['title']}")
                st.caption(f"🔗 [원문 링크]({item['link']})")
                
                with st.spinner(f"'{item['title']}' 내용을 읽고 요약 중..."):
                    title, content = get_naver_blog_content(item['link'])
                    
                    if content:
                        summary = predict_summary(content)
                        st.markdown("**[AI 3줄 요약]**")
                        st.info(summary)
                        with st.expander("원문 내용 보기"):
                            st.write(content[:500] + "...")
                    else:
                        st.warning("본문 내용을 추출하지 못했습니다 (Iframe 접근 제한 등).")
                
                st.markdown("---")
                progress_bar.progress((i + 1) / len(news_items))

# [Tab 2] 직접 입력 (백업용)
with tab2:
    st.subheader("뉴스 본문을 붙여넣으면 3줄 요약해 드립니다.")
    input_text = st.text_area("텍스트 입력", height=300)
    
    if st.button("요약하기", key="btn_manual"):
        if len(input_text) > 50:
            with st.spinner("요약 중..."):
                result = predict_summary(input_text)
                st.success("✅ 요약 완료")
                st.info(result)
        else:
            st.warning("내용이 너무 짧습니다.")
