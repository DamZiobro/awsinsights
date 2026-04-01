awsinsights
================

Get and filter logs from multiple log groups of AWS CloudWatch and filter CloudWatch logs using predefined regular expressions.

This script uses [AWS CloudWatch Insights](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/AnalyzingLogData.html) service.

Install
-----------
`awsinsights` is released to public PyPI - [awsinsights](https://pypi.org/project/awsinsights/). It can be installed using this command:
```
pip install awsinsights
```

Basic Usage
-----------
1. Set up AWS Credentials.

2. **Define apps** (sets of CloudWatch log groups assigned to app name) in `$HOME/.awsinsights.json`
   file. See [example file](#example-of-config-file) below.

3. **Get all logs from the `simplebook` app (2 log groups pre-defined) since last 30 minutes**:
```
awsinsights --timedelta 30m --appname simplebook
```

4. **Filter logs from `simplebook` app since last 7d containing words 'Monday' or
   'Tuesday'** (you can use any Regular Expression)
```
awsinsights --timedelta 7d --appname simplebook --filter "Monday|Tuesday"
```


Advanced Usage
-----------

1. **Get logs from `simplebook` from 1 Jan 2021 10:00am to 2 Jan 2021 9:00am
   which contain 'Exception' or 'ERROR' on PROD environment**
```
awsinsights --env prod --start "2021-01-01 10:00:00" --end "2021-01-02 09:00:00" --appname simplebook --filter "Exception|ERROR"
```

2. **Get all logs from CloudWatch log groups `group-one-dev` and `/aws/lambda/group-two-dev` since last 2 hours:**

```
awsinsights --timedelta 2h --log_groups "group-one-dev" "/aws/lambda/group-two-dev"
```

3. **Custom CloudWatch Insights query** (override the default filter-based query):
```
awsinsights --appname simplebook --timedelta 2h --query "fields @timestamp, @message | filter @message not like /INFO/ | sort @timestamp"
```

Glob Patterns for Log Groups
-----------

Log group names in config and `--log_groups` support `*` and `?` glob wildcards. Patterns are resolved at runtime using the CloudWatch `describe_log_groups` API.

This is useful when log group names vary by environment or region:

```json
{
    "myapp": [
        "/aws/lambda/my-function-*",
        "/aws/lambda/api-$ENV-??"
    ]
}
```

For example, `/aws/lambda/my-api-*` will match:
- `/aws/lambda/my-api-dev-eu-central-1`
- `/aws/lambda/my-api-dev-us-east-1`
- `/aws/lambda/my-api-dev-ap-southeast-1`

Log groups without glob characters are passed through unchanged (no extra API calls).

Show Log Source
-----------

When querying multiple log groups, use these flags to identify which source produced each log line:

### `--show_log_group`

Include the CloudWatch log group name in brackets before each message:
```
awsinsights --appname myapp --show_log_group --timedelta 2h --filter "ERROR"
```
Output:
```
2026-04-01 02:57:19 [/aws-glue/jobs/etl-pipeline] java.lang.OutOfMemoryError: GC overhead limit exceeded
2026-04-01 23:00:10 [/aws/lambda/process-orders] [ERROR] Table "orders_summary" does not exist
```

### `--show_log_stream`

Include the CloudWatch log stream name in brackets:
```
awsinsights --appname myapp --show_log_stream --timedelta 2h --filter "ERROR"
```

### `--show_resource`

Extract and display the AWS resource name (Lambda function, Glue job, RDS cluster, etc.) in parentheses. The resource name is extracted from the log group path and/or log stream:

```
awsinsights --appname myapp --show_resource --timedelta 2h --filter "ERROR"
```
Output:
```
2026-04-01 02:57:19 [/aws-glue/jobs/etl-pipeline] [jr_abc123] (jr_abc123) java.lang.OutOfMemoryError...
2026-04-01 23:00:10 [/aws/lambda/process-orders] (process-orders) [ERROR] Table "orders_summary" does not exist
```

Supported resource extraction patterns:

| Log Group Pattern | Extracted Resource |
|-------------------|-------------------|
| `/aws/lambda/{function}` | Lambda function name |
| `/aws/kinesisfirehose/{stream}` | Firehose delivery stream name |
| `/aws/rds/cluster/{cluster}/...` | RDS cluster name |
| `/aws/apigateway/{api}` | API Gateway name |
| `/aws/codebuild/{project}` | CodeBuild project name |
| `/aws/elasticbeanstalk/{env}/...` | Elastic Beanstalk environment |
| `/ecs/{service}` | ECS service name |
| `/aws-glue/jobs/{group}` | Glue job run ID (from log stream) |
| Custom paths | Last path segment |

All three flags can be combined:
```
awsinsights --appname myapp --show_log_group --show_log_stream --show_resource --filter "ERROR"
```

Tail mode
-----------

awsinsights allows to listen CloudWatch in live mode which is called `tail
mode`.

It can be activated using `--tail` option.

Example - listening for ERRORs and Exceptions in tail mode:
```
awsinsights --timedelta 30m --appname simplebook --filter "ERROR|Exception" --tail
```

NOTE: Please notice that there might be **few mins delay** between the time when log really happened
and the time when it will appear in output of awsinsights' `tail mode`.



Example of config file
-----------

**Config file should be placed in `$HOME/.awsinsights.json`**

This example file contains 3 apps: `simplebook`, `secondapp`, and `my-pipeline`.
Each app consists of CloudWatch log groups. Glob patterns (`*`, `?`) are supported.

```json
{
    "simplebook": [
        "/aws/lambda/simple-books-catalog-api-$ENV",
        "/aws/lambda/api-task-2-ad"
    ],
    "secondapp": [
        "first-log-group",
        "/aws/lambda/second-log-group"
    ],
    "my-pipeline": [
        "/aws-glue/jobs/etl-pipeline",
        "/aws/lambda/ingest-*",
        "/aws/lambda/process-*",
        "/aws/lambda/export-to-db",
        "/aws/kinesisfirehose/event-stream-$ENV"
    ]
}
```

The `$ENV` variable is replaced with the `--env` value (default: `dev`).
Glob patterns (`*`, `?`) are resolved at runtime against actual CloudWatch log groups.

Output file
-----------

Logs will be written to output file. Output file will be:
* `/tmp/{appname}.log` **if app name is defined** using `--appname` option OR
* `/tmp/awsinsights.log` **if app name is NOT defined**

Help
-----------

```
awsinsights [-h] [--timedelta TIMEDELTA] [--start START] [--end END]
                   [--filter FILTER]
                   (--appname APPNAME | --log_groups LOG_GROUPS [LOG_GROUPS ...])
                   [--env ENV] [--query QUERY] [--wait WAIT] [--tail]
                   [--show_log_group] [--show_log_stream] [--show_resource]

optional arguments:
  -h, --help            show this help message and exit
  --timedelta TIMEDELTA
                        delta time since now when logs should be filtered ex.
                        120m, 3h, 2d. Default: 60m
  --start START         start time of grabbing logs. Format: YYYY-MM-DD
                        HH:MM:SS
  --end END             end time of grabbing logs. Format: YYYY-MM-DD HH:MM:SS
  --filter FILTER       Regular expression for filtering logs
  --appname APPNAME     name of the app which logs should be analysed. App
                        names should have logs groups configured in
                        .awsinsights.json file. See README.md file.
  --log_groups LOG_GROUPS [LOG_GROUPS ...]
                        list of the log groups to analyse (up to 20).
                        Supports glob patterns (* and ?)
  --env ENV             env name. It can replace "$ENV" phrase in log groups
                        names. Default: dev
  --query QUERY         Custom full AWS CloudWatch Insights query. Default:
                        fields @timestamp, @message | filter @message like //
                        | sort @timestamp
  --wait WAIT           wait time for single AWS Insights Query results in
                        seconds. Default: 10
  --tail                TAIL MODE. Listen for live logs forever
  --show_log_group      Include log group name in output before each log
                        message
  --show_log_stream     Include log stream name in output before each log
                        message
  --show_resource       Include AWS resource name (Lambda function, Glue job,
                        etc.) extracted from log group/stream in output
```
