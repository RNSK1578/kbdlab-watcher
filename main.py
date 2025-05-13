from flask import Flask, render_template, redirect, url_for, request
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

LOGIN_URL = "https://kbdlab.co.kr/index.php?mid=board_wUWl20&act=dispOknameLoginForm"
LOGIN_PROC_URL = "https://kbdlab.co.kr/index.php?act=procMemberLogin"
BOARD_URL = "https://kbdlab.co.kr/index.php?mid=board_wUWl20"

session = requests.Session()
latest_hash = None
status = {'running': False, 'last_check': None, 'next_relogin': None, 'posts': []}

@app.template_filter('datetimeformat')
def datetimeformat(timestamp):
    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')

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
        print('✅ 로그인 성공')
    else:
        print('❌ 로그인 실패. 설정을 확인하세요.')

def 스크랩작업():
    global latest_hash
    print("🔁 스크래핑 시작됨.")
    status['running'] = True
    while status['running']:
        try:
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
                    print(f"📢 새 글 알림 전송됨: {posts[0]['title']}")
        except Exception as e:
            print(f"⚠️ 오류 발생: {e}")
        time.sleep(60)

@app.route('/')
def 메인화면():
    return render_template('dashboard.html', status=status, config=config)

@app.route('/설정', methods=['GET', 'POST'])
def 설정():
    if request.method == 'POST':
        config['username'] = request.form['username']
        config['password'] = request.form['password']
        config['webhook_url'] = request.form['webhook_url']
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return redirect(url_for('메인화면'))
    return render_template('settings.html', config=config)

def 자동시작():
    if all([config['username'], config['password'], config['webhook_url']]):
        로그인()
        threading.Thread(target=스크랩작업, daemon=True).start()
    else:
        print("⚠️ 설정이 누락되어 자동 시작이 중단되었습니다.")

if __name__ == '__main__':
    자동시작()
    app.run(host='0.0.0.0', port=3000)
