"""
Daily Cost Anomaly Checker Lambda Function
每天8:00通过EventBridge触发，调用AgentCore Runtime检查成本异常
"""

import json
import boto3
import os
from datetime import datetime


def lambda_handler(event, context):
    """
    Lambda处理函数 - 每日成本异常检查
    """
    
    # 获取环境变量
    agent_runtime_arn = os.environ['AGENT_RUNTIME_ARN']
    sns_topic_arn = os.environ['SNS_TOPIC_ARN']
    
    # 初始化AWS客户端
    agentcore_client = boto3.client('bedrock-agentcore', region_name='us-east-1')
    sns_client = boto3.client('sns', region_name='us-east-1')
    
    try:
        # 调用AgentCore Runtime进行成本异常检查
        query = "检查过去7天的成本异常，如果发现异常请详细说明"
        
        response = agentcore_client.invoke_agent_runtime(
            agentRuntimeArn=agent_runtime_arn,
            qualifier='DEFAULT',
            payload=json.dumps({"prompt": query})
        )
        
        # 处理流式响应
        full_response = []
        for line in response['response'].iter_lines(chunk_size=1):
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith('data: '):
                    data = line_str[6:]
                    try:
                        chunk = json.loads(data)
                        if chunk.get('type') == 'chunk':
                            full_response.append(chunk.get('data', ''))
                    except json.JSONDecodeError:
                        continue
        
        agent_response = ''.join(full_response)
        
        # 检查是否发现异常（简单关键词检测）
        anomaly_keywords = ['异常', '异常检测', '成本激增', '超出预期', '显著增长']
        has_anomaly = any(keyword in agent_response for keyword in anomaly_keywords)
        
        if has_anomaly:
            # 发送SNS告警
            message = f"""
🚨 AWS成本异常告警

检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

异常详情:
{agent_response}

请及时查看AWS控制台进行确认和处理。
            """
            
            sns_client.publish(
                TopicArn=sns_topic_arn,
                Subject='AWS成本异常告警 - 需要关注',
                Message=message
            )
            
            print(f"发现成本异常，已发送SNS告警到: {sns_topic_arn}")
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': '发现成本异常，已发送告警',
                    'anomaly_detected': True,
                    'response': agent_response
                })
            }
        else:
            print("未发现成本异常，无需告警")
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': '成本检查正常，无异常',
                    'anomaly_detected': False,
                    'response': agent_response
                })
            }
            
    except Exception as e:
        error_message = f"成本检查失败: {str(e)}"
        print(error_message)
        
        # 发送错误告警
        sns_client.publish(
            TopicArn=sns_topic_arn,
            Subject='AWS成本检查系统错误',
            Message=f"""
❌ 每日成本检查系统发生错误

错误时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
错误信息: {str(e)}

请检查Lambda函数和AgentCore Runtime状态。
            """
        )
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': error_message
            })
        }
