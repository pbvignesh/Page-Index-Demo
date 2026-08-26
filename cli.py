"""Terminal entry point.

  python cli.py ingest AAPL 10-K
  python cli.py ask 1 "How has operating margin trended?"
  python cli.py build-sandbox
"""
import json
import sys

from app import ingest, agent, sandbox


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    cmd = args[0]
    if cmd == "ingest":
        ticker = args[1]
        form = args[2] if len(args) > 2 else "10-K"
        print("ingested filing id:", ingest.ingest(ticker, form))
    elif cmd == "ask":
        print(json.dumps(agent.answer(int(args[1]), " ".join(args[2:])), indent=2))
    elif cmd == "build-sandbox":
        print(sandbox.build_image())
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
