"""``wq serve``: run the Web UI's server on 127.0.0.1 and open it in the browser."""

import argparse
import sys
import webbrowser

import uvicorn

from worqueue.cli import clock
from worqueue.cli.output import add_json_option, print_json
from worqueue.store.paths import data_dir
from worqueue.web.app import create_app

HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def register(subparsers: argparse._SubParsersAction) -> None:
    """Add ``wq serve`` to the subcommands.

    Parameters
    ----------
    subparsers : argparse._SubParsersAction
        The subcommands of ``wq``.
    """
    parser = subparsers.add_parser(
        "serve", help="Web UI のサーバーを立てる", description="Web UI のサーバーを 127.0.0.1 に立てる"
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT, metavar="<番号>", help=f"待ち受けるポート。既定は {DEFAULT_PORT}"
    )
    parser.add_argument("--no-browser", action="store_true", help="ブラウザを開かない")
    add_json_option(parser)
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> None:
    """Carry out ``wq serve``: print the URL, open the browser, and serve until Ctrl+C.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed arguments.
    """
    url = f"http://{HOST}:{args.port}/"
    app = create_app(data_dir(), lambda: clock.now())
    if args.json:
        print_json({"url": url})
    else:
        print(f"Worqueue: {url} （Ctrl+C で止める）")
    # Flush before serving blocks, so a reader of a pipe gets the URL now.
    sys.stdout.flush()
    if not args.no_browser:
        webbrowser.open(url)
    uvicorn.run(app, host=HOST, port=args.port)
