## Quick Start

### Prerequisites
- AWS CLI configured with appropriate permissions
- Cost Explorer enabled in your AWS account
- Python 3.10+ installed

### Installation & Deployment

1. **Setup:**
   pip install -r requirements.txt

2. **Test Locally (Optional but Recommended):**
   ```bash
   python test_local.py
   ```

3. **Deploy to AWS:**
   ```bash
   python deploy.py
   ```
   **Duration:** ~5 minutes. Creates IAM roles, AgentCore Memory, builds container, and deploys runtime.

4. **Test Deployed Agent:**
   ```bash
   python test_agentcore_runtime.py
   ```
   **OR**
   ```bash
   python chat_with_agent.py
   ```
   Confirms the deployed agent responds intelligently to cost optimization queries.


## Monitoring

### CloudWatch Logs
Monitor your agent after deployment:
```bash
# View logs (replace with your agent ID from deployment output)
aws logs tail /aws/bedrock-agentcore/runtimes/{agent-id}-DEFAULT --follow
```

### Observability Dashboard
Access the GenAI Observability Dashboard:
- **URL**: https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#gen-ai-observability/agent-core
- **Features**: Real-time metrics, traces, and performance monitoring

## Resource Cleanup

### Complete Cleanup
Remove all AWS resources when done:

```bash
# Complete cleanup (removes everything with project tags)
python cleanup.py
```
