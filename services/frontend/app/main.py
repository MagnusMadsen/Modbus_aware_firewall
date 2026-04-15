from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    return "<h1>Modbus Aware Sensor</h1><p>Frontend is running.</p>"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)