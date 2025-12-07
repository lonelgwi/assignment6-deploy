import streamlit as st
import torch
from transformers import PreTrainedTokenizerFast, BartForConditionalGeneration
import requests
from bs4 import BeautifulSoup
import re
import trafilatura

# ==========================================
# 1. 페이지 및 모델 설정
# ==========================================
st.set_page_config(page_title="외교부 소식 요약 봇", page_icon="🤖")

@st.cache_resource
def load_model():
    try:
        model_name = "gogamza/kobart-summarization" 
        tokenizer = PreTrainedTokenizerFast.from_pretrained(model_name)
        model = BartForConditionalGeneration.from_pretrained(model_name)
        return tokenizer, model
    except Exception as e:
        st.error(f"모델 로딩 실패: {e}")
        return None, None

tokenizer, model = load_model()

# ==========================================
# 2. 크롤링 함수 (Trafilatura + 타임아웃 강화)
# ==========================================
def get_naver_blog_content(url):
    """
    네이버 블로그 본문 추출 시도.
    실패 확률이 높으므로 짧은 타임아웃을 둡니다.
    """
    if not url: return "에러", None

    try:
        # 모바일 주소로 변환 (성공률이 조금 더 높음)
        if "m.blog.naver.com" in url:
            target_url = url.replace("m.blog.naver.com", "blog.naver.com")
        else:
            target_url = url

        # 1차 시도: Trafilatura
        downloaded = trafilatura.fetch_url(target_url)
        
        # 2차 시도: PostView 주소 직접 조립
        if downloaded is None:
            match = re.search(r'blog\.naver\.com/([a-zA-Z0-9_]+)/([0-9]+)', target_url)
            if match:
                final_url = f"https://blog.naver.com/PostView.naver?blogId={match.group(1)}&logNo={match.group(2)}"
                downloaded = trafilatura.fetch_url(final_url)

        if downloaded is None:
            return "차단됨", None

        # 텍스트 추출
        result_text = trafilatura.extract(downloaded, include_comments=False, include_tables=False, include_links=False)
        
        # 제목 추출
        soup = BeautifulSoup(downloaded, 'html.parser')
        og_title = soup.select_one('meta[property="og:title"]')
        title = og_title['content'] if og_title else "제목 없음"

        if result_text:
            text = re.sub(r'\n+', ' ', result_text)
            return title, text.strip()
        else:
            return title, None

    except Exception:
        return "에러", None

# ==========================================
# 3. RSS 파싱 함수 (핵심: Description까지 확보)
# ==========================================
def clean_text(raw_html):
    """HTML 태그와 특수문자를 제거하여 순수 텍스트만 남김"""
    if not raw_html: return ""
    clean = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', raw_html) # CDATA 제거
    clean = re.sub(r'<.*?>', '', clean) # HTML 태그 제거
    clean = re.sub(r'&[a-z]+;', ' ', clean) # 특수문자 제거
    return clean.strip()

def get_latest_mofa_news():
    rss_url = "https://rss.blog.naver.com/mofakr.xml"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        response = requests.get(rss_url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.content, 'html.parser') # xml 파서 대신 html.parser 사용 (호환성)
        
        items = soup.find_all('item')
        target_list = []
        
        for item in items:
            category = item.category.text if item.category else ""
            title = clean_text(item.title.text if item.title else "")
            link = item.link.text.strip() if item.link else ""
            
            # [비상용] RSS에 포함된 본문 요약본(Description) 가져오기
            description = clean_text(item.description.text if item.description else "")

            if not link: continue

            # 필터링
            if "소식" in category or "보도" in category or "대변인" in category or "외교부" in category:
                target_list.append({
                    "title": title, 
                    "link": link,
                    "desc": description  # 비상용 본문 저장
                })
                if len(target_list) >= 5: break
        
        # 필터링 결과가 없으면 최신 3개라도 가져옴 (비상용)
        if not target_list and items:
             for i in items[:3]:
                t = clean_text(i.title.text)
                l = i.link.text.strip()
                d = clean_text(i.description.text if i.description else "")
                target_list.append({"title": t, "link": l, "desc": d})

        return target_list

    except Exception as e:
        print(f"RSS 에러: {e}")
        return []

# ==========================================
# 4. 요약 함수
# ==========================================
def predict_summary(text):
    if not text or len(text) < 20: # 기준 완화
        return "요약할 내용이 부족합니다."

    # 입력 데이터 변환
    input_ids = tokenizer.encode(text, return_tensors="pt", max_length=1024, truncation=True)

    # 요약문 생성
    summary_text_ids = model.generate(
        input_ids=input_ids,
        bos_token_id=model.config.bos_token_id,
        eos_token_id=model.config.eos_token_id,
        length_penalty=1.0, # 패널티 완화
        max_length=128,
        min_length=20,      # 최소 길이 완화
        num_beams=4,
        early_stopping=True
    )
    
    summary = tokenizer.decode(summary_text_ids[0], skip_special_tokens=True)
    return summary

# ==========================================
# 5. 메인 UI
# ==========================================
st.title("📰 외교부 소식 자동 요약 봇")
st.write("인공지능이 외교부 블로그의 주요 소식을 3줄로 요약해 드립니다.")

if model is None:
    st.error("⚠️ 모델 로딩 실패.")
else:
    st.success("AI 모델 준비 완료! (Ready)")

tab1, tab2 = st.tabs(["🔗 URL 직접 입력", "📢 외교부 최신 소식 (자동)"])

with tab1:
    st.subheader("뉴스/블로그 주소 입력")
    input_url = st.text_input("URL 입력:")
    if st.button("요약 시작", key="btn1"):
        if input_url:
            with st.spinner('분석 중...'):
                title, raw_text = get_naver_blog_content(input_url)
                if raw_text:
                    st.markdown(f"### 📄 {title}")
                    st.info(predict_summary(raw_text))
                    with st.expander("원본 보기"): st.write(raw_text)
                else:
                    st.error("본문 접근이 차단되었습니다.")

with tab2:
    st.subheader("외교부 주요 소식 (Top 5)")
    st.write("본문 접속이 차단될 경우, 네이버가 제공한 미리보기 내용을 대신 요약합니다.")
    
    if st.button("최신 소식 가져오기", key="btn2"):
        with st.spinner('소식 가져오는 중...'):
            news_items = get_latest_mofa_news()
            
            if not news_items:
                st.warning("RSS 연결 실패.")
            else:
                st.success(f"총 {len(news_items)}개의 소식 확인")
                
                for i, item in enumerate(news_items):
                    st.markdown("---")
                    st.markdown(f"**[{i+1}] {item['title']}**")
                    
                    # 1. 크롤링 시도
                    _, content = get_naver_blog_content(item['link'])
                    
                    if content:
                        # 성공 시 본문 요약
                        st.success(predict_summary(content))
                    elif item['desc']:
                        # [비상용] 실패 시 RSS Description 요약
                        st.warning("🔒 본문 접속 차단됨 → 미리보기 내용으로 대체 요약합니다.")
                        st.info(predict_summary(item['desc']))
                    else:
                        st.error("요약할 내용을 찾을 수 없습니다.")
                    
                    st.caption(f"[원문 보러가기]({item['link']})")
