"""
Database Helper - DynamoDB Operations Made Simple
==================================================

Why this file exists:
- boto3 DynamoDB API is verbose and complex
- Every agent needs to save/load state
- We want consistent error handling
- DRY principle: write once, use everywhere

What it provides:
- save_state() - Save agent data
- get_state() - Retrieve agent data  
- delete_state() - Clean up data
- All with built-in error handling
"""

import os
import boto3
from datetime import datetime, timezone
from typing import Dict, Any, Optional

# ============================================
# INITIALIZE DYNAMODB CLIENT
# ============================================
# boto3.resource gives us high-level interface (easier than client)
dynamodb = boto3.resource('dynamodb')

# Get table name from environment variable (set in serverless.yml)
STATE_TABLE_NAME = os.environ.get('AGENT_STATE_TABLE', 'ClinisightAgentState-dev')

# Get reference to the table
# This doesn't create the table - serverless.yml already did that
state_table = dynamodb.Table(STATE_TABLE_NAME)


# ============================================
# SAVE STATE FUNCTION
# ============================================
def save_state(tenant_id: str, agent_name: str, data: Dict[str, Any]) -> bool:
    """
    Save agent state to DynamoDB.
    
    Args:
        tenant_id: Customer identifier (e.g., "acme-health")
        agent_name: Which agent (e.g., "TaskSmith")
        data: Dictionary of data to save (e.g., {"tasks_created": 5})
    
    Returns:
        True if successful, False if error
    
    Example:
        save_state("acme", "TaskSmith", {
            "epic_key": "HC-100",
            "subtasks_created": 5,
            "last_run": "2025-01-15T10:00:00Z"
        })
    
    What happens in DynamoDB:
        Item created/updated with:
        - tenantId: "acme" (partition key)
        - agentName: "TaskSmith" (sort key)
        - stateData: {...your data...}
        - updatedAt: "2025-01-15T10:05:00Z"
    """
    try:
        # Build the item to save
        item = {
            # Primary key
            'tenantId': tenant_id,
            'agentName': agent_name,
            
            # Your data
            'stateData': data,
            
            # Metadata (useful for debugging)
            'updatedAt': datetime.now(timezone.utc).isoformat(),
        }
        
        # put_item = create or replace item
        # This is like: INSERT OR REPLACE in SQL
        state_table.put_item(Item=item)
        
        print(f"✅ Saved state for {agent_name} (tenant: {tenant_id})")
        return True
        
    except Exception as e:
        # If anything goes wrong, log it but don't crash
        print(f"❌ Error saving state: {str(e)}")
        return False


# ============================================
# GET STATE FUNCTION
# ============================================
def get_state(tenant_id: str, agent_name: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve agent state from DynamoDB.
    
    Args:
        tenant_id: Customer identifier
        agent_name: Which agent
    
    Returns:
        Dictionary with state data, or None if not found
    
    Example:
        state = get_state("acme", "TaskSmith")
        if state:
            print(f"Last epic: {state['epic_key']}")
        else:
            print("No state found - agent hasn't run yet")
    """
    try:
        # get_item = fetch one item by primary key
        # This is like: SELECT * WHERE tenantId=? AND agentName=?
        response = state_table.get_item(
            Key={
                'tenantId': tenant_id,
                'agentName': agent_name
            }
        )
        
        # Check if item exists
        if 'Item' in response:
            # Return just the data part, not metadata
            return response['Item'].get('stateData', {})
        else:
            print(f"ℹ️ No state found for {agent_name} (tenant: {tenant_id})")
            return None
            
    except Exception as e:
        print(f"❌ Error getting state: {str(e)}")
        return None


# ============================================
# DELETE STATE FUNCTION
# ============================================
def delete_state(tenant_id: str, agent_name: str) -> bool:
    """
    Delete agent state from DynamoDB.
    Useful for testing or cleanup.
    
    Args:
        tenant_id: Customer identifier
        agent_name: Which agent
    
    Returns:
        True if successful
    
    Example:
        delete_state("acme", "TaskSmith")
        # State is now gone - next get_state() will return None
    """
    try:
        # delete_item = remove item by primary key
        state_table.delete_item(
            Key={
                'tenantId': tenant_id,
                'agentName': agent_name
            }
        )
        
        print(f"✅ Deleted state for {agent_name} (tenant: {tenant_id})")
        return True
        
    except Exception as e:
        print(f"❌ Error deleting state: {str(e)}")
        return False


# ============================================
# QUERY ALL AGENTS FOR A TENANT
# ============================================
def get_all_agent_states(tenant_id: str) -> Dict[str, Dict[str, Any]]:
    """
    Get state for ALL agents belonging to a tenant.
    
    This uses DynamoDB Query (not Scan):
    - Query is efficient (uses partition key)
    - Returns all items in one partition
    - Sorted by agent name
    
    Args:
        tenant_id: Customer identifier
    
    Returns:
        Dictionary mapping agent names to their state
        Example: {
            "TaskSmith": {"epic_key": "HC-100", ...},
            "CareTrack": {"last_check": "...", ...},
        }
    
    Why useful:
        For Rovo insights - get all agent data in one call
    """
    try:
        # Query = efficient lookup using partition key
        # This is like: SELECT * WHERE tenantId = ?
        response = state_table.query(
            KeyConditionExpression='tenantId = :tid',
            ExpressionAttributeValues={
                ':tid': tenant_id
            }
        )
        
        # Convert list of items to dictionary
        result = {}
        for item in response.get('Items', []):
            agent_name = item['agentName']
            result[agent_name] = item.get('stateData', {})
        
        print(f"✅ Retrieved {len(result)} agent states for tenant {tenant_id}")
        return result
        
    except Exception as e:
        print(f"❌ Error querying states: {str(e)}")
        return {}


# ============================================
# UNDERSTANDING: Query vs Scan
# ============================================
"""
DynamoDB has two ways to get multiple items:

1. QUERY (what we use)
   - Uses partition key (tenantId)
   - Fast and efficient
   - Only reads relevant items
   - Example: "Give me all agents for acme"
   
2. SCAN (avoid if possible)
   - Reads entire table
   - Slow and expensive
   - Uses lots of read capacity
   - Example: "Give me all items where epic_key contains 'HC'"
   
Rule of thumb: Use Query when you have the partition key, which we always do!
"""

# ============================================
# TESTING (Run this file directly)
# ============================================
if __name__ == '__main__':
    # This only runs if you execute: python database.py
    # Won't run when imported by other files
    
    print("Testing database operations...")
    
    # Test save
    success = save_state("test-tenant", "TestAgent", {
        "test_key": "test_value",
        "count": 42
    })
    print(f"Save test: {'✅' if success else '❌'}")
    
    # Test get
    state = get_state("test-tenant", "TestAgent")
    print(f"Get test: {'✅' if state else '❌'}")
    print(f"Retrieved data: {state}")
    
    # Test delete
    success = delete_state("test-tenant", "TestAgent")
    print(f"Delete test: {'✅' if success else '❌'}")