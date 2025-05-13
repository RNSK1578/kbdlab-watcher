# main.py
from flask import Flask, render_template, redirect, url_for, request, flash
import threading, time, hashlib, requests, json, os
from bs4 import BeautifulSoup
from datetime import datetime

CONFIG_FILE = 'config.json'

# 설정 파일 초기화 및 로드
if not os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump({'username': '', 'password': '', 'webhook_url': ''}, f, ensure_ascii=False, indent=2)
with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
    config = json.load(f)

app = Flask(__name__)
app.secret_key = 'secret-key'

# URL 설정
LOGIN_URL = "https://kbdlab.co.kr/index.php?mid=board_wUWl20&act=dispOknameLoginForm"
LOGIN_PROC_URL = "https://kbdlab.co.kr/index.php?act=procMemberLogin"
BOARD_URL = "https://kbdlab.co.kr/index.php?mid=board_wUWl20"

session = requests.Session()
latest_hash = None
status = {'running': False, 'last_check': None, 'next_relogin': None, 'posts': []}

# Jinja 필터: timestamp -> 포맷
@app.template_filter('datetimeformat')
def datetimeformat(timestamp):
    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')

# 로그인 함수
def 로그인():
    data = {
        'user_id': config['username'],
        'password': config['password'],
        'success_return_url': '/index.php?mid=board_wUWl20',
        'act': 'procMemberLogin'
    }
    headers = {'Referer': LOGIN_URL, 'User-Agent': 'Mozilla/5.0'}
    session.get(LOGIN_URL, headers=headers)
    resp = session.post(LOGIN_PROC_URL, data=data, headers=headers)
    if resp.status_code == 200 and 'dispMemberLogout' in resp.text:
        status['next_relogin'] = time.time() + 1800
        flash('✅ 로그인에 성공했습니다.', 'success')
    else:
        flash('❌ 로그인에 실패했습니다. 설정을 확인해주세요.', 'error')

# 스크래핑 함수
def 스크랩작업():
    global latest_hash
    while status['running']:
        if status['next_relogin'] and time.time() >= status['next_relogin']:
            로그인()
        resp = session.get(BOARD_URL, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(resp.text, 'html.parser')
        rows = soup.select('table.bd_lst.bd_tb_lst.bd_tb tbody tr')
        posts = []
        for row in rows:
            if 'notice' in row.get('class', []): continue
            a = row.select_one('td.title a')
            if not a: continue
            title, href = a.get_text(strip=True), a['href']
            url = href if href.startswith('http') else 'https://kbdlab.co.kr' + href
            posts.append({'title': title, 'url': url})
        status['posts'] = posts[:5]
        status['last_check'] = time.time()
        if posts and config['webhook_url']:
            h = hashlib.sha256(posts[0]['url'].encode()).hexdigest()
            if h != latest_hash:
                latest_hash = h
                payload = {'content': f"🆕 새 글 알림!\n제목: **{posts[0]['title']}**\n링크: {posts[0]['url']}"}
                requests.post(config['webhook_url'], json=payload)
        time.sleep(60)

# 메인 화면
@app.route('/')
def 메인화면():
    return render_template('dashboard.html', status=status, config=config)

# 시작 버튼
@app.route('/시작')
def 시작하기():
    if not all([config['username'], config['password'], config['webhook_url']]):
        flash('설정에서 모든 항목을 입력해주세요.', 'error')
    else:
        로그인()
        status['running'] = True
        threading.Thread(target=스크랩작업, daemon=True).start()
    return redirect(url_for('메인화면'))

# 중지 버튼
@app.route('/중지')
def 중지하기():
    status['running'] = False
    flash('스크래핑이 중지되었습니다.', 'success')
    return redirect(url_for('메인화면'))

# 새로고침 버튼
@app.route('/새로고침')
def 새로고침하기():
    status['last_check'] = None
    flash('목록이 새로고침되었습니다.', 'success')
    return redirect(url_for('메인화면'))

# 설정 페이지
@app.route('/설정', methods=['GET', 'POST'])
def 설정():
    if request.method == 'POST':
        config['username'] = request.form['username']
        config['password'] = request.form['password']
        config['webhook_url'] = request.form['webhook_url']
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        flash('✅ 설정이 저장되었습니다.', 'success')
        return redirect(url_for('메인화면'))
    return render_template('settings.html', config=config)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)

# templates/dashboard.html
"""
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8"/>
  <title>게시판 모니터 대시보드</title>
  <style>
    body{background:#1e1e2f;color:#e0e0e0;font-family:sans-serif}
    .container{width:90%;margin:2rem auto}
    .card{background:#2a2a3f;padding:1rem;border-radius:8px;margin-bottom:1rem}
    .btn{display:inline-block;padding:.5rem 1rem;margin:.2rem;background:#3a3aff;color:#fff;text-decoration:none;border-radius:4px}
    .btn.red{background:#ff4a4a}
    table{width:100%;border-collapse:collapse}
    th,td{padding:.5rem;border-bottom:1px solid #444}
    th{background:#30304f}
    .alert{padding:.5rem;margin-bottom:1rem;border-radius:4px}.error{background:#f44336}.success{background:#4caf50}
  </style>
<...
