from flask import Flask
import threading

from bot import start_bot

app = Flask(__name__)

@app.route("/")
def home():
    return "NuvixMarket x SellAuth bot ✅"

def run_discord():
    start_bot()

if __name__ == "__main__":
    t = threading.Thread(target=run_discord)
    t.start()
    app.run(host="0.0.0.0", port=10000)
