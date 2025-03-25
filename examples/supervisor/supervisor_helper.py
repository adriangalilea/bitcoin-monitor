#!/usr/bin/env python3
"""
Helper utilities for managing supervisord with the bitcoin-monitor project.
"""

import argparse
import subprocess
import sys
from pathlib import Path


def get_default_conf_path():
    """Find the supervisord.conf file"""
    # Check if we're in the project root
    supervisor_dir = Path("examples/supervisor")
    if supervisor_dir.exists():
        conf_path = supervisor_dir / "supervisord.conf"
        if conf_path.exists():
            return str(conf_path.absolute())

    # Check if we're in the examples/supervisor directory
    local_conf = Path("supervisord.conf")
    if local_conf.exists():
        return str(local_conf.absolute())

    # Check one level up
    parent_conf = Path("..") / "supervisor" / "supervisord.conf"
    if parent_conf.exists():
        return str(parent_conf.absolute())

    return None


def supervisor_cmd(cmd, conf_path=None, follow=False):
    """Run a supervisorctl command"""
    if not conf_path:
        conf_path = get_default_conf_path()
        if not conf_path:
            print("Error: Could not find supervisord.conf")
            print("Please specify with --conf or run from project root")
            sys.exit(1)

    # Build the command
    base_cmd = ["supervisorctl", "-c", conf_path]

    if cmd == "tail" and follow:
        base_cmd.extend(["tail", "-f", "bitcoin-monitor"])
    elif cmd == "tail":
        base_cmd.extend(["tail", "bitcoin-monitor"])
    elif cmd == "status":
        base_cmd.append("status")
    else:
        base_cmd.extend([cmd, "bitcoin-monitor"])

    try:
        subprocess.run(base_cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running supervisorctl command: {e}")
        sys.exit(1)


def status():
    """Check status of monitored processes"""
    parser = argparse.ArgumentParser(description="Check status of Bitcoin monitor")
    parser.add_argument("--conf", help="Path to supervisord.conf")
    args = parser.parse_args()

    supervisor_cmd("status", args.conf)


def start():
    """Start the Bitcoin monitor"""
    parser = argparse.ArgumentParser(description="Start Bitcoin monitor")
    parser.add_argument("--conf", help="Path to supervisord.conf")
    args = parser.parse_args()

    supervisor_cmd("start", args.conf)


def stop():
    """Stop the Bitcoin monitor"""
    parser = argparse.ArgumentParser(description="Stop Bitcoin monitor")
    parser.add_argument("--conf", help="Path to supervisord.conf")
    args = parser.parse_args()

    supervisor_cmd("stop", args.conf)


def logs():
    """View Bitcoin monitor logs"""
    parser = argparse.ArgumentParser(description="View Bitcoin monitor logs")
    parser.add_argument("--conf", help="Path to supervisord.conf")
    parser.add_argument("-f", "--follow", action="store_true", help="Follow log output")
    args = parser.parse_args()

    supervisor_cmd("tail", args.conf, args.follow)


def main():
    """Main entry point for the bitcoin-supervisor command"""
    parser = argparse.ArgumentParser(description="Bitcoin Monitor Supervisor Helper")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Status command
    status_parser = subparsers.add_parser("status", help="Check status")
    status_parser.add_argument("--conf", help="Path to supervisord.conf")

    # Start command
    start_parser = subparsers.add_parser("start", help="Start monitor")
    start_parser.add_argument("--conf", help="Path to supervisord.conf")

    # Stop command
    stop_parser = subparsers.add_parser("stop", help="Stop monitor")
    stop_parser.add_argument("--conf", help="Path to supervisord.conf")

    # Logs command
    logs_parser = subparsers.add_parser("logs", help="View logs")
    logs_parser.add_argument("--conf", help="Path to supervisord.conf")
    logs_parser.add_argument(
        "-f", "--follow", action="store_true", help="Follow log output"
    )

    args = parser.parse_args()

    if args.command == "status":
        supervisor_cmd("status", args.conf)
    elif args.command == "start":
        supervisor_cmd("start", args.conf)
    elif args.command == "stop":
        supervisor_cmd("stop", args.conf)
    elif args.command == "logs":
        supervisor_cmd("tail", args.conf, args.follow)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
