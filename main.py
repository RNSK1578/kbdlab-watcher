import os
import time
import threading
import hashlib
import requests
import json
from bs4 import BeautifulSoup
from flask import Flask, request, render_template, redirect, url_for, flash
from datetime import datetime

# ── 설정 파일 초기화 및 로드 ───────────────────────────
CONFIG_FILE = 'config.json'
if not os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump({'username':'', 'password':'', 'webhook_url':''}, f, ensure_ascii=False, indent=2)
with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
    config = json.load(f)

# ── Flask 앱 설정 ──────────────────────────────────
app = Flask(__name__)
app.secret_key = os.urandom(24)

# ── Jinja 필터 등록: timestamp → 한글 날짜 형식 ──────────
@app.template_filter('datetimeformat')
def _datetimeformat(ts):
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S') if ts else ''

# ── URL 및 헤더 정의 ───────────────────────────────
LOGIN_FORM_URL = "https://kbdlab.co.kr/index.php?mid=board_wUWl20&act=dispOknameLoginForm"
LOGIN_PROC_URL = "https://kbdlab.co.kr/index.php?act=procMemberLogin"
BOARD_URL      = "https://kbdlab.co.kr/index.php?mid=board_wUWl20&page=1&sort_index=regdate&order_type=desc"
HEADERS        = {'User-Agent':'Mozilla/5.0'}

# ── 전역 상태 변수 ─────────────────────────────────
session = requests.Session()
latest_hash = None
status = {
    'running': False,
    'last_check': None,
    'next_relogin': None,
    'posts': []
}

# ── 로그인 함수 ────────────────────────────────────
def do_login():
    data = {
        'user_id':   config['username'],
        'password':  config['password'],
        'keep_signed': 1,
        'act':       'procMemberLogin',
        'success_return_url': '/index.php?mid=board_wUWl20'
    }
    # 로그인 페이지 먼저 GET 해서 쿠키 수집
    session.get(LOGIN_FORM_URL, headers=HEADERS)
    r = session.post(LOGIN_PROC_URL, data=data, headers=HEADERS)
    if r.status_code == 200 and 'dispMemberLogout' in r.text:
        status['next_relogin'] = time.time() + 1800  # 30분 후 재로그인
        print("✅ 로그인 성공")
    else:
        print("❌ 로그인 실패")

# ── 크롤링 루프 ────────────────────────────────────
def crawl_loop():
    global latest_hash
    status['running'] = True
    while status['running']:
        try:
            # 자동 재로그인 체크
            if status['next_relogin'] and time.time() >= status['next_relogin']:
                do_login()

            # 게시판 페이지 요청
            r = session.get(BOARD_URL, headers=HEADERS)
            soup = BeautifulSoup(r.text, 'html.parser')

            # 정확한 테이블 찾고 tbody 안의 tr들만
            table = soup.find('table', class_='bd_lst bd_tb_lst bd_tb')
            if not table:
                print("⚠️ 게시판 테이블을 찾을 수 없습니다.")
                rows = []
            else:
                tbody = table.find('tbody')
                rows = tbody.find_all('tr', recursive=False) if tbody else []

            print(f"[디버그] 읽어온 tr 개수: {len(rows)}")

            posts = []
            for row in rows:
                # 공지사항 스킵
                if 'notice' in (row.get('class') or []):
                    continue
                a = row.select_one('td.title a')
                if not a:
                    continue
                title = a.get_text(strip=True)
                href  = a['href']
                url   = href if href.startswith('http') else 'https://kbdlab.co.kr' + href
                posts.append({'title': title, 'url': url})

            status['posts'] = posts[:5]
            status['last_check'] = time.time()

            # 새 글 디스코드 알림
            if posts and config['webhook_url']:
                h = hashlib.sha256(posts[0]['url'].encode()).hexdigest()
                if h != latest_hash:
                    latest_hash = h
                    payload = {
                        'content': f"🆕 새 글 알림!\n제목: **{posts[0]['title']}**\n링크: {posts[0]['url']}"
                    }
                    requests.post(config['webhook_url'], json=payload)
                    print("📢 알림 전송:", posts[0]['title'])

        except Exception as e:
            print("⚠️ 크롤링 오류:", e)

        time.sleep(60)

    print("🔒 크롤링 중지")

# ── 라우트 정의 ────────────────────────────────────
@app.route('/')
def index():
    return render_template('dashboard.html', status=status)

@app.route('/settings', methods=['GET','POST'])
def settings():
    if request.method == 'POST':
        config['username']    = request.form['username']
        config['password']    = request.form['password']
        config['webhook_url'] = request.form['webhook_url']
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        flash('✅ 설정 저장 완료', 'success')
        return redirect(url_for('index'))
    return render_template('settings.html', config=config)

@app.route('/start')
def start():
    if not status['running']:
        do_login()
        threading.Thread(target=crawl_loop, daemon=True).start()
    return redirect(url_for('index'))

@app.route('/stop')
def stop():
    status['running'] = False
    return redirect(url_for('index'))

@app.route('/refresh')
def refresh():
    status['last_check'] = None
    return redirect(url_for('index'))

# ── 앱 실행 ────────────────────────────────────────
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '3000')))
