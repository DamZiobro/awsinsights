#! /usr/bin/env python
# -*- coding: utf-8 -*-
# vim:fenc=utf-8
#
# Copyright © 2021 Damian Ziobro - XMementoIT Limited <damian@xmementoit.com>
#
# Distributed under terms of the MIT license.


import fnmatch
import os
import boto3
import datetime
import time
import logging

logging.basicConfig(level=logging.INFO)


def resolve_glob_log_groups(logs_client, log_groups):
    """Resolve glob patterns (e.g. /aws/lambda/oreo_*) to actual log group names.

    Uses CloudWatch describe_log_groups with the prefix before the first glob
    character, then filters results using fnmatch for full glob support.

    Log groups without glob characters are passed through unchanged.
    """
    resolved = []
    for group in log_groups:
        if "*" not in group and "?" not in group:
            resolved.append(group)
            continue

        # Extract prefix up to the first glob character for API filtering
        prefix = group.split("*")[0].split("?")[0]

        logging.info(
            f"Resolving glob pattern '{group}' "
            f"(prefix: '{prefix}')..."
        )

        # Paginate through all matching log groups
        paginator = logs_client.get_paginator("describe_log_groups")
        matched = []
        for page in paginator.paginate(logGroupNamePrefix=prefix):
            for lg in page.get("logGroups", []):
                name = lg["logGroupName"]
                if fnmatch.fnmatch(name, group):
                    matched.append(name)

        if matched:
            logging.info(
                f"  Pattern '{group}' matched {len(matched)} log groups: "
                f"{matched}"
            )
            resolved.extend(matched)
        else:
            logging.warning(
                f"  Pattern '{group}' matched 0 log groups. Skipping."
            )

    return resolved


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


def _is_recent_event_reached(recent_log_event, log_event):
    if recent_log_event is None:
        return True

    log_fields = {field["field"]: field["value"] for field in log_event}
    recent_log_fields = {field["field"]: field["value"] for field in recent_log_event}

    for field in log_fields.keys():
        if log_fields.get(field) != recent_log_fields.get(field):
            return False

    return True


def _utc_to_local(utc_datetime):
    now_timestamp = time.time()
    offset = datetime.datetime.fromtimestamp(
        now_timestamp
    ) - datetime.datetime.utcfromtimestamp(now_timestamp)
    return utc_datetime + offset


def get_logs(
    start_time,
    end_time,
    query,
    appname=None,
    log_groups=None,
    wait_sec=10,
    is_tail=False,
):
    region = (
        os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "us-east-1"
    )
    insights = boto3.client("logs", region_name=region)

    filename = "/tmp/awsinsights.log"
    if appname:
        filename = f"/tmp/{appname}.log"

    if not log_groups:
        logging.error(bcolors.FAIL + "0 log groups configured" + bcolors.ENDC)
        return

    # Resolve glob patterns (e.g. /aws/lambda/oreo_*) to actual log group names
    log_groups = resolve_glob_log_groups(insights, log_groups)

    if not log_groups:
        logging.error(
            bcolors.FAIL + "0 log groups found after resolving glob patterns"
            + bcolors.ENDC
        )
        return

    logging.info(
        bcolors.OKBLUE + f"Querying {len(log_groups)} log groups: "
        f"{log_groups}" + bcolors.ENDC
    )

    log_limit = 10000
    results = {"results": []}
    recent_timestamp = None
    recent_log_event = None

    with open(filename, "w+") as output_file:
        while len(results["results"]) in (0, log_limit) or is_tail:
            if recent_timestamp:
                start_time = datetime.datetime.strptime(
                    str(recent_timestamp), "%Y-%m-%d %H:%M:%S.%f"
                )
                start_time = _utc_to_local(start_time)

            if is_tail:
                end_time = datetime.datetime.now()

            logging.debug(f"start_time: {start_time}")
            logging.debug(f"end_time: {end_time}")

            async_resp = insights.start_query(
                logGroupNames=log_groups,
                startTime=int(start_time.timestamp()),
                endTime=int(end_time.timestamp()),
                queryString=query,
                limit=log_limit,
            )

            status = "Running"
            while status not in ("Complete", "Failed", "Cancelled", "Timeout"):
                if not is_tail:
                    logging.info(
                        bcolors.HEADER + f"waiting {wait_sec} seconds for "
                        f"query results - status: {status}" + bcolors.ENDC
                    )
                time.sleep(wait_sec)
                results = insights.get_query_results(queryId=async_resp["queryId"])
                status = results["status"]

            print_log_event = False
            for log_event in results["results"]:
                log_fields = {field["field"]: field["value"] for field in log_event}

                # Build log line with explicit field ordering:
                # @timestamp first, then @logGroup/@logStream if present, then @message
                ordered_parts = []
                if "@timestamp" in log_fields:
                    ordered_parts.append(log_fields["@timestamp"])
                if "@log" in log_fields:
                    # @log format: "accountId:logGroupName" — extract just the log group
                    log_group_name = log_fields["@log"].split(":", 1)[-1] if ":" in log_fields["@log"] else log_fields["@log"]
                    ordered_parts.append(f"[{log_group_name}]")
                elif "@logGroup" in log_fields:
                    ordered_parts.append(f"[{log_fields['@logGroup']}]")
                if "@logStream" in log_fields:
                    ordered_parts.append(f"[{log_fields['@logStream']}]")
                if "@message" in log_fields:
                    ordered_parts.append(log_fields["@message"])
                # Append any remaining fields (excluding known ones and @ptr)
                skip_fields = {"@timestamp", "@log", "@logGroup", "@logStream", "@message", "@ptr"}
                for field_entry in log_event:
                    if field_entry["field"] not in skip_fields:
                        ordered_parts.append(field_entry["value"])

                log_line = " ".join(ordered_parts)

                if not print_log_event:
                    print_log_event = _is_recent_event_reached(
                        recent_log_event, log_event
                    )
                else:
                    print(log_line)
                    output_file.write(log_line)

                recent_timestamp = log_fields.get("@timestamp")

            if len(results["results"]) > 0:
                recent_log_event = results["results"][-1]
            else:
                if not is_tail:
                    logging.warn(
                        bcolors.WARNING + "   => 0 logs found which "
                        "match defined filter..." + bcolors.ENDC
                    )
                    break
