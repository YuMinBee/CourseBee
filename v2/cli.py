from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the CourseBee v2 API and demo UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    import uvicorn

    uvicorn.run("v2.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
