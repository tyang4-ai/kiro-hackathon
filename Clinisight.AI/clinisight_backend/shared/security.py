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
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

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
# HEALTHCARE PII REGEX PATTERNS
# ============================================
# Patterns to detect PII/PHI in free text (not just field names)

HEALTHCARE_PII_PATTERNS = {
    # Social Security Number (SSN)
    # Formats: 123-45-6789, 123 45 6789, 123456789
    'ssn': {
        'pattern': r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b',
        'description': 'Social Security Number',
        'severity': 'critical'
    },

    # Medical Record Number (MRN)
    # Common formats: MRN-12345678, MRN: 12345678, MRN12345678
    'mrn': {
        'pattern': r'\b(?:MRN[-:\s]?\d{6,10}|\d{6,10}[-\s]?MRN)\b',
        'description': 'Medical Record Number',
        'severity': 'critical'
    },

    # Date of Birth
    # Formats: 01/15/1990, 1990-01-15, Jan 15, 1990
    'dob': {
        'pattern': r'\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})\b',
        'description': 'Date of Birth',
        'severity': 'high'
    },

    # Phone Numbers
    # Formats: (555) 123-4567, 555-123-4567, 5551234567
    'phone': {
        'pattern': r'\b(?:\(\d{3}\)\s*|\d{3}[-.\s]?)\d{3}[-.\s]?\d{4}\b',
        'description': 'Phone Number',
        'severity': 'high'
    },

    # Email Addresses
    'email': {
        'pattern': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        'description': 'Email Address',
        'severity': 'high'
    },

    # Insurance/Member ID
    # Common formats: Various alphanumeric patterns
    'insurance_id': {
        'pattern': r'\b(?:INS|MEM|POL|GRP)[-\s]?\d{8,12}\b',
        'description': 'Insurance/Member ID',
        'severity': 'high'
    },

    # National Provider Identifier (NPI)
    # 10-digit number
    'npi': {
        'pattern': r'\b(?:NPI[-:\s]?)?\d{10}\b',
        'description': 'National Provider Identifier',
        'severity': 'medium'
    },

    # DEA Number (Drug Enforcement Administration)
    # Format: 2 letters + 7 digits
    'dea': {
        'pattern': r'\b[A-Z]{2}\d{7}\b',
        'description': 'DEA Number',
        'severity': 'high'
    },

    # Credit Card Numbers
    # 13-19 digits, may have spaces/dashes
    'credit_card': {
        'pattern': r'\b(?:\d{4}[-\s]?){3,4}\d{1,4}\b',
        'description': 'Credit Card Number',
        'severity': 'critical'
    },

    # ICD-10 Diagnosis Codes
    # Format: Letter + 2 digits + optional decimal + up to 4 more characters
    'icd10': {
        'pattern': r'\b[A-Z]\d{2}(?:\.\d{1,4})?\b',
        'description': 'ICD-10 Diagnosis Code',
        'severity': 'medium'
    },

    # CPT Procedure Codes
    # 5-digit codes, may have modifiers
    'cpt': {
        'pattern': r'\b\d{5}(?:[-]\d{2})?\b',
        'description': 'CPT Procedure Code',
        'severity': 'low'
    },

    # NDC (National Drug Code)
    # Format: 5-4-2, 5-4-1, 5-3-2, 4-4-2
    'ndc': {
        'pattern': r'\b\d{4,5}[-]\d{3,4}[-]\d{1,2}\b',
        'description': 'National Drug Code',
        'severity': 'medium'
    },
}


# ============================================
# PII SCAN RESULT DATA CLASS
# ============================================
@dataclass
class PIIScanResult:
    """
    Result of scanning data for PII/PHI.

    Gracefully handles missing data - any field not provided
    will be set to a sensible default (empty list or 'N/A').
    """
    # What was found
    detected_patterns: List[Dict[str, Any]] = field(default_factory=list)
    sensitive_fields: List[str] = field(default_factory=list)

    # Summary
    has_pii: bool = False
    risk_level: str = 'none'  # none, low, medium, high, critical

    # Metadata
    scan_summary: str = 'N/A'
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'detected_patterns': self.detected_patterns if self.detected_patterns else [],
            'sensitive_fields': self.sensitive_fields if self.sensitive_fields else [],
            'has_pii': self.has_pii,
            'risk_level': self.risk_level,
            'scan_summary': self.scan_summary if self.scan_summary else 'N/A',
            'recommendations': self.recommendations if self.recommendations else []
        }


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
# COMPREHENSIVE PII SCANNER (HIPAA)
# ============================================
def scan_for_healthcare_pii(
    data: Optional[Dict[str, Any]] = None,
    text: Optional[str] = None,
    check_patterns: bool = True,
    check_fields: bool = True
) -> PIIScanResult:
    """
    Comprehensive PII/PHI scanner for healthcare data.

    Scans both field names AND content values for potential PII.
    Gracefully handles missing or partial data - never errors.

    Args:
        data: Dictionary to scan (optional)
        text: Free text to scan (optional)
        check_patterns: Whether to check regex patterns in values
        check_fields: Whether to check sensitive field names

    Returns:
        PIIScanResult with all findings (empty/default if nothing found)

    Example:
        # Scan a dictionary
        result = scan_for_healthcare_pii(data={
            "issue_key": "HC-123",
            "description": "Patient SSN: 123-45-6789"
        })

        if result.has_pii:
            print(f"Risk: {result.risk_level}")
            for pattern in result.detected_patterns:
                print(f"  - {pattern['type']}: {pattern['description']}")

        # Scan just text
        result = scan_for_healthcare_pii(text="Call 555-123-4567")

        # Handle gracefully if no data provided
        result = scan_for_healthcare_pii()  # Returns empty result, no error
    """
    result = PIIScanResult()
    detected = []
    sensitive = []
    severity_levels = []

    # Handle case where nothing is provided
    if data is None and text is None:
        result.scan_summary = 'No data provided for scanning'
        return result

    # Collect all text to scan
    all_text_values = []

    if text:
        all_text_values.append(text)

    if data:
        # Extract all string values from dictionary
        def extract_text(obj, path=""):
            if isinstance(obj, str):
                all_text_values.append(obj)
            elif isinstance(obj, dict):
                for key, value in obj.items():
                    current_path = f"{path}.{key}" if path else key

                    # Check field names
                    if check_fields:
                        key_lower = key.lower()
                        if any(s in key_lower for s in SENSITIVE_FIELDS):
                            sensitive.append(current_path)

                    extract_text(value, current_path)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    extract_text(item, f"{path}[{i}]")

        extract_text(data)

    # Scan text values for PII patterns
    if check_patterns and all_text_values:
        combined_text = ' '.join(all_text_values)

        for pattern_name, pattern_info in HEALTHCARE_PII_PATTERNS.items():
            regex = pattern_info.get('pattern', '')
            if not regex:
                continue

            try:
                matches = re.findall(regex, combined_text, re.IGNORECASE)
                if matches:
                    detected.append({
                        'type': pattern_name,
                        'description': pattern_info.get('description', 'Unknown'),
                        'severity': pattern_info.get('severity', 'medium'),
                        'count': len(matches),
                        'sample': matches[0][:20] + '...' if len(matches[0]) > 20 else matches[0]
                    })
                    severity_levels.append(pattern_info.get('severity', 'medium'))
            except re.error:
                # Invalid regex - skip this pattern
                continue

    # Populate result
    result.detected_patterns = detected if detected else []
    result.sensitive_fields = sensitive if sensitive else []
    result.has_pii = bool(detected or sensitive)

    # Determine overall risk level
    if not result.has_pii:
        result.risk_level = 'none'
    elif 'critical' in severity_levels or len(sensitive) > 5:
        result.risk_level = 'critical'
    elif 'high' in severity_levels or len(sensitive) > 3:
        result.risk_level = 'high'
    elif 'medium' in severity_levels or len(sensitive) > 1:
        result.risk_level = 'medium'
    else:
        result.risk_level = 'low'

    # Generate summary
    pattern_count = len(detected)
    field_count = len(sensitive)

    if result.has_pii:
        parts = []
        if pattern_count > 0:
            parts.append(f"{pattern_count} PII pattern(s)")
        if field_count > 0:
            parts.append(f"{field_count} sensitive field(s)")
        result.scan_summary = f"Found {', '.join(parts)}. Risk level: {result.risk_level.upper()}"
    else:
        result.scan_summary = 'No PII/PHI detected'

    # Generate recommendations
    recommendations = []
    if 'ssn' in [d['type'] for d in detected]:
        recommendations.append('Remove or mask Social Security Numbers before storing')
    if 'mrn' in [d['type'] for d in detected]:
        recommendations.append('Hash or encrypt Medical Record Numbers')
    if sensitive:
        recommendations.append('Rename sensitive fields or redact values before logging')
    if result.risk_level in ['high', 'critical']:
        recommendations.append('This data should NOT be stored in logs or non-encrypted storage')

    result.recommendations = recommendations if recommendations else []

    return result


def mask_pii_in_text(text: str) -> str:
    """
    Mask detected PII patterns in text with placeholders.

    Args:
        text: Text that may contain PII

    Returns:
        Text with PII replaced by [MASKED-TYPE]

    Example:
        text = "Patient SSN: 123-45-6789, Phone: 555-123-4567"
        masked = mask_pii_in_text(text)
        # Result: "Patient SSN: [MASKED-SSN], Phone: [MASKED-PHONE]"
    """
    if not text:
        return text or ''

    masked_text = text

    for pattern_name, pattern_info in HEALTHCARE_PII_PATTERNS.items():
        regex = pattern_info.get('pattern', '')
        if not regex:
            continue

        try:
            masked_text = re.sub(
                regex,
                f'[MASKED-{pattern_name.upper()}]',
                masked_text,
                flags=re.IGNORECASE
            )
        except re.error:
            continue

    return masked_text


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
    print()

    # Test comprehensive healthcare PII scanner
    print("4. Testing scan_for_healthcare_pii():")

    # Test with SSN and phone
    healthcare_data = {
        "issue_key": "HC-123",
        "description": "Patient SSN: 123-45-6789, call 555-123-4567",
        "patient_name": "John Doe",
        "notes": "MRN-12345678"
    }

    result = scan_for_healthcare_pii(data=healthcare_data)
    print(f"Summary: {result.scan_summary}")
    print(f"Risk Level: {result.risk_level}")
    print(f"Has PII: {result.has_pii}")

    if result.detected_patterns:
        print("Detected patterns:")
        for pattern in result.detected_patterns:
            print(f"  - {pattern['type']}: {pattern['description']} (severity: {pattern['severity']})")

    if result.sensitive_fields:
        print("Sensitive fields:")
        for field in result.sensitive_fields:
            print(f"  - {field}")

    if result.recommendations:
        print("Recommendations:")
        for rec in result.recommendations:
            print(f"  - {rec}")
    print()

    # Test with no data (graceful handling)
    print("5. Testing graceful handling of missing data:")
    empty_result = scan_for_healthcare_pii()
    print(f"Empty data result: {empty_result.scan_summary}")
    print(f"Risk Level: {empty_result.risk_level}")
    print(f"Has PII: {empty_result.has_pii}")
    print()

    # Test partial data (just SSN, nothing else)
    print("6. Testing partial data (just SSN):")
    partial_result = scan_for_healthcare_pii(text="123-45-6789")
    print(f"Summary: {partial_result.scan_summary}")
    print(f"Detected: {[p['type'] for p in partial_result.detected_patterns]}")
    print()

    # Test masking
    print("7. Testing mask_pii_in_text():")
    sensitive_text = "Patient SSN: 123-45-6789, Phone: 555-123-4567, Email: test@example.com"
    masked = mask_pii_in_text(sensitive_text)
    print(f"Original: {sensitive_text}")
    print(f"Masked: {masked}")