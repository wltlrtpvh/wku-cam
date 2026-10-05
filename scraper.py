"""
원광대학교 공지사항 자동 수집 스크립트
------------------------------------
학교 홈페이지의 공지 게시판을 확인해서 새 글이 있으면 Supabase에 저장합니다.
GitHub Actions로 이 스크립트를 주기적으로(예: 1시간마다) 실행하면
서버 없이도 "자동 수집"이 완성됩니다.

사용 전 준비물:
  1. Supabase 프로젝트 (무료) 생성 → https://supabase.com
  2. notices 테이블 생성 (아래 SQL 참고)
  3. 환경변수 SUPABASE_URL, SUPABASE_KEY 설정 (GitHub Actions Secrets에 등록)

--- notices 테이블 생성 SQL (Supabase SQL Editor에서 실행) ---
create table notices (
  id bigint generated always as identity primary key,
  category text not null,
  title text not null,
  url text unique not null,
  posted_date text,
  body text,
  created_at timestamp with time zone default now()
);
alter table notices enable row level security;
create policy "public read" on notices for select using (true);
----------------------------------------------------------
"""

import os
import re
import time
import requests
from bs4 import BeautifulSoup

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; WKUCampusBot/1.0)"}

# 게시판당 최신 몇 개까지 갱신할지. 예전엔 10개라 장학공지(14개)의 오래된 빈 본문이 안 채워졌다.
MAX_ITEMS_PER_BOARD = 15
MAX_RUNTIME_SEC = 480

# 카테고리별 게시판 URL — 학교 홈페이지 개편 시 주소가 바뀔 수 있으니
# 직접 접속해서 주소가 맞는지 가끔 확인해주세요.
BOARDS = {
    "academic":    "https://www.wku.ac.kr/category/notice/academic-notice",
    "scholarship": "https://www.wku.ac.kr/category/notice/scholar-notice",
    "job":         "https://www.wku.ac.kr/category/notice/recruit",
    "campus":      "https://www.wku.ac.kr/category/news/school-news",
}

def fetch_list(category, url):
    """게시판 목록 페이지에서 글 제목과 링크를 뽑아온다."""
    res = requests.get(url, headers=HEADERS, timeout=15)
    print(f"[{category}] 요청 상태코드: {res.status_code}, 응답 길이: {len(res.text)}자")
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")

    candidates = [
        ("h3 a", soup.select("h3 a")),
        ("h2 a", soup.select("h2 a")),
        (".elementor-post__title a", soup.select(".elementor-post__title a")),
        (".entry-title a", soup.select(".entry-title a")),
        ("article a", soup.select("article a")),
        ("table a", soup.select("table a")),
    ]
    for name, found in candidates:
        print(f"[{category}] 선택자 '{name}' → {len(found)}개 발견")

    links = []
    used = None
    for name, found in candidates:
        if len(found) >= 3:
            links = found
            used = name
            break
    print(f"[{category}] 사용한 선택자: {used or '없음 (전부 실패)'}")

    items = []
    for a in links:
        title = a.get_text(strip=True)
        link = a.get("href", "")
        if not title or not link.startswith("http"):
            continue

        date_match = None
        parent = a.find_parent(["li", "article", "tr", "div"])
        if parent:
            text_near = parent.get_text(" ", strip=True)
            m = re.search(r"(20\d{2}[./]\d{2}[./]\d{2})", text_near)
            if m:
                date_match = m.group(1).replace("/", ".")

        items.append({
            "category": category,
            "title": title,
            "url": link,
            "posted_date": date_match or "",
        })

    seen = set()
    unique_items = []
    for it in items:
        if it["url"] not in seen:
            seen.add(it["url"])
            unique_items.append(it)

    # 게시판이 상단 고정글/비정렬 목록을 줘도 "날짜 기준 최신순"으로 고른다.
    # 날짜가 없는 항목은 맨 뒤로 보내고, 같은 날짜끼리는 원래 순서를 유지한다(sorted는 안정 정렬).
    unique_items = sorted(unique_items, key=lambda it: it["posted_date"] or "0000.00.00", reverse=True)

    print(f"[{category}] 최종 추출된 글 수: {len(unique_items)}개")
    if unique_items:
        print(f"[{category}] 첫 번째 글 예시: {unique_items[0]['title']}")
    else:
        print(f"[{category}] 디버그용 HTML 앞부분 500자:\n{res.text[:500]}")
    return unique_items

def fetch_body(url):
    """상세 페이지에서 본문 텍스트를 가져온다 (실패해도 넘어감).

    이 사이트(Elementor 기반)는 페이지 안에 "관련 글" 미리보기 카드들도
    <article> 태그로 되어 있어서, 단순히 첫 번째 <article>을 고르면
    본문이 아니라 엉뚱한 다른 글의 제목/날짜가 딸려온다.
    그래서 실제 본문 위젯(theme-post-content)을 먼저 찾고,
    없으면 entry-content, 그래도 없으면 main 순서로 넘어간다.
    """
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        # 학사/장학/일부 채용 글은 신형(Elementor)이 아니라 구형 ComBoard 템플릿으로 내려온다.
        # 이 경우 본문은 td.styleBoardViewContent 안(.bbs-div-kcy)에 있고 main/.entry-content는 없다.
        content = (
            soup.select_one(".elementor-widget-theme-post-content .elementor-widget-container")
            or soup.select_one('[data-widget_type^="theme-post-content"] .elementor-widget-container')
            or soup.select_one("td.styleBoardViewContent")
            or soup.select_one(".bbs-div-kcy")
            or soup.select_one(".entry-content")
            or soup.select_one("main")
        )
        if content:
            text = content.get_text("\n", strip=True)
            return text[:2000]  # 너무 길면 잘라서 저장
    except Exception as e:
        print(f"본문 가져오기 실패: {url} ({e})")
    return ""

def save_to_supabase(notice):
    """Supabase REST API로 글을 저장한다.

    url이 이미 있으면 내용(특히 body)을 최신 값으로 덮어쓴다.
    (예전엔 중복이면 그냥 무시해서, 한 번 잘못 저장된 빈 본문이
    영영 안 고쳐지는 문제가 있었다.)
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        # dry-run: 파싱 결과만 확인할 수 있게 날짜/본문 길이를 같이 찍는다.
        print(f"[dry-run] {notice['posted_date'] or '날짜없음'} | 본문 {len(notice.get('body', ''))}자 | {notice['title']}")
        return

    # 본문을 못 가져온(빈) 경우엔 body 키를 빼고 보낸다. merge-duplicates는 보낸 컬럼만 갱신하므로,
    # 일시적인 타임아웃으로 기존에 잘 저장된 본문이 빈 값으로 덮어써지는 걸 막는다.
    notice = {k: v for k, v in notice.items() if not (k == "body" and not v)}

    endpoint = f"{SUPABASE_URL}/rest/v1/notices?on_conflict=url"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",  # url이 중복이면 최신 내용으로 갱신
    }
    res = requests.post(endpoint, headers=headers, json=notice, timeout=15)
    if res.status_code in (200, 201, 409):
        print("저장됨:", notice["title"])
    else:
        print("저장 실패:", res.status_code, res.text[:200])

def main():
    total = 0
    started = time.time()
    for category, url in BOARDS.items():
        # 일부 시간대에 실행이 15분 가까이 걸리다 취소된 이력이 있어서(응답 지연 추정),
        # 전체 실행 시간에 상한을 두고 넘으면 남은 게시판은 다음 실행으로 넘긴다.
        if time.time() - started > MAX_RUNTIME_SEC:
            print(f"[{category}] 실행 시간 상한({MAX_RUNTIME_SEC}초) 초과 — 이번 실행은 여기서 종료")
            break
        try:
            items = fetch_list(category, url)
        except Exception as e:
            print(f"[{category}] 목록 가져오기 실패: {e}")
            continue

        for item in items[:MAX_ITEMS_PER_BOARD]:
            if time.time() - started > MAX_RUNTIME_SEC:
                print(f"[{category}] 실행 시간 상한 초과 — 남은 글은 다음 실행에서 처리")
                break
            item["body"] = fetch_body(item["url"])
            save_to_supabase(item)
            total += 1
            time.sleep(0.3)  # 학교 서버에 부담 주지 않게 간격을 둔다

    print(f"완료: 총 {total}건 확인")

if __name__ == "__main__":
    main()
