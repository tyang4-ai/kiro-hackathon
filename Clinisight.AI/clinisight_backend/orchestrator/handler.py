"""
Orchestrator - Central Event Router
====================================

PURPOSE:
The orchestrator is the "traffic controller" - it receives ALL incoming events
and routes them to the appropriate agent.

WHY NEEDED?
- Single entry point (one API Gateway endpoint)
- Central logging and error handling
- Easy to add new agents (just add routing rules)
- Loose coupling (agents don't know about each other)

FLOW:
1. API Gateway receives webhook from Jira/Confluence
2. Calls orchestrator Lambda
3. Orchestrator analyzes event type
4. Invokes appropriate agent Lambda
5. Returns result to API Gateway
"""

import json
import os
from typing import Dict, Any, Optional
import boto3

# Import our shared utilities
from shared.logger import Logger
from shared.security import validate_tenant_id, sanitize_for_logging

# ============================================
# INITIALIZE AWS CLIENTS
# ============================================

# Lambda client - for invoking other Lambdas
lambda_client = boto3.client('lambda')

# Get current AWS region from environment
REGION = os.environ.get('AWS_REGION', 'us-east-1')
STAGE = os.environ.get('STAGE', 'dev')

# Build Lambda function names
# Format: clinisight-backend-{stage}-{agent}
# Example: clinisight-backend-dev-tasksmith
SERVICE_NAME = 'clinisight-backend'


# ============================================
# LAMBDA HANDLER (Main Entry Point)
# ============================================
def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Orchestrator Lambda handler.
    
    This function receives ALL incoming events and routes them.
    
    Event Sources:
    1. API Gateway (webhooks from Forge)
    2. EventBridge (scheduled triggers)
    3. Manual invocations (testing)
    
    Args:
        event: Event data (format varies by source)
        context: AWS Lambda context
    
    Returns:
        API Gateway response format:
        {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": "{...json...}"
        }
    """
    
    # ========================================
    # STEP 0: Handle CLI invocation (event might be JSON string)
    # ========================================
    if isinstance(event, str):
        try:
            event = json.loads(event)
        except json.JSONDecodeError:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({
                    'error': 'Invalid JSON in event',
                    'orchestrator': 'error'
                })
            }
    
    # ========================================
    # STEP 1: Parse Event Source
    # ========================================
    
    # Determine where event came from
    event_source = determine_event_source(event)
    
    print(f"📥 Event received from: {event_source}")
    print(f"📋 Raw event: {sanitize_for_logging(event)}")
    
    # ========================================
    # STEP 2: Extract Event Data
    # ========================================
    
    if event_source == 'api_gateway':
        # Event from API Gateway (webhook)
        # Body is JSON string, need to parse it
        body = json.loads(event.get('body', '{}'))
        event_type = body.get('eventType', 'UNKNOWN')
        tenant_id = body.get('tenantId', 'unknown')
        event_data = body.get('data', {})
        
    elif event_source == 'eventbridge':
        # Event from EventBridge (scheduled)
        # Event is already parsed
        event_type = event.get('eventType', 'UNKNOWN')
        tenant_id = event.get('tenantId', 'unknown')
        event_data = event.get('data', {})
        
    else:
        # Direct invocation (testing)
        event_type = event.get('eventType', 'UNKNOWN')
        tenant_id = event.get('tenantId', 'unknown')
        event_data = event.get('data', {})
    
    # ========================================
    # STEP 3: Validate Tenant
    # ========================================
    
    if not validate_tenant_id(tenant_id):
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'error': 'Invalid or missing tenantId',
                'provided': tenant_id
            })
        }
    
    # ========================================
    # STEP 4: Initialize Logger
    # ========================================
    
    log = Logger("Orchestrator", tenant_id)
    
    log.info("Orchestrator invoked", {
        "source": event_source,
        "event_type": event_type
    })
    
    # ========================================
    # STEP 5: Route to Appropriate Agent
    # ========================================
    
    try:
        result = route_event(event_type, tenant_id, event_data, log)
        
        log.info("Orchestrator completed", {
            "event_type": event_type,
            "agent_invoked": result.get('agent', 'none')
        })
        
        # Return success
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps(result)
        }
        
    except Exception as e:
        log.error("Orchestrator failed", error=e, data={
            "event_type": event_type
        })
        
        # Return error
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'error': str(e),
                'event_type': event_type
            })
        }


# ============================================
# EVENT SOURCE DETECTION
# ============================================
def determine_event_source(event: Dict[str, Any]) -> str:
    """
    Figure out where the event came from.
    
    Different sources have different event structures:
    - API Gateway: has 'httpMethod', 'headers', 'body'
    - EventBridge: has 'source', 'detail-type'
    - Direct: has our custom fields
    
    Args:
        event: The Lambda event
    
    Returns:
        'api_gateway', 'eventbridge', or 'direct'
    """
    
    # Check for API Gateway markers
    if 'httpMethod' in event and 'headers' in event:
        return 'api_gateway'
    
    # Check for EventBridge markers
    if 'source' in event and 'detail-type' in event:
        return 'eventbridge'
    
    # Otherwise, direct invocation
    return 'direct'


# ============================================
# EVENT ROUTING LOGIC
# ============================================
def route_event(
    event_type: str,
    tenant_id: str,
    event_data: Dict[str, Any],
    log: Logger
) -> Dict[str, Any]:
    """
    Route event to the appropriate agent.
    
    This is the "decision tree" - based on event_type, call the right agent.
    
    Args:
        event_type: Type of event (e.g., "EPIC_CREATED", "SCHEDULED_CHECK")
        tenant_id: Customer identifier
        event_data: Additional event data
        log: Logger instance
    
    Returns:
        Agent's result dictionary
    
    Raises:
        ValueError: If event_type is unknown
    """
    
    log.info("Routing event", {
        "event_type": event_type,
        "has_data": bool(event_data)
    })
    
    # ========================================
    # ROUTING RULES
    # ========================================
    
    if event_type == 'EPIC_CREATED' or event_type == 'JIRA_EPIC_CREATED':
        # Epic created in Jira → TaskSmith
        log.info("Routing to TaskSmith")
        
        # Extract epic details from event_data
        epic_key = event_data.get('epicKey') or event_data.get('issue', {}).get('key')
        epic_summary = event_data.get('epicSummary') or event_data.get('issue', {}).get('fields', {}).get('summary')
        
        # Build payload for TaskSmith
        payload = {
            'tenantId': tenant_id,
            'epicKey': epic_key,
            'epicSummary': epic_summary
        }
        
        # Invoke TaskSmith Lambda
        result = invoke_agent('tasksmith', payload, log)
        return result
    
    elif event_type == 'SCHEDULED_CHECK' or event_type == 'CARETRACK_CHECK':
        # Scheduled workflow check → CareTrack
        log.info("Routing to CareTrack")
        
        # CareTrack doesn't need much data - just tenant
        payload = {
            'tenantId': tenant_id
        }
        
        # Invoke CareTrack Lambda (when we build it)
        # For now, return placeholder
        return {
            'agent': 'CareTrack',
            'status': 'not_implemented',
            'message': 'CareTrack agent coming soon!'
        }
    
    elif event_type == 'ROVO_INSIGHTS':
        # Rovo requesting insights → Get all agent states
        log.info("Fetching Rovo insights")
        
        # Get insights from all agents
        insights = get_rovo_insights(tenant_id, log)
        return insights
    
    else:
        # Unknown event type
        log.warning("Unknown event type", {
            "event_type": event_type
        })
        
        raise ValueError(f"Unknown event type: {event_type}")


# ============================================
# AGENT INVOCATION
# ============================================
def invoke_agent(
    agent_name: str,
    payload: Dict[str, Any],
    log: Logger
) -> Dict[str, Any]:
    """
    Invoke another Lambda function (agent).
    
    This is how orchestrator calls agents - using AWS Lambda's invoke API.
    
    Args:
        agent_name: Name of agent (e.g., 'tasksmith')
        payload: Data to pass to agent
        log: Logger instance
    
    Returns:
        Agent's response (parsed from JSON)
    
    How it works:
    1. Build full Lambda function name
    2. Call lambda_client.invoke()
    3. Parse response
    4. Return result
    """
    
    # Build Lambda function name
    # Format: clinisight-backend-{stage}-{agent}
    function_name = f"{SERVICE_NAME}-{STAGE}-{agent_name}"
    
    log.info("Invoking agent Lambda", {
        "agent": agent_name,
        "function_name": function_name
    })
    
    try:
        # Invoke the Lambda function
        # InvocationType='RequestResponse' = synchronous (wait for result)
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='RequestResponse',  # Synchronous
            Payload=json.dumps(payload)
        )
        
        # Read response
        response_payload = response['Payload'].read()
        
        # Parse JSON
        result = json.loads(response_payload)
        
        # Lambda returns API Gateway format: {"statusCode": 200, "body": "{...}"}
        # Extract the body
        if 'body' in result:
            # Parse body if it's a string
            if isinstance(result['body'], str):
                body = json.loads(result['body'])
            else:
                body = result['body']
            
            return body
        else:
            # Direct response (testing)
            return result
        
    except Exception as e:
        log.error("Failed to invoke agent", error=e, data={
            "agent": agent_name,
            "function_name": function_name
        })
        
        # Return error
        return {
            'agent': agent_name,
            'status': 'error',
            'error': str(e)
        }


# ============================================
# ROVO INSIGHTS (Get All Agent States)
# ============================================
def get_rovo_insights(tenant_id: str, log: Logger) -> Dict[str, Any]:
    """
    Get insights from all agents for Rovo dashboard.
    
    This queries DynamoDB for all agent states and returns a summary.
    
    Args:
        tenant_id: Customer identifier
        log: Logger instance
    
    Returns:
        Dictionary with insights from all agents
    """
    
    from shared.database import get_all_agent_states
    
    log.info("Fetching all agent states for Rovo")
    
    # Get all states
    all_states = get_all_agent_states(tenant_id)
    
    # Build insights
    insights = {
        'tenant_id': tenant_id,
        'agents': {}
    }
    
    # Process each agent's state
    for agent_name, state in all_states.items():
        if agent_name == 'TaskSmith':
            insights['agents']['TaskSmith'] = {
                'status': 'active',
                'summary': f"Processed {state.get('epic_key', 'unknown epic')}, created {state.get('subtasks_created', 0)} subtasks"
            }
        else:
            insights['agents'][agent_name] = {
                'status': 'active',
                'summary': 'Agent data available'
            }
    
    # Add placeholder for agents we haven't built yet
    for agent_name in ['CareTrack', 'DealFlow', 'MindMesh', 'RoadmapSmith']:
        if agent_name not in insights['agents']:
            insights['agents'][agent_name] = {
                'status': 'not_implemented',
                'summary': 'Coming soon'
            }
    
    return insights


# ============================================
# UNDERSTANDING: Why Orchestrator?
# ============================================
"""
Why not have API Gateway call agents directly?

1. SINGLE ENTRY POINT
   - One webhook URL for Forge
   - Easy to secure (one endpoint to protect)
   - Central logging

2. LOOSE COUPLING
   - Agents don't know about API Gateway
   - Can change API format without changing agents
   - Can add new event sources easily

3. ROUTING LOGIC
   - Complex routing in one place
   - Easy to add new agents
   - Can route to multiple agents if needed

4. ERROR HANDLING
   - Centralized error handling
   - Consistent response format
   - Better observability

This is event-driven architecture best practice!
"""


# ============================================
# TESTING LOCALLY
# ============================================
if __name__ == '__main__':
    """
    Test orchestrator locally.
    Run with: python handler.py
    """
    
    print("Testing Orchestrator...")
    print()
    
    # Test event: Epic created
    test_event = {
        'eventType': 'EPIC_CREATED',
        'tenantId': 'test-tenant',
        'data': {
            'epicKey': 'HC-100',
            'epicSummary': 'Implement Patient Portal'
        }
    }
    
    result = lambda_handler(test_event, None)
    
    print(f"Status Code: {result['statusCode']}")
    print(f"Response: {result['body']}")