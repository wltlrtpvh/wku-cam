name: 원광대 공지 수집

on:
  schedule:
    - cron: "0 * * * *"   # 매시 정각에 실행 (원하는 주기로 조정 가능)
  workflow_dispatch:        # GitHub 화면에서 수동 실행 버튼도 생김

jobs:
  scrape:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Python 설치
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: 필요한 패키지 설치
        run: pip install requests beautifulsoup4

      - name: 스크래퍼 실행
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
        run: python scraper.py
