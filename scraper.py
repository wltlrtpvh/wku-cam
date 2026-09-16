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
import requests
from bs4 import BeautifulSoup

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; WKUCampusBot/1.0)"}

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
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")

    items = []
    # 이 사이트는 각 글이 <h3><a href="...">제목</a></h3> 형태로 되어 있습니다.
    # 실제 페이지에서 F12(개발자 도구)로 열어 구조가 다르면 이 부분을 조정하세요.
    for h3 in soup.select("main h3"):
        a = h3.find("a")
        if not a or not a.get("href"):
            continue
        title = a.get_text(strip=True)
        link = a["href"]
        if not title or not link.startswith("http"):
            continue

        # 날짜는 보통 글 근처에 YYYY/MM/DD 형태로 있습니다.
        date_match = None
        parent = h3.find_parent()
        if parent:
            text_near = parent.get_text(" ", strip=True)
            m = re.search(r"(20\d{2}/\d{2}/\d{2})", text_near)
            if m:
                date_match = m.group(1).replace("/", ".")

        items.append({
            "category": category,
            "title": title,
            "url": link,
            "posted_date": date_match or "",
        })
    return items


def fetch_body(url):
    """상세 페이지에서 본문 텍스트를 가져온다 (실패해도 넘어감)."""
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        content = soup.select_one("article") or soup.select_one("main")
        if content:
            text = content.get_text("\n", strip=True)
            return text[:2000]  # 너무 길면 잘라서 저장
    except Exception as e:
        print(f"본문 가져오기 실패: {url} ({e})")
    return ""


def save_to_supabase(notice):
    """Supabase REST API로 새 글을 저장 (이미 있으면 무시)."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("[건너뜀 - 환경변수 없음]", notice["title"])
        return

    endpoint = f"{SUPABASE_URL}/rest/v1/notices"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=ignore-duplicates",  # url이 중복이면 무시
    }
    res = requests.post(endpoint, headers=headers, json=notice, timeout=15)
    if res.status_code in (200, 201, 409):
        print("저장됨:", notice["title"])
    else:
        print("저장 실패:", res.status_code, res.text[:200])


def main():
    total = 0
    for category, url in BOARDS.items():
        try:
            items = fetch_list(category, url)
        except Exception as e:
            print(f"[{category}] 목록 가져오기 실패: {e}")
            continue

        for item in items[:10]:  # 최근 10개만 확인 (매번 전체를 다 볼 필요 없음)
            item["body"] = fetch_body(item["url"])
            save_to_supabase(item)
            total += 1

    print(f"완료: 총 {total}건 확인")


if __name__ == "__main__":
    main()
