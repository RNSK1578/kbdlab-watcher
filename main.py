# main.py
import time
import threading
import hashlib
import requests
import json
import xml.etree.ElementTree as ET
from flask import Flask, request, render_template, redirect, url_for
from datetime import datetime

# 설정 load/초기화
CONFIG_FILE = 'config.json'
try:
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config = json.load(f)
except FileNotFoundError:
    config = {'webhook_url': ''}
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

app = Flask(__name__)
app.secret_key = 'secret'

RSS_URL = "https://kbdlab.co.kr/index.php?module=rss&act=rss&mid=board_wUWl20"
latest_hash = None
status = {'running': False, 'last_check': None, 'posts': []}

def fetch_rss():
    global latest_hash
    try:
        resp = requests.get(RSS_URL, headers={'User-Agent':'Mozilla/5.0'})
        root = ET.fromstring(resp.content)
        # <item>... 구조
        items = root.findall('.//item')
        posts = []
        for item in items:
            title = item.findtext('title', '').strip()
            link  = item.findtext('link', '').strip()
            # 공지 제목에 “전파법” 또는 “키보드랩 장터 준수 사항” 등 포함된 경우 제외
            if '전파법' in title or '준수 사항' in title:
                continue
            posts.append({'title': title, 'url': link})
        status['posts'] = posts[:5]
        status['last_check'] = time.time()

        # 디스코드 알림
        if posts and config.get('webhook_url'):
            h = hashlib.sha256(posts[0]['url'].encode()).hexdigest()
            if h != latest_hash:
                latest_hash = h
                payload = {'content': f"🆕 새 글 알림!\n제목: **{posts[0]['title']}**\n링크: {posts[0]['url']}"}
                requests.post(config['webhook_url'], json=payload)
    except Exception as e:
        print("⚠️ RSS 파싱 오류:", e)

def monitor_loop():
    status['running'] = True
    while status['running']:
        fetch_rss()
        time.sleep(60)
    print("🔒 모니터링 중지")

@app.route('/')
def index():
    return render_template('dashboard.html', status=status)

@app.route('/settings', methods=['GET','POST'])
def settings():
    if request.method == 'POST':
        config['webhook_url'] = request.form['webhook_url']
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return redirect(url_for('index'))
    return render_template('settings.html', config=config)

@app.route('/start')
def start():
    if not status['running']:
        threading.Thread(target=monitor_loop, daemon=True).start()
    return redirect(url_for('index'))

@app.route('/stop')
def stop():
    status['running'] = False
    return redirect(url_for('index'))

@app.route('/refresh')
def refresh():
    fetch_rss()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)
