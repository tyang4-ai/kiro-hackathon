"""
Orchestrator - Central Event Router (WITH SENTRY)
==================================================

CHANGES MADE:
- Added Sentry initialization
- Added error capture to Sentry
- Added performance monitoring spans
- All errors now tracked to Sentry

To use this file:
1. Add SENTRY_DSN to serverless.yml environment
2. Add sentry-sdk==1.40.0 to requirements.txt
3. Replace handler.py with this file
"""

import json
import os
from typing import Dict, Any, Optional
import boto3
import sentry_sdk

# Initialize Sentry FIRST (before other imports)
from sentry_init import init_sentry
init_sentry()

# Import our shared utilities
from shared.logger import Logger
from shared.security import validate_tenant_id, sanitize_for_logging

# ============================================
# INITIALIZE AWS CLIENTS
# ============================================

lambda_client = boto3.client('lambda')
REGION = os.environ.get('AWS_REGION', 'us-east-1')
STAGE = os.environ.get('STAGE', 'dev')
SERVICE_NAME = 'clinisight-backend'


# ============================================
# LAMBDA HANDLER (Main Entry Point)
# ============================================
def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Orchestrator Lambda handler with Sentry integration."""

    # Set Sentry context
    sentry_sdk.set_tag("lambda_function", "orchestrator")
    sentry_sdk.set_tag("stage", STAGE)

    # ========================================
    # STEP 0: Handle CLI invocation
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
    event_source = determine_event_source(event)

    print(f"📥 Event received from: {event_source}")
    print(f"📋 Raw event: {sanitize_for_logging(event)}")

    # ========================================
    # STEP 2: Extract Event Data
    # ========================================
    if event_source == 'api_gateway':
        http_method = event.get('httpMethod', 'POST')
        path = event.get('path', '')

        # Handle GET requests (e.g., /rovo/insights)
        if http_method == 'GET':
            query_params = event.get('queryStringParameters') or {}
            tenant_id = query_params.get('tenantId', 'demo-tenant')

            # Determine event type from path
            if '/rovo/insights' in path:
                event_type = 'ROVO_INSIGHTS'
            else:
                event_type = 'UNKNOWN'

            event_data = {}
        else:
            # Handle POST requests
            body = json.loads(event.get('body') or '{}')
            event_type = body.get('eventType', 'UNKNOWN')
            tenant_id = body.get('tenantId', 'unknown')
            event_data = body.get('data', {})

    elif event_source == 'eventbridge':
        event_type = event.get('eventType', 'UNKNOWN')
        tenant_id = event.get('tenantId', 'unknown')
        event_data = event.get('data', {})

    else:
        event_type = event.get('eventType', 'UNKNOWN')
        tenant_id = event.get('tenantId', 'unknown')
        event_data = event.get('data', {})

    # Set Sentry user context
    sentry_sdk.set_user({"id": tenant_id})
    sentry_sdk.set_tag("event_type", event_type)

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
        # Capture to Sentry with full context
        sentry_sdk.capture_exception(e)
        sentry_sdk.capture_message(
            f"Orchestrator failed for event type: {event_type}",
            level="error"
        )

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
    """Figure out where the event came from."""

    if 'httpMethod' in event and 'headers' in event:
        return 'api_gateway'

    if 'source' in event and 'detail-type' in event:
        return 'eventbridge'

    return 'direct'


# ============================================
# EVENT ROUTING LOGIC (WITH SENTRY SPANS)
# ============================================
def route_event(
    event_type: str,
    tenant_id: str,
    event_data: Dict[str, Any],
    log: Logger
) -> Dict[str, Any]:
    """Route event to the appropriate agent with performance tracking."""

    # Start performance span
    with sentry_sdk.start_span(op="orchestrator.route", description=f"Route {event_type}"):
        log.info("Routing event", {
            "event_type": event_type,
            "has_data": bool(event_data)
        })

        # ========================================
        # ROUTING RULES
        # ========================================
        if event_type == 'EPIC_CREATED' or event_type == 'JIRA_EPIC_CREATED':
            log.info("Routing to TaskSmith")

            epic_key = event_data.get('epicKey') or event_data.get('issue', {}).get('key')
            epic_summary = event_data.get('epicSummary') or event_data.get('issue', {}).get('fields', {}).get('summary')

            payload = {
                'tenantId': tenant_id,
                'epicKey': epic_key,
                'epicSummary': epic_summary
            }

            result = invoke_agent('tasksmith', payload, log)
            return result

        elif event_type == 'SCHEDULED_CHECK' or event_type == 'CARETRACK_CHECK':
            log.info("Routing to CareTrack")

            payload = {
                'tenantId': tenant_id
            }

            # Placeholder for CareTrack
            return {
                'agent': 'CareTrack',
                'status': 'not_implemented',
                'message': 'CareTrack agent coming soon!'
            }

        elif event_type == 'ROVO_INSIGHTS':
            log.info("Fetching Rovo insights")

            insights = get_rovo_insights(tenant_id, log)
            return insights

        else:
            log.warning("Unknown event type", {
                "event_type": event_type
            })

            raise ValueError(f"Unknown event type: {event_type}")


# ============================================
# AGENT INVOCATION (WITH SENTRY TRACKING)
# ============================================
def invoke_agent(
    agent_name: str,
    payload: Dict[str, Any],
    log: Logger
) -> Dict[str, Any]:
    """Invoke another Lambda function with Sentry performance tracking."""

    function_name = f"{SERVICE_NAME}-{STAGE}-{agent_name}"

    log.info("Invoking agent Lambda", {
        "agent": agent_name,
        "function_name": function_name
    })

    # Track Lambda invocation performance
    with sentry_sdk.start_span(op="lambda.invoke", description=f"Invoke {agent_name}"):
        try:
            response = lambda_client.invoke(
                FunctionName=function_name,
                InvocationType='RequestResponse',
                Payload=json.dumps(payload)
            )

            response_payload = response['Payload'].read()
            result = json.loads(response_payload)

            if 'body' in result:
                if isinstance(result['body'], str):
                    body = json.loads(result['body'])
                else:
                    body = result['body']

                return body
            else:
                return result

        except Exception as e:
            # Capture to Sentry with agent context
            sentry_sdk.capture_exception(e)

            log.error("Failed to invoke agent", error=e, data={
                "agent": agent_name,
                "function_name": function_name
            })

            return {
                'agent': agent_name,
                'status': 'error',
                'error': str(e)
            }


# ============================================
# ROVO INSIGHTS
# ============================================
def get_rovo_insights(tenant_id: str, log: Logger) -> Dict[str, Any]:
    """Get insights from all agents for Rovo dashboard."""

    from shared.database import get_all_agent_states

    log.info("Fetching all agent states for Rovo")

    all_states = get_all_agent_states(tenant_id)

    insights = {
        'tenant_id': tenant_id,
        'agents': {}
    }

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

    for agent_name in ['CareTrack', 'DealFlow', 'MindMesh', 'RoadmapSmith']:
        if agent_name not in insights['agents']:
            insights['agents'][agent_name] = {
                'status': 'not_implemented',
                'summary': 'Coming soon'
            }

    return insights


# ============================================
# TESTING LOCALLY
# ============================================
if __name__ == '__main__':
    print("Testing Orchestrator with Sentry...")
    print()

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
