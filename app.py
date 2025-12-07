import streamlit as st
import torch
from transformers import PreTrainedTokenizerFast, BartForConditionalGeneration
import requests
from bs4 import BeautifulSoup
import re
import trafilatura  # [핵심] 강력한 크롤링 도구

# ==========================================
# 1. 페이지 및 모델 설정
# ==========================================
st.set_page_config(page_title="외교부 소식 요약 봇", page_icon="🤖")

@st.cache_resource
def load_model():
    try:
        # 깃허브 용량/LFS 문제 해결을 위해 Hugging Face Hub의 공개 모델 사용
        model_name = "gogamza/kobart-summarization" 
        tokenizer = PreTrainedTokenizerFast.from_pretrained(model_name)
        model = BartForConditionalGeneration.from_pretrained(model_name)
        return tokenizer, model
    except Exception as e:
        st.error(f"모델 로딩 실패: {e}")
        return None, None

tokenizer, model = load_model()

# ==========================================
# 2. [최종 해결책] Trafilatura 크롤링 함수
# ==========================================
def get_naver_blog_content(url):
    """
    일반 requests 대신 trafilatura 라이브러리를 사용합니다.
    이 라이브러리는 네이버 블로그의 복잡한 구조와 봇 차단을
    더 효과적으로 우회하여 본문만 추출해냅니다.
    """
    if not url:
        return "에러", "URL이 없습니다."

    try:
        # 1. 모바일 주소 변환 (모바일 페이지가 크롤링 성공률이 높음)
        if "m.blog.naver.com" in url:
            target_url = url.replace("m.blog.naver.com", "blog.naver.com")
        else:
            target_url = url

        # 2. trafilatura로 다운로드 시도 (네이버 차단 우회 시도)
        downloaded = trafilatura.fetch_url(target_url)
        
        # 3. 실패 시, PostView 전용 주소로 재시도 (2차 시도)
        if downloaded is None:
            match = re.search(r'blog\.naver\.com/([a-zA-Z0-9_]+)/([0-9]+)', target_url)
            if match:
                blog_id = match.group(1)
                log_no = match.group(2)
                # Iframe 없는 순수 본문 URL
                final_url = f"https://blog.naver.com/PostView.naver?blogId={blog_id}&logNo={log_no}"
                downloaded = trafilatura.fetch_url(final_url)

        # 4. 그래도 없으면 실패 처리
        if downloaded is None:
            return "접속 실패", None

        # 5. 본문 텍스트 추출
        result_text = trafilatura.extract(downloaded, include_comments=False, include_tables=False, include_links=False)
        
        # 제목 추출 (메타 태그 활용)
        soup = BeautifulSoup(downloaded, 'html.parser')
        og_title = soup.select_one('meta[property="og:title"]')
        title = og_title['content'] if og_title else "제목 없음"

        if result_text:
            # 줄바꿈 정리
            text = re.sub(r'\n+', ' ', result_text)
            return title, text.strip()
        else:
            return title, None

    except Exception as e:
        return "에러", f"크롤링 시스템 에러: {e}"

# ==========================================
# 3. RSS 파싱 함수 (제목 깨짐 해결 + 필터링)
# ==========================================
def clean_html_title(raw_html):
    """제목에 붙은 지저분한 태그(CDATA 등) 제거"""
    if not raw_html: return ""
    clean = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', raw_html) # CDATA 제거
    clean = re.sub(r'<.*?>', '', clean) # HTML 태그 제거
    clean = re.sub(r'&[a-z]+;', '', clean) # 특수문자 제거
    return clean.strip()

def get_latest_mofa_news():
    rss_url = "https://rss.blog.naver.com/mofakr.xml"
    
    # 일반 브라우저처럼 보이게 하는 헤더
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(rss_url, headers=headers, timeout=5)
        # lxml 없어도 되도록 html.parser 사용
        soup = BeautifulSoup(response.content, 'html.parser') 
        
        items = soup.find_all('item')
        target_links = []
        
        for item in items:
            # RSS 태그 안전하게 가져오기
            category = item.category.text if item.category else ""
            raw_title = item.title.text if item.title else ""
            link = item.link.text.strip() if item.link else ""
            
            # 제목 정제
            title = clean_html_title(raw_title)

            if not link: continue

            # [필터링] '소식', '보도', '대변인' 키워드가 들어간 글만 수집
            if "소식" in category or "보도" in category or "대변인" in category or "외교부" in category:
                target_links.append({"title": title, "link": link})
                if len(target_links) >= 5: # 5개 모으면 끝
                    break
        
        # 필터링 된 게 없으면 최신글 3개라도 가져옴 (비상용)
        if not target_links and items:
             for i in items[:3]:
                t = clean_html_title(i.title.text)
                l = i.link.text.strip()
                if l: # 링크가 있을 때만
                    target_links.append({"title": t, "link": l})

        return target_links

    except Exception as e:
        print(f"RSS 에러: {e}")
        return []

# ==========================================
# 4. 요약 함수 (KoBART)
# ==========================================
def predict_summary(text):
    if not text or len(text) < 50:
        return "요약할 내용이 너무 짧거나 본문을 가져오지 못했습니다."

    # 입력 데이터 변환
    input_ids = tokenizer.encode(text, return_tensors="pt", max_length=1024, truncation=True)

    # 요약문 생성
    summary_text_ids = model.generate(
        input_ids=input_ids,
        bos_token_id=model.config.bos_token_id,
        eos_token_id=model.config.eos_token_id,
        length_penalty=1.2,
        max_length=256,
        min_length=30,
        num_beams=4,
        early_stopping=True,
        no_repeat_ngram_size=3
    )
    
    summary = tokenizer.decode(summary_text_ids[0], skip_special_tokens=True)

    # 문장부호 정리
    if summary and summary[-1] not in ['.', '!', '?']:
        last_punctuation = max(summary.rfind('.'), summary.rfind('!'), summary.rfind('?'))
        if last_punctuation != -1:
            summary = summary[:last_punctuation+1]

    return summary

# ==========================================
# 5. 메인 UI
# ==========================================
st.title("📰 외교부 소식 자동 요약 봇")
st.write("인공지능이 외교부 블로그의 주요 소식을 3줄로 요약해 드립니다.")

if model is None:
    st.error("⚠️ 모델 로딩 실패. 잠시 후 다시 시도해주세요.")
else:
    st.success("AI 모델 준비 완료! (Ready)")

tab1, tab2 = st.tabs(["🔗 URL 직접 입력", "📢 외교부 최신 소식 (자동)"])

# [Tab 1]
with tab1:
    st.subheader("뉴스/블로그 주소 입력")
    input_url = st.text_input("요약하고 싶은 네이버 블로그 URL을 입력하세요:")
    
    if st.button("요약 시작", key="btn1"):
        if input_url:
            with st.spinner('분석 중...'):
                title, raw_text = get_naver_blog_content(input_url)
                
                if raw_text:
                    summary = predict_summary(raw_text)
                    st.markdown(f"### 📄 {title}")
                    st.info(summary)
                    with st.expander("원본 내용 보기"):
                        st.write(raw_text)
                else:
                    st.error("본문을 가져오지 못했습니다. (접근 권한 또는 삭제된 글)")

# [Tab 2]
with tab2:
    st.subheader("외교부 주요 소식 (Top 5)")
    st.write("버튼을 누르면 최신 소식을 가져와 요약합니다.")
    
    if st.button("최신 소식 가져오기", key="btn2"):
        with st.spinner('외교부 블로그 스캔 중... (약 10초 소요)'):
            news_items = get_latest_mofa_news()
            
            if not news_items:
                st.warning("최신 소식을 가져오지 못했습니다. 잠시 후 다시 시도해주세요.")
            else:
                st.success(f"총 {len(news_items)}개의 소식을 가져왔습니다.")
                
                for i, item in enumerate(news_items):
                    st.markdown("---")
                    st.markdown(f"**[{i+1}] {item['title']}**")
                    
                    # 크롤링 시도
                    _, content = get_naver_blog_content(item['link'])
                    
                    if content:
                        summary = predict_summary(content)
                        st.success(summary)
                    else:
                        # 2중 3중으로 뚫으려 시도했지만, 그래도 네이버가 클라우드 IP를 원천 차단한 경우
                        st.warning("🔒 네이버 보안 정책으로 인해 본문 요약을 할 수 없습니다.")
                        st.write(f"👉 [원문 보러가기]({item['link']})")
