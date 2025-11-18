"""
Structured Logger - CloudWatch-Friendly Logging
================================================

Why structured logging?
- Plain print() is hard to search in CloudWatch
- JSON logs are machine-readable
- Can filter/search by specific fields
- Consistent format across all agents

What it provides:
- log_info() - Normal operations
- log_warning() - Potential issues
- log_error() - Actual errors
- All automatically include: timestamp, agent name, tenant
"""

import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional


# ============================================
# LOG FUNCTIONS
# ============================================

def log_info(agent_name: str, tenant_id: str, message: str, data: Optional[Dict[str, Any]] = None):
    """
    Log informational message.
    
    Args:
        agent_name: Which agent is logging (e.g., "TaskSmith")
        tenant_id: Which customer (e.g., "acme-health")
        message: Human-readable message
        data: Optional dictionary with additional context
    
    Example:
        log_info("TaskSmith", "acme", "Created subtasks", {
            "epic_key": "HC-100",
            "count": 5
        })
    
    Output in CloudWatch:
        {
          "timestamp": "2025-01-15T10:30:00Z",
          "level": "INFO",
          "agent": "TaskSmith",
          "tenant": "acme",
          "message": "Created subtasks",
          "data": {"epic_key": "HC-100", "count": 5}
        }
    
    Why this format?
        - CloudWatch Insights can parse JSON
        - Can query: fields @timestamp, message | filter agent="TaskSmith"
        - Can aggregate: stats count() by tenant
    """
    log_entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'level': 'INFO',
        'agent': agent_name,
        'tenant': tenant_id,
        'message': message
    }
    
    # Add optional data if provided
    if data:
        log_entry['data'] = data
    
    # Print as JSON (CloudWatch captures stdout)
    print(json.dumps(log_entry))


def log_warning(agent_name: str, tenant_id: str, message: str, data: Optional[Dict[str, Any]] = None):
    """
    Log warning message - something unusual but not broken.
    
    Example:
        log_warning("CareTrack", "acme", "Issue approaching SLA limit", {
            "issue_key": "HC-45",
            "days_in_status": 6,
            "sla_limit": 7
        })
    """
    log_entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'level': 'WARNING',
        'agent': agent_name,
        'tenant': tenant_id,
        'message': message
    }
    
    if data:
        log_entry['data'] = data
    
    print(json.dumps(log_entry))


def log_error(agent_name: str, tenant_id: str, message: str, error: Optional[Exception] = None, data: Optional[Dict[str, Any]] = None):
    """
    Log error message - something broke.
    
    Args:
        agent_name: Which agent
        tenant_id: Which customer
        message: What went wrong
        error: Optional Exception object
        data: Optional context data
    
    Example:
        try:
            create_jira_issue()
        except Exception as e:
            log_error("TaskSmith", "acme", "Failed to create issue", error=e, data={
                "epic_key": "HC-100"
            })
    """
    log_entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'level': 'ERROR',
        'agent': agent_name,
        'tenant': tenant_id,
        'message': message
    }
    
    # Include error details if provided
    if error:
        log_entry['error'] = {
            'type': type(error).__name__,
            'message': str(error)
        }
    
    if data:
        log_entry['data'] = data
    
    print(json.dumps(log_entry))


# ============================================
# CLASS-BASED LOGGER (Optional, Cleaner)
# ============================================
class Logger:
    """
    Class-based logger - set agent and tenant once, use everywhere.
    
    Why useful?
        Instead of passing agent_name and tenant_id to every log call,
        set them once when creating the logger.
    
    Example:
        # In your Lambda handler
        log = Logger("TaskSmith", "acme-health")
        
        # Then throughout your code
        log.info("Starting epic decomposition", {"epic_key": "HC-100"})
        log.warning("Epic has no description")
        log.error("Failed to call Jira API", error=e)
    """
    
    def __init__(self, agent_name: str, tenant_id: str):
        """Initialize logger with agent and tenant."""
        self.agent_name = agent_name
        self.tenant_id = tenant_id
    
    def info(self, message: str, data: Optional[Dict[str, Any]] = None):
        """Log info message."""
        log_info(self.agent_name, self.tenant_id, message, data)
    
    def warning(self, message: str, data: Optional[Dict[str, Any]] = None):
        """Log warning message."""
        log_warning(self.agent_name, self.tenant_id, message, data)
    
    def error(self, message: str, error: Optional[Exception] = None, data: Optional[Dict[str, Any]] = None):
        """Log error message."""
        log_error(self.agent_name, self.tenant_id, message, error, data)


# ============================================
# CLOUDWATCH INSIGHTS QUERIES
# ============================================
"""
With structured logs, you can query in CloudWatch Insights:

1. Find all errors for a specific agent:
   fields @timestamp, message, error
   | filter level="ERROR" and agent="TaskSmith"
   | sort @timestamp desc

2. Count operations by tenant:
   stats count() by tenant
   | sort count desc

3. Find slow operations:
   fields @timestamp, agent, message, data.duration_ms
   | filter data.duration_ms > 5000
   | sort data.duration_ms desc

4. Find specific epic operations:
   fields @timestamp, agent, message, data
   | filter data.epic_key="HC-100"

This is why structured logging matters!
"""


# ============================================
# TESTING
# ============================================
if __name__ == '__main__':
    print("Testing logger...")
    print()
    
    # Test function-based logging
    log_info("TestAgent", "test-tenant", "Test info message", {"key": "value"})
    log_warning("TestAgent", "test-tenant", "Test warning")
    
    try:
        raise ValueError("Test error")
    except Exception as e:
        log_error("TestAgent", "test-tenant", "Test error occurred", error=e)
    
    print()
    print("Testing class-based logger...")
    print()
    
    # Test class-based logging
    log = Logger("TestAgent", "test-tenant")
    log.info("Class-based info")
    log.warning("Class-based warning")
    log.error("Class-based error")