#! /usr/bin/env python
# -*- coding: utf-8 -*-
# vim:fenc=utf-8
#
# Copyright © 2021 Damian Ziobro - XMementoIT Limited <damian@xmementoit.com>
#
# Distributed under terms of the MIT license.


import difflib
import fnmatch
import os
import re
import sys
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
        # (empty prefix happens for patterns like "*name*" — scan all groups)
        paginator = logs_client.get_paginator("describe_log_groups")
        matched = []
        paginate_kwargs = {"logGroupNamePrefix": prefix} if prefix else {}
        for page in paginator.paginate(**paginate_kwargs):
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


def _get_region():
    return (
        os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "us-east-1"
    )


def _glue_job_run_ids(job_name, start_time, end_time, region):
    """Return run IDs of Glue job `job_name` overlapping the time window.

    Returns None if no such Glue job exists (or Glue API is unavailable),
    [] if the job exists but has no runs in the window.
    Glue writes to shared log groups (/aws-glue/jobs/...) where the log
    stream name is the run ID — the job name appears nowhere, so run IDs
    are the only way to narrow shared groups to one job.
    """
    glue = boto3.client("glue", region_name=region)
    run_ids = []
    try:
        paginator = glue.get_paginator("get_job_runs")
        for page in paginator.paginate(JobName=job_name):
            for run in page["JobRuns"]:
                started = run.get("StartedOn")
                completed = run.get("CompletedOn")
                if started and started.timestamp() > end_time.timestamp():
                    continue
                if completed and completed.timestamp() < start_time.timestamp():
                    # runs are returned newest first — everything below is older
                    return run_ids
                run_id = run.get("Id")
                if run_id:
                    run_ids.append(run_id)
    except glue.exceptions.EntityNotFoundException:
        return None
    except Exception:
        logging.debug(f"Glue lookup for '{job_name}' failed; skipping Glue")
        return None
    return run_ids


def resolve_resource_log_groups(resources, start_time, end_time):
    """Map AWS resource names (Lambda function, Glue job, etc.) to log groups.

    For each name:
      - collects all log groups whose name contains the resource name
        (covers /aws/lambda/{name}, /ecs/{name}, custom groups)
      - if a Glue job with that name has runs in the time window, adds the
        shared /aws-glue/jobs/output log group (application stdout only —
        Spark/server logs in error, logs-v2 and continuous-logging groups
        are deliberately skipped; use --log_groups to query those)

    Returns (log_groups, stream_filter) where stream_filter is a regex of
    Glue run IDs to apply on @logStream, or None.
    """
    region = _get_region()
    logs_client = boto3.client("logs", region_name=region)

    log_groups = []
    stream_ids = []

    for name in resources:
        matched = resolve_glob_log_groups(logs_client, [f"*{name}*"])
        log_groups.extend(g for g in matched if g not in log_groups)

        run_ids = _glue_job_run_ids(name, start_time, end_time, region)
        if run_ids == []:
            logging.warning(
                bcolors.WARNING + f"Glue job '{name}' exists but has 0 runs "
                f"in the time window — widen it with --timedelta/--start"
                + bcolors.ENDC
            )
        if run_ids:
            logging.info(
                bcolors.OKGREEN + f"Glue job '{name}': {len(run_ids)} run(s) "
                f"in time window" + bcolors.ENDC
            )
            glue_app_group = "/aws-glue/jobs/output"
            if glue_app_group not in log_groups:
                log_groups.append(glue_app_group)
            stream_ids.extend(run_ids)

    if not log_groups:
        logging.error(
            bcolors.FAIL + f"No log groups found for resource(s) "
            f"{resources} in region {region}" + bcolors.ENDC
        )
        for name in resources:
            suggestions = _suggest_resource_names(name, region)
            if suggestions:
                logging.error(
                    bcolors.WARNING + f"Did you mean: "
                    f"{', '.join(suggestions)}?" + bcolors.ENDC
                )

    stream_filter = "|".join(stream_ids) if stream_ids else None
    return log_groups, stream_filter


def _suggest_resource_names(name, region):
    """Return up to 3 existing resource names similar to `name`.

    Candidates: Glue job names and resource names derived from log groups.
    """
    candidates = set()
    try:
        glue = boto3.client("glue", region_name=region)
        for page in glue.get_paginator("list_jobs").paginate():
            candidates.update(page.get("JobNames", []))
    except Exception:
        pass
    try:
        logs_client = boto3.client("logs", region_name=region)
        for page in logs_client.get_paginator("describe_log_groups").paginate():
            for lg in page.get("logGroups", []):
                resource = extract_resource_name(lg["logGroupName"])
                if resource:
                    candidates.add(resource)
    except Exception:
        pass
    return difflib.get_close_matches(name, candidates, n=3, cutoff=0.6)


LOG_LEVEL_PATTERN = re.compile(r"\b(CRITICAL|FATAL|ERROR|WARNING|WARN|INFO|DEBUG)\b")

# "key": value pairs in JSON-formatted log messages (string/number/bool/null values)
JSON_PAIR_PATTERN = re.compile(
    r'"(?P<key>[^"]+)"(?P<sep>\s*:\s*)'
    r'(?P<val>"(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?|true|false|null)'
)

_PART_COLORS = {
    "timestamp": bcolors.OKCYAN,
    "log_group": bcolors.OKBLUE,
    "log_stream": bcolors.HEADER,
    "resource": bcolors.OKGREEN,
}


def _colorize_json_pair(match):
    key, sep, val = match.group("key", "sep", "val")
    key_part = f'{bcolors.OKBLUE}"{key}"{bcolors.ENDC}'
    if val.startswith('"'):
        if key == "message":
            val_part = f"{bcolors.BOLD}{bcolors.WARNING}{val}{bcolors.ENDC}"
        elif key == "level":
            val_part = f"{bcolors.OKGREEN}{val}{bcolors.ENDC}"
        else:
            val_part = val
    else:
        # numbers, true/false, null
        val_part = f"{bcolors.HEADER}{val}{bcolors.ENDC}"
    return f"{key_part}{sep}{val_part}"


def _colorize_message(text):
    """Colorize one log message for terminal display.

    ERROR/CRITICAL messages are fully red, WARNING fully yellow (visibility
    first). Everything else gets field-level highlighting: JSON keys blue,
    the "message" value bold, the "level" value green, numbers/bools magenta.
    Plain-text messages just get their level token colored.
    """
    match = LOG_LEVEL_PATTERN.search(text)
    level = match.group(1) if match else ""
    if level in ("CRITICAL", "FATAL", "ERROR"):
        return bcolors.FAIL + text + bcolors.ENDC
    if level in ("WARNING", "WARN"):
        return bcolors.WARNING + text + bcolors.ENDC

    colored, count = JSON_PAIR_PATTERN.subn(_colorize_json_pair, text)
    if count:
        return colored
    if level:
        return text.replace(level, bcolors.OKGREEN + level + bcolors.ENDC, 1)
    return text


def colorize_parts(parts):
    """Render (text, kind) parts as one ANSI-colored line for terminal display.

    Message text is colored via _colorize_message; other kinds get a fixed
    color per _PART_COLORS.
    """
    out = []
    for text, kind in parts:
        if kind == "message":
            out.append(_colorize_message(text))
        elif kind in _PART_COLORS:
            out.append(_PART_COLORS[kind] + text + bcolors.ENDC)
        else:
            out.append(text)
    return " ".join(out)


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


def extract_resource_name(log_group, log_stream=None):
    """Extract AWS resource name from log group path and optionally log stream.

    Supports common AWS log group naming patterns:
      /aws/lambda/{function}         → function name
      /aws/kinesisfirehose/{stream}  → delivery stream name
      /aws/rds/cluster/{cluster}/..  → cluster name
      /aws/apigateway/{api}          → API name
      /aws/ecs/{service}             → service name
      /aws/codebuild/{project}       → project name
      /aws/elasticbeanstalk/{env}/.. → environment name
      /ecs/{service}                 → service name
      /aws-glue/jobs/{group}         → job name from log stream (shared log group)
      Custom log groups              → last path segment

    For Glue jobs (shared log group), the job run ID is in the log stream.
    """
    if not log_group:
        return None

    parts = log_group.strip("/").split("/")

    # AWS Glue: shared log group — job name is in the log stream
    # Log stream format: "jr_<hash>" or "{job-name}/{run-id}"
    if log_group.startswith("/aws-glue/") and log_stream:
        # Some Glue log streams contain the job name as prefix
        if "/" in log_stream:
            return log_stream.split("/")[0]
        return log_stream

    # Standard AWS service patterns: /aws/{service}/{resource}
    if len(parts) >= 3 and parts[0] == "aws":
        service = parts[1]
        # /aws/rds/cluster/{cluster-name}/error|audit|...
        if service == "rds" and len(parts) >= 4:
            return parts[3]
        # /aws/lambda/{function}, /aws/kinesisfirehose/{stream}, etc.
        return parts[2]

    # /ecs/{service-name}
    if len(parts) >= 2 and parts[0] == "ecs":
        return parts[1]

    # /aws-glue/jobs/{group} without log stream
    if len(parts) >= 3 and parts[0] == "aws-glue":
        return parts[2]

    # Fallback: last path segment
    return parts[-1] if parts else log_group


def get_logs(
    start_time,
    end_time,
    query,
    appname=None,
    log_groups=None,
    wait_sec=10,
    is_tail=False,
    show_resource=False,
    output_file_path=None,
):
    region = _get_region()
    insights = boto3.client("logs", region_name=region)

    # colorize only when printing to a terminal; raw text when piped/redirected
    use_color = sys.stdout.isatty()

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
    result_count = 0
    recent_timestamp = None
    last_seen_ptr = None

    # Determine output file path
    if output_file_path:
        filename = output_file_path
    elif appname:
        filename = f"/tmp/{appname}.log"

    with open(filename, "w") as output_file:
        is_first_chunk = True

        while True:
            if recent_timestamp and not is_first_chunk:
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

            if not results["results"]:
                if not is_tail:
                    if is_first_chunk:
                        logging.warning(
                            bcolors.WARNING + "   => 0 logs found which "
                            "match defined filter..." + bcolors.ENDC
                        )
                    break
                else:
                    time.sleep(wait_sec)
                    continue

            for log_event in results["results"]:
                log_fields = {field["field"]: field["value"] for field in log_event}

                # Skip the last event from previous chunk to avoid duplicates
                current_ptr = log_fields.get("@ptr")
                if current_ptr and current_ptr == last_seen_ptr:
                    continue

                # Build log line with explicit field ordering:
                # @timestamp first, then @logGroup/@logStream if present, then @message
                # Parts are (text, kind) tuples so the terminal line can be
                # colorized while the file/pipe output stays raw.
                ordered_parts = []
                if "@timestamp" in log_fields:
                    ordered_parts.append((log_fields["@timestamp"], "timestamp"))
                log_group_name = None
                if "@log" in log_fields:
                    # @log format: "accountId:logGroupName" — extract just the log group
                    log_group_name = log_fields["@log"].split(":", 1)[-1] if ":" in log_fields["@log"] else log_fields["@log"]
                    ordered_parts.append((f"[{log_group_name}]", "log_group"))
                elif "@logGroup" in log_fields:
                    log_group_name = log_fields["@logGroup"]
                    ordered_parts.append((f"[{log_group_name}]", "log_group"))
                log_stream_name = log_fields.get("@logStream")
                if log_stream_name:
                    ordered_parts.append((f"[{log_stream_name}]", "log_stream"))
                if show_resource and log_group_name:
                    resource = extract_resource_name(log_group_name, log_stream_name)
                    if resource:
                        ordered_parts.append((f"({resource})", "resource"))
                if "@message" in log_fields:
                    ordered_parts.append((log_fields["@message"], "message"))
                # Append any remaining fields (excluding known ones and @ptr)
                skip_fields = {"@timestamp", "@log", "@logGroup", "@logStream", "@message", "@ptr"}
                for field_entry in log_event:
                    if field_entry["field"] not in skip_fields:
                        ordered_parts.append((field_entry["value"], "other"))

                log_line = " ".join(text for text, _ in ordered_parts)
                print(colorize_parts(ordered_parts) if use_color else log_line)
                output_file.write(log_line + "\n")

                recent_timestamp = log_fields.get("@timestamp")

            # Track last event's @ptr for dedup across chunks
            last_event = results["results"][-1]
            last_seen_ptr = {f["field"]: f["value"] for f in last_event}.get("@ptr")

            result_count = len(results["results"])
            is_first_chunk = False

            # If fewer results than limit, we've got all logs
            if result_count < log_limit and not is_tail:
                break
