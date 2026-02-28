"""
Multi-Account Cost Analysis Tools
Provides cross-account cost aggregation and comparison
"""

import boto3
import json
from datetime import datetime, timedelta
from typing import List, Optional


def get_linked_accounts() -> str:
    """
    Get all linked accounts in the organization.
    
    Returns:
        str: JSON with linked account IDs and names
    """
    try:
        # Try Organizations API first
        try:
            org_client = boto3.client('organizations')
            response = org_client.list_accounts()
            
            accounts = []
            for account in response.get('Accounts', []):
                accounts.append({
                    'account_id': account['Id'],
                    'name': account['Name'],
                    'email': account['Email'],
                    'status': account['Status']
                })
            
            return json.dumps({
                'total_accounts': len(accounts),
                'accounts': accounts,
                'source': 'organizations'
            }, indent=2)
            
        except Exception:
            # Fallback: Get from Cost Explorer dimension values
            ce_client = boto3.client('ce')
            
            # Get last 90 days to ensure we capture all accounts
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
            
            response = ce_client.get_dimension_values(
                TimePeriod={'Start': start_date, 'End': end_date},
                Dimension='LINKED_ACCOUNT'
            )
            
            accounts = []
            for dim in response.get('DimensionValues', []):
                accounts.append({
                    'account_id': dim['Value'],
                    'name': f"Account-{dim['Value'][-4:]}",  # Use last 4 digits as name
                    'source': 'cost_explorer'
                })
            
            return json.dumps({
                'total_accounts': len(accounts),
                'accounts': accounts,
                'source': 'cost_explorer'
            }, indent=2)
            
    except Exception as e:
        return json.dumps({
            'error': str(e),
            'message': 'Failed to retrieve linked accounts'
        })


def get_multi_account_costs(account_ids: Optional[List[str]] = None, time_period: str = "LAST_30_DAYS") -> str:
    """
    Get cost breakdown across multiple linked accounts (for payer account).
    
    Args:
        account_ids: List of account IDs. If None, shows all linked accounts
        time_period: LAST_7_DAYS, LAST_30_DAYS, or LAST_90_DAYS
    
    Returns:
        str: JSON with linked accounts cost breakdown
    """
    try:
        ce_client = boto3.client("ce")
        
        # Calculate date range
        days = {"LAST_7_DAYS": 7, "LAST_30_DAYS": 30, "LAST_90_DAYS": 90}.get(time_period, 30)
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        # Build filter for specific accounts if provided
        filter_expr = None
        if account_ids:
            filter_expr = {
                "Dimensions": {
                    "Key": "LINKED_ACCOUNT",
                    "Values": account_ids
                }
            }
        
        # Get costs grouped by linked account (payer account can see all)
        response = ce_client.get_cost_and_usage(
            TimePeriod={"Start": start_date, "End": end_date},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "LINKED_ACCOUNT"}],
            Filter=filter_expr
        )
        
        accounts = {}
        total_cost = 0.0
        
        for result in response.get("ResultsByTime", []):
            for group in result.get("Groups", []):
                account_id = group["Keys"][0]
                cost = float(group["Metrics"]["UnblendedCost"]["Amount"])
                accounts[account_id] = accounts.get(account_id, 0) + cost
                total_cost += cost
        
        # Sort by cost (highest first)
        sorted_accounts = sorted(accounts.items(), key=lambda x: x[1], reverse=True)
        
        results = {
            "time_period": {"start": start_date, "end": end_date, "days": days},
            "total_linked_accounts": len(accounts),
            "total_cost": round(total_cost, 2),
            "linked_accounts": [
                {
                    "account_id": acc_id,
                    "cost": round(cost, 2),
                    "percentage": round((cost / total_cost * 100) if total_cost > 0 else 0, 2)
                }
                for acc_id, cost in sorted_accounts
            ]
        }
        
        return json.dumps(results, indent=2)
        
    except Exception as e:
        return json.dumps({"error": str(e), "message": "Failed to get linked accounts costs. Ensure this is run from payer account."})


def compare_account_costs(account_ids: List[str], time_period: str = "LAST_30_DAYS") -> str:
    """
    Compare costs between specific linked accounts with service breakdown.
    
    Args:
        account_ids: List of linked account IDs to compare
        time_period: Analysis time period
    
    Returns:
        str: JSON with detailed account comparison
    """
    try:
        ce_client = boto3.client("ce")
        
        days = {"LAST_7_DAYS": 7, "LAST_30_DAYS": 30, "LAST_90_DAYS": 90}.get(time_period, 30)
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        account_details = {}
        
        for account_id in account_ids:
            # Get service breakdown for each linked account
            response = ce_client.get_cost_and_usage(
                TimePeriod={"Start": start_date, "End": end_date},
                Granularity="MONTHLY",
                Metrics=["UnblendedCost"],
                GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
                Filter={
                    "Dimensions": {
                        "Key": "LINKED_ACCOUNT",
                        "Values": [account_id]
                    }
                }
            )
            
            services = {}
            total_cost = 0.0
            
            for result in response.get("ResultsByTime", []):
                for group in result.get("Groups", []):
                    service = group["Keys"][0]
                    cost = float(group["Metrics"]["UnblendedCost"]["Amount"])
                    services[service] = cost
                    total_cost += cost
            
            # Get top 5 services for this account
            top_services = sorted(services.items(), key=lambda x: x[1], reverse=True)[:5]
            
            account_details[account_id] = {
                "total_cost": round(total_cost, 2),
                "top_services": [
                    {"service": svc, "cost": round(cost, 2)}
                    for svc, cost in top_services
                ]
            }
        
        # Find highest and lowest cost accounts
        if account_details:
            highest_cost_account = max(account_details.items(), key=lambda x: x[1]["total_cost"])
            lowest_cost_account = min(account_details.items(), key=lambda x: x[1]["total_cost"])
        else:
            highest_cost_account = lowest_cost_account = None
        
        results = {
            "time_period": {"start": start_date, "end": end_date, "days": days},
            "accounts_compared": len(account_ids),
            "comparison": account_details,
            "summary": {
                "highest_cost_account": {
                    "account_id": highest_cost_account[0],
                    "cost": highest_cost_account[1]["total_cost"]
                } if highest_cost_account else None,
                "lowest_cost_account": {
                    "account_id": lowest_cost_account[0], 
                    "cost": lowest_cost_account[1]["total_cost"]
                } if lowest_cost_account else None,
                "total_combined_cost": round(sum(acc["total_cost"] for acc in account_details.values()), 2)
            }
        }
        
        return json.dumps(results, indent=2)
        
    except Exception as e:
        return json.dumps({"error": str(e), "message": "Failed to compare linked accounts costs. Ensure this is run from payer account."})
