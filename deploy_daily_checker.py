"""
部署每日成本检查系统
创建EventBridge Rule、Lambda Function和SNS Topic
"""

import boto3
import json
import zipfile
import os
from pathlib import Path


def deploy_daily_cost_checker():
    """部署每日成本检查系统"""
    
    # 读取agent ARN
    agent_arn_file = Path('.agent_arn')
    if not agent_arn_file.exists():
        print("❌ 请先部署agent (运行 python deploy.py)")
        return
    
    with open(agent_arn_file, 'r') as f:
        agent_runtime_arn = f.read().strip()
    
    # 获取账户信息
    sts_client = boto3.client('sts')
    account_id = sts_client.get_caller_identity()['Account']
    region = 'us-east-1'
    
    # 初始化客户端
    sns_client = boto3.client('sns', region_name=region)
    lambda_client = boto3.client('lambda', region_name=region)
    events_client = boto3.client('events', region_name=region)
    iam_client = boto3.client('iam', region_name=region)
    
    print("🚀 开始部署每日成本检查系统...")
    
    # 1. 创建SNS Topic
    print("📧 创建SNS Topic...")
    topic_response = sns_client.create_topic(
        Name='cost-anomaly-alerts',
        Tags=[
            {'Key': 'Project', 'Value': 'cost-optimization-agent'},
            {'Key': 'Purpose', 'Value': 'daily-cost-alerts'}
        ]
    )
    sns_topic_arn = topic_response['TopicArn']
    print(f"✅ SNS Topic创建成功: {sns_topic_arn}")
    
    # 2. 创建Lambda执行角色
    print("🔐 创建Lambda执行角色...")
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "lambda.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }
        ]
    }
    
    role_name = 'daily-cost-checker-role'
    try:
        iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Tags=[
                {'Key': 'Project', 'Value': 'cost-optimization-agent'}
            ]
        )
    except iam_client.exceptions.EntityAlreadyExistsException:
        print("⚠️ IAM角色已存在，跳过创建")
    
    # 附加权限策略
    lambda_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream", 
                    "logs:PutLogEvents"
                ],
                "Resource": f"arn:aws:logs:{region}:{account_id}:*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "bedrock-agentcore:InvokeAgentRuntime"
                ],
                "Resource": agent_runtime_arn
            },
            {
                "Effect": "Allow",
                "Action": [
                    "sns:Publish"
                ],
                "Resource": sns_topic_arn
            }
        ]
    }
    
    iam_client.put_role_policy(
        RoleName=role_name,
        PolicyName='DailyCostCheckerPolicy',
        PolicyDocument=json.dumps(lambda_policy)
    )
    
    role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"
    print(f"✅ Lambda角色创建成功: {role_arn}")
    
    # 3. 创建Lambda部署包
    print("📦 创建Lambda部署包...")
    zip_path = '/tmp/daily_cost_checker.zip'
    with zipfile.ZipFile(zip_path, 'w') as zip_file:
        zip_file.write('daily_cost_checker.py', 'lambda_function.py')
    
    # 4. 部署Lambda函数
    print("⚡ 部署Lambda函数...")
    function_name = 'daily-cost-checker'
    
    with open(zip_path, 'rb') as zip_file:
        try:
            lambda_client.create_function(
                FunctionName=function_name,
                Runtime='python3.9',
                Role=role_arn,
                Handler='lambda_function.lambda_handler',
                Code={'ZipFile': zip_file.read()},
                Environment={
                    'Variables': {
                        'AGENT_RUNTIME_ARN': agent_runtime_arn,
                        'SNS_TOPIC_ARN': sns_topic_arn
                    }
                },
                Timeout=300,
                Tags={
                    'Project': 'cost-optimization-agent',
                    'Purpose': 'daily-cost-check'
                }
            )
        except lambda_client.exceptions.ResourceConflictException:
            # 更新现有函数
            lambda_client.update_function_code(
                FunctionName=function_name,
                ZipFile=zip_file.read()
            )
            lambda_client.update_function_configuration(
                FunctionName=function_name,
                Environment={
                    'Variables': {
                        'AGENT_RUNTIME_ARN': agent_runtime_arn,
                        'SNS_TOPIC_ARN': sns_topic_arn
                    }
                }
            )
    
    lambda_arn = f"arn:aws:lambda:{region}:{account_id}:function:{function_name}"
    print(f"✅ Lambda函数部署成功: {lambda_arn}")
    
    # 5. 创建EventBridge规则 (每天8:00 UTC)
    print("⏰ 创建EventBridge规则...")
    rule_name = 'daily-cost-check-rule'
    
    events_client.put_rule(
        Name=rule_name,
        ScheduleExpression='cron(0 8 * * ? *)',  # 每天8:00 UTC
        Description='每日成本异常检查',
        State='ENABLED',
        Tags=[
            {'Key': 'Project', 'Value': 'cost-optimization-agent'}
        ]
    )
    
    # 6. 添加Lambda目标
    events_client.put_targets(
        Rule=rule_name,
        Targets=[
            {
                'Id': '1',
                'Arn': lambda_arn
            }
        ]
    )
    
    # 7. 给EventBridge权限调用Lambda
    try:
        lambda_client.add_permission(
            FunctionName=function_name,
            StatementId='allow-eventbridge',
            Action='lambda:InvokeFunction',
            Principal='events.amazonaws.com',
            SourceArn=f"arn:aws:events:{region}:{account_id}:rule/{rule_name}"
        )
    except lambda_client.exceptions.ResourceConflictException:
        print("⚠️ Lambda权限已存在，跳过添加")
    
    print("✅ EventBridge规则创建成功")
    
    print(f"""
🎉 每日成本检查系统部署完成！

📧 SNS Topic: {sns_topic_arn}
⚡ Lambda函数: {lambda_arn}  
⏰ 检查时间: 每天8:00 UTC

下一步：
1. 订阅SNS Topic接收告警邮件:
   aws sns subscribe --topic-arn {sns_topic_arn} --protocol email --notification-endpoint your-email@example.com

2. 手动测试Lambda函数:
   aws lambda invoke --function-name {function_name} response.json

3. 查看CloudWatch日志:
   aws logs describe-log-groups --log-group-name-prefix /aws/lambda/{function_name}
    """)


if __name__ == "__main__":
    deploy_daily_cost_checker()
