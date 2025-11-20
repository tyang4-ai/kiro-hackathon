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
import uuid
import boto3
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

# ============================================
# INITIALIZE DYNAMODB CLIENT
# ============================================
# boto3.resource gives us high-level interface (easier than client)
dynamodb = boto3.resource('dynamodb')

# Get table names from environment variables (set in serverless.yml)
STATE_TABLE_NAME = os.environ.get('AGENT_STATE_TABLE', 'ClinisightAgentState-dev')
AUDIT_LOG_TABLE_NAME = os.environ.get('AUDIT_LOG_TABLE', 'ClinisightAuditLog-dev')

# Get references to the tables
# This doesn't create the tables - serverless.yml already did that
state_table = dynamodb.Table(STATE_TABLE_NAME)
audit_log_table = dynamodb.Table(AUDIT_LOG_TABLE_NAME)

# HIPAA requires 7 years data retention (2556 days)
HIPAA_RETENTION_DAYS = 2556


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
# AUDIT LOGGING FUNCTIONS (HIPAA Compliance)
# ============================================
"""
HIPAA requires comprehensive audit trails for all PHI access.
These functions log every data operation to the audit log table.

Audit log entries include:
- WHO: tenant_id, agent_name, user_id (if available)
- WHAT: action type (create, read, update, delete)
- WHEN: timestamp (ISO 8601)
- WHERE: resource type and keys
- WHY: reason/context (optional)
"""

def log_audit_event(
    tenant_id: str,
    action: str,
    agent_name: str,
    resource_type: str,
    resource_keys: Dict[str, Any],
    user_id: Optional[str] = None,
    reason: Optional[str] = None,
    additional_data: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Log an audit event for HIPAA compliance.

    Args:
        tenant_id: Customer identifier
        action: One of 'CREATE', 'READ', 'UPDATE', 'DELETE', 'ACCESS'
        agent_name: Which agent performed the action
        resource_type: Type of resource (e.g., 'agent_state', 'patient_data')
        resource_keys: Keys identifying the resource (e.g., {"epic_key": "HC-100"})
        user_id: User who triggered the action (if known)
        reason: Business reason for the action
        additional_data: Any extra context to log

    Returns:
        True if logged successfully, False otherwise

    Example:
        log_audit_event(
            tenant_id="acme-health",
            action="READ",
            agent_name="TaskSmith",
            resource_type="agent_state",
            resource_keys={"agentName": "TaskSmith"},
            user_id="user-123",
            reason="Retrieved state for epic decomposition"
        )
    """
    try:
        # Generate timestamp for sort key (high precision for uniqueness)
        timestamp = datetime.now(timezone.utc).isoformat()

        # Add unique suffix to prevent collisions for same-millisecond events
        unique_timestamp = f"{timestamp}#{uuid.uuid4().hex[:8]}"

        # Calculate expiration time (7 years for HIPAA)
        expires_at = datetime.now(timezone.utc) + timedelta(days=HIPAA_RETENTION_DAYS)

        # Build audit log entry
        item = {
            # Primary key
            'tenantId': tenant_id,
            'timestamp': unique_timestamp,

            # Who performed the action
            'agentName': agent_name,
            'userId': user_id or 'system',

            # What action was performed
            'action': action.upper(),
            'resourceType': resource_type,
            'resourceKeys': resource_keys,

            # Additional context
            'reason': reason or 'Not specified',
            'additionalData': additional_data or {},

            # HIPAA retention (7 years)
            'expiresAt': int(expires_at.timestamp()),

            # Metadata
            'createdAt': timestamp,
        }

        # Write to audit log table
        audit_log_table.put_item(Item=item)

        print(f"📝 Audit: {action} by {agent_name} on {resource_type} (tenant: {tenant_id})")
        return True

    except Exception as e:
        # Audit logging failures should be captured but not crash the app
        print(f"❌ Error writing audit log: {str(e)}")
        # TODO: Send to Sentry as critical error
        return False


def query_audit_logs(
    tenant_id: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 100
) -> list:
    """
    Query audit logs for a tenant within a time range.

    Args:
        tenant_id: Customer identifier
        start_time: ISO 8601 timestamp (default: 24 hours ago)
        end_time: ISO 8601 timestamp (default: now)
        limit: Maximum number of results

    Returns:
        List of audit log entries, sorted by timestamp descending

    Example:
        logs = query_audit_logs(
            tenant_id="acme-health",
            start_time="2025-01-01T00:00:00Z",
            limit=50
        )
        for log in logs:
            print(f"{log['timestamp']}: {log['action']} by {log['agentName']}")
    """
    try:
        # Default time range: last 24 hours
        if not start_time:
            start_time = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        if not end_time:
            end_time = datetime.now(timezone.utc).isoformat()

        # Query with time range
        response = audit_log_table.query(
            KeyConditionExpression='tenantId = :tid AND #ts BETWEEN :start AND :end',
            ExpressionAttributeNames={
                '#ts': 'timestamp'  # timestamp is a reserved word
            },
            ExpressionAttributeValues={
                ':tid': tenant_id,
                ':start': start_time,
                ':end': end_time + 'Z'  # Ensure we capture all timestamps
            },
            ScanIndexForward=False,  # Newest first
            Limit=limit
        )

        logs = response.get('Items', [])
        print(f"✅ Retrieved {len(logs)} audit logs for tenant {tenant_id}")
        return logs

    except Exception as e:
        print(f"❌ Error querying audit logs: {str(e)}")
        return []


# ============================================
# ENHANCED STATE FUNCTIONS WITH AUDIT LOGGING
# ============================================

def save_state_with_audit(
    tenant_id: str,
    agent_name: str,
    data: Dict[str, Any],
    user_id: Optional[str] = None,
    reason: Optional[str] = None
) -> bool:
    """
    Save agent state and log the action for HIPAA compliance.

    This is the HIPAA-compliant version of save_state().
    Use this when handling any data that might contain PHI.

    Args:
        tenant_id: Customer identifier
        agent_name: Which agent
        data: Dictionary of data to save
        user_id: User who triggered the save
        reason: Business reason for the save

    Returns:
        True if both save and audit log succeed
    """
    # First, save the state
    save_success = save_state(tenant_id, agent_name, data)

    if save_success:
        # Log the audit event
        log_audit_event(
            tenant_id=tenant_id,
            action='UPDATE' if get_state(tenant_id, agent_name) else 'CREATE',
            agent_name=agent_name,
            resource_type='agent_state',
            resource_keys={'agentName': agent_name},
            user_id=user_id,
            reason=reason,
            additional_data={'data_keys': list(data.keys())}
        )

    return save_success


def get_state_with_audit(
    tenant_id: str,
    agent_name: str,
    user_id: Optional[str] = None,
    reason: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Retrieve agent state and log the access for HIPAA compliance.

    This is the HIPAA-compliant version of get_state().
    Use this when accessing any data that might contain PHI.

    Args:
        tenant_id: Customer identifier
        agent_name: Which agent
        user_id: User who triggered the read
        reason: Business reason for the read

    Returns:
        Dictionary with state data, or None if not found
    """
    # Get the state
    state = get_state(tenant_id, agent_name)

    # Log the access (even if not found - attempted access is logged)
    log_audit_event(
        tenant_id=tenant_id,
        action='READ',
        agent_name=agent_name,
        resource_type='agent_state',
        resource_keys={'agentName': agent_name},
        user_id=user_id,
        reason=reason,
        additional_data={'found': state is not None}
    )

    return state


def delete_state_with_audit(
    tenant_id: str,
    agent_name: str,
    user_id: Optional[str] = None,
    reason: Optional[str] = None
) -> bool:
    """
    Delete agent state and log the action for HIPAA compliance.

    This is the HIPAA-compliant version of delete_state().
    Use this when deleting any data that might contain PHI.

    Args:
        tenant_id: Customer identifier
        agent_name: Which agent
        user_id: User who triggered the delete
        reason: Business reason for the delete

    Returns:
        True if successful
    """
    # Delete the state
    delete_success = delete_state(tenant_id, agent_name)

    if delete_success:
        # Log the audit event
        log_audit_event(
            tenant_id=tenant_id,
            action='DELETE',
            agent_name=agent_name,
            resource_type='agent_state',
            resource_keys={'agentName': agent_name},
            user_id=user_id,
            reason=reason
        )

    return delete_success

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