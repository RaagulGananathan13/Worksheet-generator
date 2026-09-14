"""Local entry point. Production should use HTTPS via the supplied proxy."""
import argparse
import os

import uvicorn
from app.server import create_app


def main():
    parser = argparse.ArgumentParser(description="Independent worksheet grading portal")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    application = create_app()
    print("\nWorksheet grading portal")
    print(f"Open http://{args.host}:{args.port}")
    if os.getenv("AG_BOOTSTRAP_TOKEN"):
        print("First-teacher setup uses your configured AG_BOOTSTRAP_TOKEN (not printed in logs).")
    else:
        print("First-teacher setup token (keep private):", application.state.bootstrap_token)
    print("The token only works before the first teacher exists.")
    if os.getenv("AG_SECURE_COOKIES") != "1":
        print("Local HTTP mode. Use HTTPS and AG_SECURE_COOKIES=1 when hosting.\n")
    uvicorn.run(application, host=args.host, port=args.port, workers=1)


if __name__ == "__main__":
    main()
