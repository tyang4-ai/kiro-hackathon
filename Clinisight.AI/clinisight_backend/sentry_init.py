"""
Sentry Initialization for AWS Lambda
=====================================

This module initializes Sentry with AWS Lambda integration.
Import this at the TOP of every Lambda handler file.

Usage:
    from sentry_init import init_sentry
    init_sentry()
"""

import os
import sentry_sdk
from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration


def init_sentry():
    """
    Initialize Sentry for Lambda functions.

    Features:
    - AWS Lambda integration (automatic error capture)
    - Timeout warnings (alerts before Lambda times out)
    - Performance monitoring (traces sample rate)
    - Environment tagging (dev/prod separation)
    """

    sentry_dsn = os.environ.get('SENTRY_DSN')

    if not sentry_dsn:
        print("⚠️ SENTRY_DSN not set - error tracking disabled")
        return

    environment = os.environ.get('STAGE', 'development')

    sentry_sdk.init(
        dsn=sentry_dsn,

        # AWS Lambda integration with timeout warnings
        integrations=[
            AwsLambdaIntegration(timeout_warning=True)
        ],

        # Environment tracking (dev/prod)
        environment=environment,

        # Performance monitoring (10% sample rate)
        traces_sample_rate=0.1,

        # Tag all errors with service
        before_send=add_service_context,
    )

    print(f"✅ Sentry initialized for environment: {environment}")


def add_service_context(event, hint):
    """
    Add additional context to all Sentry events.

    This runs before every error is sent to Sentry.
    """
    # Add service tag
    event.setdefault('tags', {})
    event['tags']['service'] = 'clinisight-backend'
    event['tags']['aws_region'] = os.environ.get('AWS_REGION', 'unknown')

    return event
