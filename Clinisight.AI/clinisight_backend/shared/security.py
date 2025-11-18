"""
Security Utilities - Data Sanitization & PII Protection
========================================================

CRITICAL FOR HEALTHCARE:
We NEVER store or log PII (Personally Identifiable Information) or PHI (Protected Health Information).

Why this matters:
- HIPAA compliance requires protecting patient data
- Logs go to CloudWatch (could be accessed by many people)
- Even accidental logging of PII is a violation

What we store:
✅ Jira issue IDs (HC-123)
✅ Metadata (timestamps, counts, status)
✅ Aggregate metrics

What we DON'T store:
❌ Patient names
❌ SSNs or medical record numbers
❌ Diagnoses or treatment details
❌ Any personal identifiers

This file provides functions to sanitize data before logging or storing.
"""

import re
from typing import Dict, Any, List

# ============================================
# SENSITIVE FIELD PATTERNS
# ============================================
# These field names should NEVER be logged in full

SENSITIVE_FIELDS = [
    # Personal identifiers
    'name', 'first_name', 'last_name', 'full_name',
    'email', 'phone', 'phone_number',
    'address', 'street', 'city', 'zip', 'postal_code',
    'ssn', 'social_security', 'tax_id',
    'dob', 'date_of_birth', 'birthdate',
    
    # Healthcare identifiers
    'patient_name', 'patient_id', 'medical_record_number', 'mrn',
    'diagnosis', 'condition', 'treatment', 'medication',
    'prescription', 'procedure', 'test_result',
    
    # Authentication
    'password', 'token', 'api_key', 'secret', 'credential',
    'auth', 'authorization', 'access_token', 'refresh_token',
]


# ============================================
# SANITIZE FUNCTION
# ============================================
def sanitize_for_logging(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Remove or redact sensitive fields from data before logging.
    
    This function recursively searches through dictionaries and
    replaces sensitive values with "[REDACTED]".
    
    Args:
        data: Dictionary that might contain sensitive data
    
    Returns:
        Sanitized dictionary safe for logging
    
    Example:
        raw = {
            "issue_key": "HC-123",
            "patient_name": "John Doe",
            "status": "In Progress",
            "assignee": {
                "email": "doctor@hospital.com",
                "name": "Dr. Smith"
            }
        }
        
        safe = sanitize_for_logging(raw)
        # Result:
        # {
        #   "issue_key": "HC-123",          # Safe - just an ID
        #   "patient_name": "[REDACTED]",   # Removed - PII
        #   "status": "In Progress",        # Safe - metadata
        #   "assignee": {
        #     "email": "[REDACTED]",        # Removed - PII
        #     "name": "[REDACTED]"          # Removed - PII
        #   }
        # }
        
        log_info("TaskSmith", "acme", "Processing issue", safe)
    """
    if not isinstance(data, dict):
        return data
    
    sanitized = {}
    
    for key, value in data.items():
        # Convert key to lowercase for case-insensitive matching
        key_lower = key.lower()
        
        # Check if this key matches any sensitive field
        is_sensitive = any(
            sensitive_word in key_lower 
            for sensitive_word in SENSITIVE_FIELDS
        )
        
        if is_sensitive:
            # Redact sensitive field
            sanitized[key] = '[REDACTED]'
        
        elif isinstance(value, dict):
            # Recursively sanitize nested dictionaries
            sanitized[key] = sanitize_for_logging(value)
        
        elif isinstance(value, list):
            # Sanitize lists of dictionaries
            sanitized[key] = [
                sanitize_for_logging(item) if isinstance(item, dict) else item
                for item in value
            ]
        
        else:
            # Safe to include
            sanitized[key] = value
    
    return sanitized


# ============================================
# VALIDATION FUNCTIONS
# ============================================

def validate_tenant_id(tenant_id: str) -> bool:
    """
    Validate tenant ID format to prevent injection attacks.
    
    Valid format:
    - Lowercase letters (a-z)
    - Numbers (0-9)
    - Hyphens (-)
    - Length: 3-50 characters
    
    Args:
        tenant_id: Tenant identifier to validate
    
    Returns:
        True if valid, False otherwise
    
    Examples:
        validate_tenant_id("acme-health")      # ✅ Valid
        validate_tenant_id("healthcare-123")   # ✅ Valid
        validate_tenant_id("UPPERCASE")        # ❌ Invalid (no uppercase)
        validate_tenant_id("has spaces")       # ❌ Invalid (no spaces)
        validate_tenant_id("ab")               # ❌ Invalid (too short)
        validate_tenant_id("x" * 51)           # ❌ Invalid (too long)
    
    Why validate?
        Prevents SQL injection-like attacks in DynamoDB queries
        Ensures consistent naming across system
    """
    # Pattern: lowercase alphanumeric + hyphens, 3-50 chars
    pattern = r'^[a-z0-9\-]{3,50}$'
    
    if not re.match(pattern, tenant_id):
        return False
    
    return True


def check_for_pii(data: Dict[str, Any]) -> List[str]:
    """
    Check if data contains potential PII that shouldn't be stored.
    
    Returns list of warnings (empty list = safe).
    
    Args:
        data: Dictionary to check
    
    Returns:
        List of warning messages
    
    Example:
        data = {
            "issue_key": "HC-123",
            "patient_name": "John Doe"
        }
        
        warnings = check_for_pii(data)
        # Returns: ["Field 'patient_name' contains potential PII"]
        
        if warnings:
            print("⚠️ PII detected!")
            for warning in warnings:
                print(f"  - {warning}")
    
    Use this before saving to DynamoDB to catch accidental PII storage.
    """
    warnings = []
    
    def check_dict(d: Dict[str, Any], path: str = ""):
        """Recursively check nested dictionaries."""
        for key, value in d.items():
            current_path = f"{path}.{key}" if path else key
            key_lower = key.lower()
            
            # Check if key matches sensitive pattern
            if any(sensitive in key_lower for sensitive in SENSITIVE_FIELDS):
                warnings.append(
                    f"Field '{current_path}' appears to contain PII/PHI"
                )
            
            # Recursively check nested dicts
            if isinstance(value, dict):
                check_dict(value, current_path)
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        check_dict(item, f"{current_path}[{i}]")
    
    check_dict(data)
    return warnings


# ============================================
# USAGE EXAMPLES
# ============================================
"""
HOW TO USE IN YOUR AGENTS:

1. Always sanitize before logging:
   
   raw_data = {"patient_name": "John", "issue_key": "HC-123"}
   safe_data = sanitize_for_logging(raw_data)
   log_info("TaskSmith", "acme", "Processing issue", safe_data)

2. Validate tenant IDs:
   
   if not validate_tenant_id(tenant_id):
       raise ValueError("Invalid tenant ID format")

3. Check for PII before saving to database:
   
   warnings = check_for_pii(data_to_save)
   if warnings:
       log_error("TaskSmith", tenant_id, "Attempted to save PII!", data={"warnings": warnings})
       raise ValueError("Cannot save PII to database")
   
   # Safe to save
   save_state(tenant_id, "TaskSmith", data_to_save)

REMEMBER: When in doubt, DON'T log it!
"""


# ============================================
# TESTING
# ============================================
if __name__ == '__main__':
    print("Testing security utilities...")
    print()
    
    # Test sanitization
    print("1. Testing sanitize_for_logging():")
    test_data = {
        "issue_key": "HC-123",
        "patient_name": "John Doe",
        "email": "john@example.com",
        "status": "In Progress",
        "nested": {
            "password": "secret123",
            "count": 5
        }
    }
    
    sanitized = sanitize_for_logging(test_data)
    print(f"Original: {test_data}")
    print(f"Sanitized: {sanitized}")
    print()
    
    # Test tenant validation
    print("2. Testing validate_tenant_id():")
    test_ids = [
        "acme-health",      # Valid
        "test-123",         # Valid
        "UPPERCASE",        # Invalid
        "has spaces",       # Invalid
        "ab",               # Too short
        "x" * 51            # Too long
    ]
    
    for tenant_id in test_ids:
        valid = validate_tenant_id(tenant_id)
        status = "✅" if valid else "❌"
        print(f"{status} {tenant_id}: {valid}")
    print()
    
    # Test PII detection
    print("3. Testing check_for_pii():")
    pii_data = {
        "issue_key": "HC-123",
        "patient_name": "John Doe",
        "count": 5
    }
    
    warnings = check_for_pii(pii_data)
    if warnings:
        print("⚠️ PII detected:")
        for warning in warnings:
            print(f"  - {warning}")
    else:
        print("✅ No PII detected")