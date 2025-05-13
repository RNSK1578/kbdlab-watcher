import time
import threading
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, redirect
import schedule
import datetime

app = Flask(__name__)

config = {
    "username": "",
    "password": "",
    "webhook_url": "",
}

status = {
    "running": False,
    "last_check": None,
    "next_relogin": None,
    "posts": [],
}

session = requests.Session()
last_post_ids = set()

LOGIN_URL = "https://kbdlab.co.kr/index.php?act=procMemberLogin"
BOARD_URL = "https://kbdlab.co.kr/index.php?mid=board_wUWl20"

def login():
    global session
    session = requests.Session()
    login_data = {
        "user_id": config["username"],
        "password": config["password"],
        "keep_signed": "1",
        "act": "procMemberLogin",
    }
    headers = {
        "Referer": BOARD_URL,
        "User-Agent": "Mozilla/5.0",
    }
    response = session.post(LOGIN_URL, data=login_data, headers=headers)
    if "alert" in response.text or "action_login" in response.url:
        print("❌ 로그인 실패!")
        return False
    print("✅ 로그인 성공!")
    return True

def fetch_latest_posts():
    global last_post_ids

    headers = {"User-Agent": "Mozilla/5.0"}
    response = session.get(BOARD_URL, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    rows = soup.select("table.bd_lst tbody tr")
    new_posts = []

    for row in rows:
        if "notice" in row.get("class", []):
            continue

        link_tag = row.select_one("td.title a")
        if not link_tag:
            continue

        title = link_tag.get_text(strip=True)
        url = link_tag["href"]
        full_url = url if url.startswith("http") else "https://kbdlab.co.kr" + url
        post_id = full_url.split("document_srl=")[-1]

        if post_id not in last_post_ids:
            last_post_ids.add(post_id)
            new_posts.append({"title": title, "url": full_url})

    return new_posts

def send_to_discord(posts):
    if not config["webhook_url"]:
        return

    for post in posts:
        data = {"content": f"📌 새 글: {post['title']}\n{post['url']}"}
        try:
            requests.post(config["webhook_url"], json=data)
            print("✅ 디스코드 알림 전송:", post['title'])
        except Exception as e:
            print("❌ 디스코드 전송 실패:", e)

def check():
    status["last_check"] = int(time.time())

    if int(time.time()) > status.get("next_relogin", 0):
        if login():
            status["next_relogin"] = int(time.time()) + 1800

    posts = fetch_latest_posts()
    if posts:
        send_to_discord(posts)
        status["posts"] = posts

def run_scheduler():
    while status["running"]:
        schedule.run_pending()
        time.sleep(1)

@app.template_filter("datetimeformat")
def datetimeformat_filter(value):
    if value is None:
        return "-"
    return datetime.datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")

@app.route("/")
def index():
    return render_template("dashboard.html", status=status, config=config)

@app.route("/start")
def start():
    if not status["running"]:
        status["running"] = True
        schedule.every(1).minutes.do(check)
        threading.Thread(target=run_scheduler, daemon=True).start()
    return redirect("/")

@app.route("/stop")
def stop():
    status["running"] = False
    schedule.clear()
    return redirect("/")

@app.route("/refresh")
def refresh():
    check()
    return redirect("/")

@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        config["username"] = request.form.get("username", "")
        config["password"] = request.form.get("password", "")
        config["webhook_url"] = request.form.get("webhook_url", "")
        return redirect("/")
    return render_template("settings.html", config=config)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
