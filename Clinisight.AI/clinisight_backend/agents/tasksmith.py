"""
TaskSmith Agent - Epic Decomposition
=====================================

PURPOSE:
When a project manager creates an Epic in Jira (like "Implement Patient Portal"),
TaskSmith automatically breaks it down into smaller, actionable subtasks.

EXAMPLE FLOW:
1. User creates Epic "Implement Patient Portal" (HC-100)
2. Orchestrator calls this Lambda
3. TaskSmith analyzes the epic
4. Creates 5 subtasks: HC-101, HC-102, HC-103, HC-104, HC-105
5. Saves what it did to DynamoDB
6. Returns success

WHY THIS MATTERS:
- Saves project managers hours of planning
- Ensures consistent task breakdown
- Nothing gets forgotten
"""

import json
from typing import Dict, Any, List

# Import our shared utilities (we built these!)
from shared.logger import Logger
from shared.database import save_state, get_state
from shared.security import validate_tenant_id, sanitize_for_logging, check_for_pii


# ============================================
# LAMBDA HANDLER (AWS Entry Point)
# ============================================
def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    This is THE function AWS calls when Lambda is triggered.
    
    AWS Lambda contract:
    - Input: event (dict with data) + context (runtime info)
    - Output: dict with statusCode and body
    
    Args:
        event: Dictionary with event data
               Example: {
                   "tenantId": "acme-health",
                   "epicKey": "HC-100",
                   "epicSummary": "Implement Patient Portal"
               }
        
        context: AWS runtime context (has request ID, memory limit, etc.)
                 We don't use this much, but AWS requires it
    
    Returns:
        Dictionary in API Gateway format:
        {
            "statusCode": 200,
            "body": "{...json...}"
        }
    
    This format is required for API Gateway integration.
    """
    
    # ========================================
    # STEP 1: Parse and Validate Event
    # ========================================
    
    # Handle CLI invocation (event might be JSON string)
    if isinstance(event, str):
        try:
            event = json.loads(event)
        except json.JSONDecodeError:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Invalid JSON in event',
                    'agent': 'TaskSmith'
                })
            }
    
    # Extract required fields
    tenant_id = event.get('tenantId')
    epic_key = event.get('epicKey')  # e.g., "HC-100"
    epic_summary = event.get('epicSummary', '')  # e.g., "Implement Patient Portal"
    
    # Validate tenant ID (security!)
    if not tenant_id or not validate_tenant_id(tenant_id):
        return {
            'statusCode': 400,
            'body': json.dumps({
                'error': 'Invalid or missing tenantId',
                'agent': 'TaskSmith'
            })
        }
    
    # Validate epic key
    if not epic_key:
        return {
            'statusCode': 400,
            'body': json.dumps({
                'error': 'Missing epicKey',
                'agent': 'TaskSmith'
            })
        }
    
    # ========================================
    # STEP 2: Initialize Logger
    # ========================================
    
    # Create logger for this execution
    # Now we can just call log.info(), log.error(), etc.
    log = Logger("TaskSmith", tenant_id)
    
    # Log that we started (this goes to CloudWatch)
    log.info("TaskSmith invoked", {
        "epic_key": epic_key,
        "epic_summary": epic_summary
    })
    
    # ========================================
    # STEP 3: Run the Agent Logic
    # ========================================
    
    try:
        # Call our main function (defined below)
        result = process_epic(tenant_id, epic_key, epic_summary, log)
        
        # Log success
        log.info("TaskSmith completed successfully", {
            "epic_key": epic_key,
            "subtasks_created": result['subtasks_created']
        })
        
        # Return success response
        return {
            'statusCode': 200,
            'body': json.dumps(result)
        }
        
    except Exception as e:
        # Something went wrong - log the error
        log.error("TaskSmith failed", error=e, data={
            "epic_key": epic_key
        })
        
        # Return error response
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'agent': 'TaskSmith',
                'epic_key': epic_key
            })
        }


# ============================================
# MAIN BUSINESS LOGIC
# ============================================
def process_epic(
    tenant_id: str, 
    epic_key: str, 
    epic_summary: str, 
    log: Logger
) -> Dict[str, Any]:
    """
    Main TaskSmith logic - decomposes epic into subtasks.
    
    This function is separate from lambda_handler so we can:
    - Test it independently
    - Keep lambda_handler focused on AWS mechanics
    - Reuse logic if needed
    
    Args:
        tenant_id: Customer identifier
        epic_key: Jira epic key (e.g., "HC-100")
        epic_summary: Epic title (e.g., "Implement Patient Portal")
        log: Logger instance for this execution
    
    Returns:
        Dictionary with results:
        {
            "agent": "TaskSmith",
            "epic_key": "HC-100",
            "subtasks_created": 5,
            "subtasks": [...]
        }
    """
    
    # ========================================
    # STEP 1: Check if we've processed this epic before
    # ========================================
    
    log.info("Checking if epic was already processed", {
        "epic_key": epic_key
    })
    
    # Get previous state from DynamoDB
    previous_state = get_state(tenant_id, "TaskSmith")
    
    if previous_state and previous_state.get('epic_key') == epic_key:
        # We already processed this epic!
        log.warning("Epic already processed, returning cached result", {
            "epic_key": epic_key,
            "previous_subtasks": previous_state.get('subtasks_created', 0)
        })
        
        return {
            "agent": "TaskSmith",
            "epic_key": epic_key,
            "subtasks_created": previous_state.get('subtasks_created', 0),
            "subtasks": previous_state.get('subtasks', []),
            "cached": True
        }
    
    # ========================================
    # STEP 2: Analyze Epic and Generate Subtasks
    # ========================================
    
    log.info("Generating subtasks", {
        "epic_key": epic_key,
        "epic_summary": epic_summary
    })
    
    # Call our decomposition function (defined below)
    subtasks = decompose_epic(epic_summary)
    
    log.info("Subtasks generated", {
        "count": len(subtasks)
    })
    
    # ========================================
    # STEP 3: Save State to DynamoDB
    # ========================================
    
    # Build state data
    state_data = {
        "epic_key": epic_key,
        "epic_summary": epic_summary,
        "subtasks_created": len(subtasks),
        "subtasks": subtasks,
        "timestamp": "2025-11-04T06:00:00Z"  # In production, use: datetime.now(timezone.utc).isoformat()
    }
    
    # Check for PII (shouldn't be any, but let's be safe)
    pii_warnings = check_for_pii(state_data)
    if pii_warnings:
        log.error("Attempted to save PII!", data={
            "warnings": pii_warnings
        })
        raise ValueError("Cannot save state - contains PII")
    
    # Save to DynamoDB
    success = save_state(tenant_id, "TaskSmith", state_data)
    
    if not success:
        log.warning("Failed to save state to DynamoDB")
    
    # ========================================
    # STEP 4: Return Results
    # ========================================
    
    return {
        "agent": "TaskSmith",
        "status": "success",
        "epic_key": epic_key,
        "subtasks_created": len(subtasks),
        "subtasks": subtasks
    }


# ============================================
# EPIC DECOMPOSITION LOGIC
# ============================================
def decompose_epic(epic_summary: str) -> List[Dict[str, str]]:
    """
    Break down an epic into subtasks.
    
    IN PRODUCTION, this would:
    - Call Claude API or GPT-4
    - Use advanced NLP
    - Learn from past decompositions
    
    FOR LEARNING, we use:
    - Simple keyword matching
    - Predefined templates
    - Rule-based logic
    
    This keeps it simple while you learn the architecture.
    Once you understand Lambda/DynamoDB/etc., upgrading this to use
    real AI is just changing this one function!
    
    Args:
        epic_summary: Title of the epic
    
    Returns:
        List of subtask dictionaries:
        [
            {"title": "Design authentication system", "description": "..."},
            {"title": "Build patient dashboard", "description": "..."},
            ...
        ]
    """
    
    # Convert to lowercase for matching
    summary_lower = epic_summary.lower()
    
    # ========================================
    # TEMPLATE 1: Patient Portal
    # ========================================
    if 'portal' in summary_lower or 'patient portal' in summary_lower:
        return [
            {
                "title": "Design user authentication and authorization system",
                "description": "Implement secure login with multi-factor authentication for patient access. Include password reset flow and session management."
            },
            {
                "title": "Build patient dashboard UI",
                "description": "Create responsive dashboard showing appointments, test results, and messages. Must be mobile-friendly and WCAG 2.1 compliant."
            },
            {
                "title": "Integrate with Electronic Health Record (EHR) system",
                "description": "Establish secure API connection to retrieve patient data. Implement proper error handling and data validation."
            },
            {
                "title": "Implement secure messaging between patients and providers",
                "description": "Build HIPAA-compliant messaging with end-to-end encryption. Include read receipts and attachment support."
            },
            {
                "title": "Add appointment scheduling functionality",
                "description": "Allow patients to view provider availability and book appointments. Include calendar integration and reminder notifications."
            }
        ]
    
    # ========================================
    # TEMPLATE 2: Compliance / HIPAA
    # ========================================
    elif 'compliance' in summary_lower or 'hipaa' in summary_lower:
        return [
            {
                "title": "Conduct HIPAA compliance audit",
                "description": "Review current systems and processes against HIPAA requirements. Document gaps and create remediation plan."
            },
            {
                "title": "Implement access controls and audit logging",
                "description": "Ensure all PHI access is logged and monitored. Set up role-based access control (RBAC) and regular access reviews."
            },
            {
                "title": "Update privacy policies and consent forms",
                "description": "Revise patient-facing documentation to comply with current regulations. Get legal review and approval."
            },
            {
                "title": "Conduct staff training on HIPAA requirements",
                "description": "Educate team on privacy and security best practices. Include annual refresher training and testing."
            }
        ]
    
    # ========================================
    # TEMPLATE 3: Integration
    # ========================================
    elif 'integration' in summary_lower or 'integrate' in summary_lower:
        return [
            {
                "title": "Document API requirements and specifications",
                "description": "Define data formats, authentication methods, and endpoints. Create API documentation and test cases."
            },
            {
                "title": "Develop integration middleware layer",
                "description": "Build service layer to connect systems. Implement retry logic, error handling, and logging."
            },
            {
                "title": "Implement data transformation and validation",
                "description": "Ensure data quality and consistency between systems. Create mapping rules and validation logic."
            },
            {
                "title": "Test integration end-to-end",
                "description": "Verify data flows correctly in all scenarios. Include edge cases and error conditions."
            },
            {
                "title": "Deploy to production and monitor",
                "description": "Roll out integration with monitoring and alerting. Create runbook for common issues."
            }
        ]
    
    # ========================================
    # DEFAULT TEMPLATE (Generic)
    # ========================================
    else:
        return [
            {
                "title": f"Research and design solution for: {epic_summary}",
                "description": "Investigate requirements, review existing solutions, and create technical design document."
            },
            {
                "title": f"Implement core functionality for: {epic_summary}",
                "description": "Build the main features according to technical design. Include unit tests."
            },
            {
                "title": f"Test and validate: {epic_summary}",
                "description": "Create comprehensive test suite and ensure quality standards are met."
            },
            {
                "title": f"Deploy and document: {epic_summary}",
                "description": "Release to production and create user documentation. Set up monitoring."
            }
        ]


# ============================================
# UNDERSTANDING: Why This Structure?
# ============================================
"""
We separated the code into layers:

1. lambda_handler() - AWS mechanics
   - Parse event
   - Validate inputs
   - Return API Gateway format
   - Catch all errors

2. process_epic() - Business logic
   - Check cache
   - Generate subtasks
   - Save state
   - Return results

3. decompose_epic() - Domain knowledge
   - Epic templates
   - Decomposition rules
   - Easy to update/improve

WHY?
- Testability: Can test process_epic() without AWS
- Clarity: Each function has one job
- Maintainability: Change decomposition logic without touching Lambda handler
- Reusability: Could call process_epic() from multiple places

This is professional code structure!
"""


# ============================================
# TESTING LOCALLY (Optional)
# ============================================
if __name__ == '__main__':
    """
    This runs only if you execute: python tasksmith.py
    Won't run when AWS invokes the Lambda.
    
    Useful for testing logic locally before deploying!
    """
    
    print("Testing TaskSmith locally...")
    print()
    
    # Test event
    test_event = {
        "tenantId": "test-tenant",
        "epicKey": "HC-100",
        "epicSummary": "Implement Patient Portal"
    }
    
    # Call handler
    result = lambda_handler(test_event, None)
    
    # Print result
    print(f"Status Code: {result['statusCode']}")
    print(f"Response: {result['body']}")