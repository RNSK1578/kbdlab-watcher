# main.py
from flask import Flask, render_template, redirect, url_for, request
import threading, time, hashlib, requests, json, os
from bs4 import BeautifulSoup
from datetime import datetime

# 설정 파일
CONFIG_FILE = 'config.json'
if not os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump({'username':'','password':'','webhook_url':''}, f, ensure_ascii=False, indent=2)
with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
    config = json.load(f)

# Flask 앱
app = Flask(__name__)
app.secret_key = os.urandom(24)

# URL 정의
LOGIN_FORM_URL = "https://kbdlab.co.kr/index.php?mid=board_wUWl20&act=dispOknameLoginForm"
LOGIN_PROC_URL = "https://kbdlab.co.kr/index.php?act=procMemberLogin"
BOARD_URL      = "https://kbdlab.co.kr/index.php?mid=board_wUWl20&order_type=desc"

# 세션 및 상태
session = requests.Session()
latest_hash = None
status = {'running':False, 'last_check':None, 'next_relogin':None, 'posts':[]}

# 날짜 포맷 필터
@app.template_filter('datetimeformat')
def datetimeformat(ts):
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S') if ts else ''

# 로그인 함수
def do_login():
    data = {'user_id':config['username'], 'password':config['password'], 'act':'procMemberLogin', 'success_return_url':'/index.php?mid=board_wUWl20'}
    headers={'Referer':LOGIN_FORM_URL, 'User-Agent':'Mozilla/5.0'}
    session.get(LOGIN_FORM_URL, headers=headers)
    r = session.post(LOGIN_PROC_URL, data=data, headers=headers)
    if r.status_code==200 and 'dispMemberLogout' in r.text:
        status['next_relogin']=time.time()+1800
        print('로그인 성공')
    else:
        print('로그인 실패')

# 크롤링 작업
def crawl_loop():
    global latest_hash
    status['running'] = True
    while status['running']:
        try:
            # 재로그인
            if status['next_relogin'] and time.time()>=status['next_relogin']:
                do_login()
            # 게시판 요청
            resp = session.get(BOARD_URL, headers={'User-Agent':'Mozilla/5.0'})
            soup = BeautifulSoup(resp.text, 'html.parser')
            rows = soup.select('table.bd_lst tbody tr')
            posts=[]
            for row in rows:
                if 'notice' in row.get('class',[]): continue
                a = row.select_one('td.title a')
                if not a: continue
                title=a.get_text(strip=True); href=a['href']
                url = href if href.startswith('http') else 'https://kbdlab.co.kr'+href
                posts.append({'title':title,'url':url})
            status['posts']=posts[:5]
            status['last_check']=time.time()
            # 디스코드 알림
            if posts and config['webhook_url']:
                h=hashlib.sha256(posts[0]['url'].encode()).hexdigest()
                if h!=latest_hash:
                    latest_hash=h
                    payload={'content':f"🆕 새 글: {posts[0]['title']}\n{posts[0]['url']}"}
                    requests.post(config['webhook_url'], json=payload)
                    print('알림 전송')
        except Exception as e:
            print('크롤링 오류', e)
        time.sleep(60)
    print('크롤링 중지')

# 라우트
@app.route('/')
def index():
    return render_template('dashboard.html', status=status)

@app.route('/설정', methods=['GET','POST'])
def settings():
    if request.method=='POST':
        config['username']=request.form['username']
        config['password']=request.form['password']
        config['webhook_url']=request.form['webhook_url']
        with open(CONFIG_FILE,'w',encoding='utf-8') as f:
            json.dump(config,f,ensure_ascii=False,indent=2)
        return redirect(url_for('index'))
    return render_template('settings.html', config=config)

@app.route('/시작')
def start():
    if not status['running']:
        do_login()
        threading.Thread(target=crawl_loop,daemon=True).start()
    return redirect(url_for('index'))

@app.route('/중지')
def stop():
    status['running']=False
    return redirect(url_for('index'))

@app.route('/새로고침')
def refresh():
    status['last_check']=None
    return redirect(url_for('index'))

if __name__=='__main__':
    port=int(os.environ.get('PORT',3000))
    app.run(host='0.0.0.0',port=port)

# requirements.txt
"""
flask
requests
beautifulsoup4
schedule
"""

# templates/dashboard.html
"""
<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"><title>대시보드</title>
<style>body{background:#1e1e2f;color:#e0e0e0} .container{padding:2rem}</style></head>
<body><div class="container">
<h1>키보드LAB 장터 모니터</h1>
<div>
  <p>상태: {% if status.running %}<strong>실행 중</strong>{% else %}<strong>중지됨</strong>{% endif %}</p>
  <p>마지막 확인: {% if status.last_check %}{{ status.last_check|int|datetimeformat }}{% else %}아직 없음{% endif %}</p>
</div>
<div>
  <h2>최신 글</h2>
  <ul>
  {% for post in status.posts %}
    <li><a href="{{ post.url }}" target="_blank" style="color:#4facff">{{ post.title }}</a></li>
  {% else %}
    <li>게시물이 없습니다</li>
  {% endfor %}
  </ul>
</div>
<div>
  <a href="/시작">시작</a> |
  <a href="/중지">중지</a> |
  <a href="/새로고침">새로고침</a> |
  <a href="/설정">설정</a>
</div>
</div></body>
</html>
"""

# templates/settings.html
"""
<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"><title>설정</title>
<style>body{background:#1e1e2f;color:#e0e0e0} .container{padding:2rem}</style></head>
<body><div class="container">
<h1>설정</h1>
<form method="post">
  <label>아이디:<input type="text" name="username" value="{{ config.username }}" required></label><br>
  <label>비밀번호:<input type="password" name="password" value="{{ config.password }}" required></label><br>
  <label>웹훅 URL:<input type="text" name="webhook_url" value="{{ config.webhook_url }}" required></label><br>
  <button type="submit">저장하기</button> <a href="/">뒤로가기</a>
</form>
</div></body>
</html>
"""
