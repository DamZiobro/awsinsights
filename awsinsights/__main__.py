#! /usr/bin/env python
# -*- coding: utf-8 -*-
# vim:fenc=utf-8
#
# Copyright © 2021 Damian Ziobro - XMementoIT Limited <damian@xmementoit.com>
#
# Distributed under terms of the MIT license.

import argparse
import logging
import os
import sys
import json
import traceback

from datetime import datetime, timedelta

from awsinsights import awsinsights


class bcolors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


def _get_time_delta(input_time):
    value = input_time[0:-1]
    unit = input_time[-1]

    if unit == "m":
        return timedelta(minutes=int(value))
    if unit == "h":
        return timedelta(hours=int(value))
    if unit == "d":
        return timedelta(days=int(value))
    return timedelta(minutes=60)


def _get_log_groups_of_app(appname, env):
    rcfile = os.path.expanduser("~/.awsinsights.json")

    logging.info(
        bcolors.OKCYAN + f"Checking whether app '{appname}' exists in "
        f"{rcfile}..." + bcolors.ENDC
    )

    log_groups = []
    try:
        with open(rcfile) as rc:
            apps = json.load(rc)

            log_groups = apps.get(appname)

            # resolve $ENV variable in log group names
            log_groups = [group.replace("$ENV", env) for group in log_groups]

    except Exception:
        traceback.print_exc()
        logging.error(
            bcolors.FAIL + f"app '{appname}' is not configured in "
            f"{rcfile}" + bcolors.ENDC
        )

    if log_groups:
        logging.info(
            bcolors.OKGREEN + f"app `{appname}` configured properly in {rcfile}. "
            f"Found {len(log_groups)} log groups." + bcolors.ENDC
        )

    logging.info(bcolors.OKBLUE + f"log_groups: {log_groups}" + bcolors.ENDC)

    return log_groups


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--timedelta",
        help="delta time since now when logs should be filtered "
        "ex. 120m, 3h, 2d. Default: 60m",
        default="60m",
    )
    parser.add_argument(
        "--start", help="start time of grabbing logs. Format: YYYY-MM-DD HH:MM:SS"
    )
    parser.add_argument(
        "--end", help="end time of grabbing logs. Format: YYYY-MM-DD HH:MM:SS"
    )

    parser.add_argument(
        "--filter", help="Regular expression for filtering logs", default=""
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--appname",
        help="name of the app which logs should "
        "be analysed. App names should have logs groups "
        "configured in .awsinsightsrc file. See README.md file.",
    )
    group.add_argument(
        "--log_groups",
        help='list of the log groups " \
                       "to analyse (up to 20)',
        nargs="+",
    )

    parser.add_argument(
        "--env",
        help='env name. It can replace "$ENV" phrase in log groups names. Default: dev',
        default="dev",
    )

    parser.add_argument(
        "--wait",
        help="wait time for single AWS Insights Query results in seconds. Default: 10",
        default=10,
    )

    insights_query = (
        "fields @timestamp, @message | filter @message like // | sort @timestamp"
    )
    parser.add_argument(
        "--query",
        help=f'Custom full AWS CloudWatch Insights query. " \
                        "Default: {insights_query}',
        default=insights_query,
    )
    parser.add_argument(
        "--tail",
        help='TAIL MODE. If set to "true", It will listen for live logs forever',
        dest="tail",
        action="store_true",
    )
    args = parser.parse_args()

    if args.query == insights_query:
        args.query = (
            "fields @timestamp, @message | filter @message "
            f"like /{args.filter}/ | sort @timestamp"
        )

    if args.appname:
        app_log_groups = _get_log_groups_of_app(args.appname, args.env)
        if not app_log_groups:
            sys.exit(-1)

        args.log_groups = app_log_groups

    start = None
    end = None

    if args.start and not args.end:
        start = datetime.strptime(args.start, "%Y-%m-%d %H:%M:%S")
        end = datetime.now()
    if args.start and args.end:
        start = datetime.strptime(args.start, "%Y-%m-%d %H:%M:%S")
        end = datetime.strptime(args.end, "%Y-%m-%d %H:%M:%S")
    elif args.timedelta:
        end = datetime.now()
        start = end - _get_time_delta(args.timedelta)
    else:
        logging.error("ERROR => Neither start/end pair nor timedelta is defined")
        parser.print_help()

    if args.tail:
        logging.info(
            bcolors.OKGREEN + "\n\n   LISTENING IN TAIL MODE...\n" + bcolors.ENDC
        )

    # start grabbing logs
    awsinsights.get_logs(
        start_time=start,
        end_time=end,
        query=args.query,
        appname=args.appname,
        log_groups=args.log_groups,
        wait_sec=int(args.wait),
        is_tail=args.tail,
    )


if __name__ == "__main__":
    main()
