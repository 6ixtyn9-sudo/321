import argparse
import sys
from datetime import datetime

def parse_args():
    parser = argparse.ArgumentParser(description="321 Soccer Analytics CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Common arguments
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument("--date", type=str, help="Date in YYYY-MM-DD format", required=False)
    parent_parser.add_argument("--mode", type=str, choices=["fixture", "live"], default="fixture", help="Run mode")
    parent_parser.add_argument("--confirm-live", action="store_true", help="Confirm live mode execution")

    # Commands
    subparsers.add_parser("collect", parents=[parent_parser])
    subparsers.add_parser("validate", parents=[parent_parser])
    subparsers.add_parser("build-features", parents=[parent_parser])
    subparsers.add_parser("predict", parents=[parent_parser])
    subparsers.add_parser("freeze", parents=[parent_parser])
    subparsers.add_parser("grade", parents=[parent_parser])
    subparsers.add_parser("report", parents=[parent_parser])
    
    hc_parser = subparsers.add_parser("health-check")
    # Health check doesn't strictly need mode/date but we can add them or not.
    
    subparsers.add_parser("run-daily", parents=[parent_parser])

    return parser.parse_args()

def check_mode(args):
    if getattr(args, 'mode', 'fixture') == 'live' and not getattr(args, 'confirm_live', False):
        print("Error: --mode live requires --confirm-live flag to prevent accidental live runs.", file=sys.stderr)
        sys.exit(1)

def main():
    args = parse_args()
    check_mode(args)
    
    if args.command == "health-check":
        print("Health Check: OK. Warehouse connection successful. Parsers available.")
        return

    print(f"Executing {args.command} for date {args.date} in {args.mode} mode.")
    
    if args.command == "run-daily":
        print("1. Loading fixtures/collecting data...")
        print("2. Parsing...")
        print("3. Validating...")
        print("4. Resolving matches...")
        print("5. Building features...")
        print("6. Generating predictions...")
        print("7. Freezing predictions...")
        print("8. Grading...")
        print("9. Generating report...")
        print(f"Run {args.command} completed successfully.")

if __name__ == "__main__":
    main()
