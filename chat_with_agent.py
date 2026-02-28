#!/usr/bin/env python3
"""
Interactive chat with the deployed Cost Optimization Agent
"""

import boto3
import json
import sys
from pathlib import Path


def get_runtime_arn():
    """Get the runtime ARN from .agent_arn file"""
    arn_file = Path(".agent_arn")
    if not arn_file.exists():
        print("❌ .agent_arn file not found. Deploy the agent first.")
        sys.exit(1)

    with open(arn_file, "r") as f:
        return f.read().strip()


def chat_with_agent(runtime_arn: str, query: str):
    """Send query to agent and get response"""
    client = boto3.client("bedrock-agentcore", region_name="us-east-1")

    try:
        response = client.invoke_agent_runtime(
            agentRuntimeArn=runtime_arn, 
            qualifier="DEFAULT", 
            payload=json.dumps({"prompt": query})
        )

        # Process streaming response
        full_response = []
        for line in response["response"].iter_lines(chunk_size=1):
            if line:
                line_str = line.decode("utf-8")
                if line_str.startswith("data: "):
                    data = line_str[6:]  # Remove 'data: ' prefix
                    try:
                        chunk = json.loads(data)
                        if chunk.get("type") == "chunk":
                            full_response.append(chunk.get("data", ""))
                    except json.JSONDecodeError:
                        continue

        return "".join(full_response)

    except Exception as e:
        return f"❌ Error: {e}"


def main():
    """Interactive chat loop"""

    # Get runtime ARN
    runtime_arn = get_runtime_arn()
    print(f"🤖 Connected to agent: {runtime_arn.split('/')[-1]}\n")

    while True:
        try:
            # Get user input
            user_input = input("💬 You: ").strip()
            
            # Check for exit commands
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("\n👋 Goodbye!")
                break
            
            if not user_input:
                continue
            
            # Send to agent
            print("\n🤖 Agent: ", end="", flush=True)
            response = chat_with_agent(runtime_arn, user_input)
            print(response)
            print("\n" + "─" * 80 + "\n")
            
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}\n")


if __name__ == "__main__":
    main()
