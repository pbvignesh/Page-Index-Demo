"""Terminal entry point.

  python cli.py ingest AAPL 10-K
  python cli.py ask 1 "How has operating margin trended?"
  python cli.py build-sandbox
"""
import json
import sys

from app.ingest import ingest as ingest_filing
from app.agent import answer
from app.agent import sandbox


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return

    command = args[0]
    if command == "ingest":
        ticker = args[1]
        form = args[2] if len(args) > 2 else "10-K"
        print("ingested filing id:", ingest_filing(ticker, form))
    elif command == "ask":
        filing_id = int(args[1])
        question = " ".join(args[2:])
        print(json.dumps(answer(filing_id, question), indent=2))
    elif command == "build-sandbox":
        print(sandbox.build_image())
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
