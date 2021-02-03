awsinsights
================

Get and filter logs from multiple log groups of AWS CloudWatch and filter CloudWatch logs using predefined regular expressions. 

This script uses [AWS CloudWatch Insights](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/AnalyzingLogData.html) service.

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
   'Tuesday'** (you can use any Regular Expression in )
```
awsinsights --timedelta 7d --appname simplebook --filter "Monday|Tuesday"
```


Advanced Usage
-----------

1. **Get logs from `simplebook` from 1 Jan 2021 10:00am to 2 Jan 2021 9:00am
   which contain 'Exception' or 'ERROR' on PROD environment**
```
awsinsights --env prod --start 2021-01-01 10:00:00 --end 2021-01-02 09:00:00 --appname simplebook --filter "Exception|ERROR"
```

2. **Get all logs from CloudWatch log groups `group-one-dev` and `/aws/lambda/group-two-dev` since last 2 hours:**

```
awsinsights --timedelta 2h --log_groups "group-one-dev" "/aws/lambda/group-two-dev"
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

This example file contains 2 apps: `simplebook` and `secondapp`. 
Each app consits of 2 CloudWatch log groups.

```
{
    "simplebook": [
        "/aws/lambda/simple-books-catalog-api-$ENV",
        "/aws/lambda/api-task-2-ad"
    ],
    "secondapp": [
        "first-log-group",
        "/aws/lambda/second-log-group"
    ]
}
```

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
                   [--env ENV] [--query QUERY]

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
                        .awsinsightsrc file. See README.md file.
  --log_groups LOG_GROUPS [LOG_GROUPS ...]
                        list of the log groups " "to analyse (up to 20)
  --env ENV             env name. It can be used to resolve "{env}" var in log
                        groups names. Default: dev
  --query QUERY         Custom full AWS CloudWatch Insights query. " "Default:
                        fields @timestamp, @message | filter @message like //
                        | sort @timestamp
  --tail                TAIL MODE. If set to "true", It will listen for live
                        logs forever
```
