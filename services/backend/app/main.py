# formål

from flask import Flask

from api import api_bp
from capture import start_capture_thread
from db import apply_schema, verify_schema
from users_bootstrap import bootstrap_default_user
from state import init_state_manager

app = Flask(__name__)
app.register_blueprint(api_bp)


if __name__ == "__main__":
    apply_schema()
    verify_schema()
    bootstrap_default_user()
    init_state_manager()
    start_capture_thread()
    app.run(host="0.0.0.0", port=8000, debug=False)


