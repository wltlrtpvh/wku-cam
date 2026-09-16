/*
  wku-campus.html 안의 정적 NOTICES 배열을 이 코드로 교체하면
  Supabase에 저장된 실제 데이터를 불러와서 보여줄 수 있어요.

  1. 아래 SUPABASE_URL, SUPABASE_ANON_KEY 값을 본인 프로젝트 값으로 바꾸세요.
     (Supabase 대시보드 > Project Settings > API 에서 확인)
  2. anon(공개) key만 쓰세요. service_role key는 절대 웹페이지에 넣지 마세요.
  3. 기존 "const NOTICES = [...]" 부분을 지우고, 이 코드로 대체하세요.
*/

const SUPABASE_URL = "https://YOUR_PROJECT.supabase.co";
const SUPABASE_ANON_KEY = "YOUR_ANON_KEY";

let NOTICES = []; // 처음엔 비어있다가, 아래에서 채워짐

async function loadNotices() {
  try {
    const res = await fetch(
      `${SUPABASE_URL}/rest/v1/notices?select=*&order=posted_date.desc&limit=50`,
      {
        headers: {
          apikey: SUPABASE_ANON_KEY,
          Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
        },
      }
    );
    const data = await res.json();

    NOTICES = data.map((row) => ({
      cat: row.category,
      title: row.title,
      date: row.posted_date,
      ddays: null, // 마감일 계산 로직은 필요하면 나중에 추가
      body: row.body,
      url: row.url,
    }));
  } catch (e) {
    console.error("공지 불러오기 실패:", e);
    NOTICES = [];
  }

  renderChips();
  renderNotices();
}

// 페이지 시작할 때 정적 배열 대신 이 함수를 호출하세요:
// loadNotices();  ← init 부분의 renderNotices() 호출을 이걸로 교체
