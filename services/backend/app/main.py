from flask import Flask
from api import api_bp
from capture import start_capture_thread

app = Flask(__name__)
app.register_blueprint(api_bp)

if __name__ == "__main__":
    start_capture_thread()
    app.run(host="0.0.0.0", port=8000, debug=False)