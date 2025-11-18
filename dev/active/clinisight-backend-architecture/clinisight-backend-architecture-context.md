# Clinisight Backend Architecture - Context & Key Decisions

**Last Updated:** 2025-11-11

---

## Project Overview

**Name:** Clinisight.AI - Healthcare Intelligence Platform
**Purpose:** AI-powered project management intelligence for healthcare teams using Atlassian tools
**Status:** Early development - foundation established, expanding to full agent ecosystem

**Core Value Proposition:**
Automated intelligence agents that understand healthcare workflows, reduce manual project management overhead, ensure HIPAA compliance, and provide strategic insights through natural language interaction.

---

## Technology Stack

### Frontend
- **Platform:** Atlassian Forge (Node.js 20.x runtime)
- **UI Framework:** Forge UI components (declarative React-like)
- **Modules:**
  - Jira Issue Panel (displaying agent status)
  - Rovo Agent (planned - conversational interface)
  - Confluence Macro (planned - dashboard)

### Backend
- **Language:** Python 3.11
- **Framework:** Serverless Framework 3
- **Cloud Provider:** AWS
- **Deployment:** AWS Lambda (serverless functions)

### Data Storage
- **Primary Database:** DynamoDB
  - `ClinisightAgentState-{stage}` - Agent state persistence
  - `ClinisightEmbeddings-{stage}` - Vector embeddings for knowledge retrieval
- **Billing Mode:** PAY_PER_REQUEST (auto-scaling)
- **Encryption:** AWS-managed encryption (planned: customer-managed KMS)

### Integration Layer
- **API Gateway:** REST API for webhooks from Forge
- **EventBridge:** Scheduled triggers for periodic agent runs
- **Lambda SDK:** boto3 for AWS service interaction

### Monitoring & Observability
- **Current:** CloudWatch Logs only
- **Planned:** Sentry v8 for error tracking and performance monitoring
- **Metrics:** Custom CloudWatch metrics for agent performance

### AI/ML
- **Current:** Rule-based logic (keyword matching)
- **Planned:** Claude API (Anthropic) for natural language understanding
- **Embeddings:** OpenAI ada-002 or AWS Titan (for MindMesh agent)

---

## Architecture Pattern: Event-Driven Orchestrator

### Core Principle
**Separation of Concerns:** Single orchestrator routes events to specialized agents, enabling loose coupling and independent scaling.

### Event Flow
```
User Action (Jira/Confluence)
  → Webhook Trigger
    → API Gateway
      → Orchestrator Lambda
        → Specific Agent Lambda
          → DynamoDB (state persistence)
            → Response to Orchestrator
              → API Gateway Response
```

### Why This Pattern?

1. **Scalability:** Each agent scales independently based on demand
2. **Maintainability:** Agents are self-contained, changes don't cascade
3. **Testability:** Can test agents in isolation without full system
4. **Observability:** Central logging in orchestrator, distributed tracing per agent
5. **Cost Efficiency:** Only pay for agents that are invoked

---

## Key Files & Their Purposes

### Backend (`Clinisight.AI/clinisight_backend/`)

#### Core Infrastructure
| File | Purpose | Status |
|------|---------|--------|
| `serverless.yml` | Infrastructure-as-code, defines all AWS resources | ✅ Production-ready |
| `package.json` | Node.js dependencies for Serverless Framework | ✅ Complete |
| `requirements.txt` | Python dependencies (boto3, sentry-sdk, etc.) | 🔄 Needs sentry-sdk |
| `secret.json` | Secrets (API keys, DSNs) - NOT committed to git | ⚠️ Template only |

#### Orchestrator
| File | Purpose | Status |
|------|---------|--------|
| `orchestrator/handler.py` | Main event router, determines which agent to invoke | ✅ Well-architected |
| `orchestrator/__init__.py` | Python package marker | ✅ Complete |

#### Agents
| File | Purpose | Status |
|------|---------|--------|
| `agents/tasksmith.py` | Epic decomposition agent | ✅ MVP complete |
| `agents/__init__.py` | Python package marker | ✅ Complete |
| `agents/caretrack.py` | (Planned) Workflow monitoring agent | ❌ Not started |
| `agents/dealflow.py` | (Planned) Resource allocation agent | ❌ Not started |
| `agents/mindmesh.py` | (Planned) Knowledge retrieval agent | ❌ Not started |
| `agents/roadmapsmith.py` | (Planned) Strategic planning agent | ❌ Not started |

#### Shared Utilities
| File | Purpose | Status |
|------|---------|--------|
| `shared/database.py` | DynamoDB operations (CRUD, Query) | ✅ Production-ready |
| `shared/logger.py` | Structured logging utilities | ✅ Complete |
| `shared/security.py` | Tenant validation, PII detection, sanitization | ✅ Basic, needs expansion |
| `shared/__init__.py` | Python package marker | ✅ Complete |

#### Monitoring (Planned)
| File | Purpose | Status |
|------|---------|--------|
| `sentry_init.py` | Sentry SDK initialization | 🔄 Exists but not integrated |
| `orchestrator/handler_with_sentry.py` | Orchestrator with Sentry integration | 🔄 WIP, not deployed |

### Frontend (`Clinisight.AI/`)

| File | Purpose | Status |
|------|---------|--------|
| `src/index.js` | Main Forge resolver, renders issue panel | ✅ Basic UI only |
| `manifest.yml` | Forge app configuration (modules, permissions) | ✅ Basic setup |
| `package.json` | Forge dependencies | ✅ Complete |

---

## Key Decisions & Rationale

### Decision 1: Python vs. Node.js for Backend
**Choice:** Python 3.11
**Rationale:**
- Rich AI/ML ecosystem (langchain, openai, anthropic)
- boto3 provides excellent AWS integration
- Easier to read/maintain for healthcare domain logic
- Team expertise in Python

**Trade-off:** Node.js would have faster cold starts, but Python's AI library support is critical.

### Decision 2: DynamoDB vs. RDS
**Choice:** DynamoDB with PAY_PER_REQUEST
**Rationale:**
- Fully serverless (no server management)
- Auto-scales to zero when unused (cost savings)
- Single-millisecond latency for agent state retrieval
- Multi-region replication available (future-proofing)

**Trade-off:** NoSQL requires different thinking than SQL, but agent state is simple key-value.

### Decision 3: Orchestrator Pattern vs. Direct Agent Invocation
**Choice:** Orchestrator pattern
**Rationale:**
- Single webhook endpoint (easier to configure in Forge)
- Central error handling and logging
- Routing logic in one place (easy to modify)
- Agents don't need to know about API Gateway

**Trade-off:** Adds one extra Lambda invocation per request, but negligible cost and latency.

### Decision 4: Serverless Framework vs. AWS SAM
**Choice:** Serverless Framework
**Rationale:**
- Simpler YAML syntax than CloudFormation
- Rich plugin ecosystem (python-requirements, offline)
- Multi-cloud portability (not locked to AWS)
- Better documentation and community

**Trade-off:** Less AWS-native than SAM, but benefits outweigh.

### Decision 5: Sentry vs. CloudWatch Insights
**Choice:** Sentry (to be implemented)
**Rationale:**
- Superior error grouping (avoids log noise)
- User context tracking (tenant ID, agent name)
- Performance monitoring built-in
- Better developer experience (email alerts, Slack integration)

**Trade-off:** Additional $29-99/month cost, but worth it for observability.

### Decision 6: Claude vs. GPT-4 for AI
**Choice:** Claude (Anthropic)
**Rationale:**
- Better reasoning on complex tasks (epic decomposition)
- HIPAA-compliant infrastructure available
- Lower hallucination rate (critical for healthcare)
- Longer context window in newer models

**Trade-off:** Slightly more expensive per token, but quality is paramount.

---

## Data Models

### DynamoDB: AgentStateTable

**Table Name:** `ClinisightAgentState-{stage}`

**Schema:**
```python
{
  "tenantId": "acme-health",        # Partition key (string)
  "agentName": "TaskSmith",         # Sort key (string)
  "stateData": {                    # Agent-specific data (map)
    "epic_key": "HC-100",
    "subtasks_created": 5,
    "subtasks": [...]
  },
  "updatedAt": "2025-01-15T10:00:00Z"  # ISO timestamp
}
```

**Access Patterns:**
1. **Save agent state:** `put_item(tenantId, agentName, stateData)`
2. **Get agent state:** `get_item(tenantId, agentName)`
3. **Get all agents for tenant:** `query(tenantId)` (for Rovo insights)

**Why This Schema?**
- Composite key (tenantId + agentName) ensures isolation and efficient queries
- Flexible `stateData` map allows each agent to store custom fields
- `updatedAt` enables audit trails and debugging

### DynamoDB: EmbeddingsTable (Planned)

**Table Name:** `ClinisightEmbeddings-{stage}`

**Schema:**
```python
{
  "tenantId": "acme-health",        # Partition key
  "documentId": "doc-123",          # Sort key
  "embedding": [0.1, 0.2, ...],     # 1536-dim vector (OpenAI ada-002)
  "documentType": "confluence_page", # "epic", "comment", etc.
  "content": "First 500 chars...",  # Snippet for display
  "metadata": {                     # Additional context
    "url": "https://...",
    "title": "HIPAA Compliance Guide",
    "createdAt": "2025-01-01"
  }
}
```

**Access Patterns:**
1. **Store embedding:** `put_item(tenantId, documentId, embedding, ...)`
2. **Retrieve by ID:** `get_item(tenantId, documentId)`
3. **Semantic search:** `scan` with cosine similarity (inefficient, may migrate to OpenSearch)

**Why This Schema?**
- Multi-tenant isolation via tenantId
- documentId as sort key enables versioning (same doc, different versions)
- Storing embedding + snippet enables fast retrieval + display

---

## Dependencies & External Services

### AWS Services
| Service | Usage | Cost Impact |
|---------|-------|-------------|
| Lambda | Agent execution | $0.20 per 1M requests + compute time |
| DynamoDB | State persistence | ~$1.25 per million writes (PAY_PER_REQUEST) |
| API Gateway | Webhook endpoint | $3.50 per million requests |
| CloudWatch Logs | Logging | $0.50 per GB ingested |
| EventBridge | Scheduled triggers | $1.00 per million events |
| IAM | Access control | Free |

**Total Estimated Cost:** $100-200/month for pilot (10 tenants, moderate usage)

### Third-Party Services
| Service | Usage | Cost | Status |
|---------|-------|------|--------|
| Sentry | Error tracking | $29-99/month | Planned |
| Anthropic Claude | AI reasoning | ~$0.01 per 1K tokens | Planned |
| OpenAI Embeddings | Vector embeddings | ~$0.0001 per 1K tokens | Planned |

### Atlassian Services
| Service | Usage | Cost | Status |
|---------|-------|------|--------|
| Forge | App hosting | Free (developer) | Active |
| Jira Cloud API | Read/write issues | Free (bundled with Forge) | Active |
| Confluence Cloud API | Read/write pages | Free (bundled with Forge) | Planned |
| Rovo | Conversational AI | Beta (free for now) | Planned |

---

## Security & Compliance Considerations

### HIPAA Requirements

**PHI (Protected Health Information) Handling:**
- **Current State:** PII detection in `shared/security.py`, basic validation
- **Required:**
  - Encryption at rest (DynamoDB)
  - Encryption in transit (TLS 1.2+)
  - Audit logging (who accessed what, when)
  - Data retention policies (7-year minimum per HIPAA)
  - BAA (Business Associate Agreement) with all vendors

**Security Controls:**
| Control | Status | Priority |
|---------|--------|----------|
| Tenant ID validation | ✅ Implemented | P0 |
| PII detection in logs | ✅ Basic implementation | P1 |
| Encryption at rest | ❌ Using AWS defaults | P1 |
| Customer-managed KMS keys | ❌ Not implemented | P2 |
| Audit logging | ❌ Not implemented | P1 |
| WAF with rate limiting | ❌ Not implemented | P2 |
| Multi-factor authentication | ❌ Relies on Atlassian | P2 |

### Data Isolation
- **Multi-tenancy Strategy:** Tenant ID as partition key in DynamoDB
- **Prevents:** Cross-tenant data leakage (different partition keys = different physical storage)
- **Limitation:** Shared Lambda execution environment (acceptable risk for serverless)

---

## Testing Strategy

### Current State
- **Unit Tests:** None
- **Integration Tests:** Manual testing only
- **Load Tests:** None
- **Security Tests:** None

### Planned Approach

**Unit Tests (pytest):**
- Test each agent function in isolation
- Mock DynamoDB, AI API calls
- Target: 80%+ code coverage

**Integration Tests:**
- Test orchestrator → agent → DynamoDB flow
- Use LocalStack for local DynamoDB
- Test Forge → API Gateway → Lambda flow

**Performance Tests:**
- Load test with 1000 concurrent requests
- Measure Lambda cold start times
- Validate DynamoDB query performance

**Security Tests:**
- Penetration testing (simulated attacks)
- OWASP Top 10 vulnerability scan
- Compliance audit (HIPAA checklist)

---

## Deployment Process

### Current Process
```bash
# Backend deployment
cd clinisight_backend
serverless deploy --stage dev

# Frontend deployment
cd ../
forge deploy --no-verify
forge install --product jira
```

**Issues:**
- Manual deployment (human error risk)
- No automated testing before deploy
- No rollback mechanism
- No environment parity (dev vs. prod differences)

### Planned CI/CD (Phase 9)
```yaml
# GitHub Actions workflow (planned)
on: [push, pull_request]

jobs:
  test:
    - Run pytest with coverage
    - Run integration tests
    - Security scan (Bandit, Safety)

  deploy-dev:
    if: branch == main
    - Deploy to dev environment
    - Run smoke tests

  deploy-prod:
    if: tag matches v*
    - Manual approval required
    - Deploy to prod
    - Monitor Sentry for errors
    - Auto-rollback if error rate > 5%
```

---

## Known Issues & Technical Debt

### High Priority
1. **No error tracking system** - Sentry integration critical for production
2. **No AI integration** - TaskSmith uses keyword matching, not real AI
3. **No audit logging** - HIPAA compliance gap
4. **No automated testing** - Risky to deploy changes

### Medium Priority
1. **Limited agent coverage** - Only TaskSmith implemented (1 of 5)
2. **Basic frontend** - Static text, no real-time updates
3. **No webhook configuration** - Manual trigger only
4. **No caching** - AI API calls will be expensive without caching

### Low Priority
1. **No CI/CD pipeline** - Manual deployment works for now
2. **No multi-region support** - Single region (us-east-1) sufficient for pilot
3. **No cost optimization** - No CloudWatch cost alerts, no budget caps

---

## Common Troubleshooting

### Issue: Lambda function not invoking
**Symptoms:** Orchestrator receives event, but agent doesn't run
**Causes:**
- IAM role missing `lambda:InvokeFunction` permission
- Agent Lambda not deployed
- Function name mismatch (check SERVICE_NAME and STAGE)

**Resolution:**
```bash
# Verify Lambda exists
aws lambda list-functions | grep clinisight

# Check orchestrator IAM role
aws iam get-role --role-name clinisight-backend-dev-orchestrator

# Test manual invocation
aws lambda invoke --function-name clinisight-backend-dev-tasksmith out.json
```

### Issue: DynamoDB write fails
**Symptoms:** Agent runs but state not saved
**Causes:**
- IAM role missing DynamoDB permissions
- Table doesn't exist
- Invalid tenantId format

**Resolution:**
```bash
# Check table exists
aws dynamodb describe-table --table-name ClinisightAgentState-dev

# Test write manually
aws dynamodb put-item --table-name ClinisightAgentState-dev \
  --item '{"tenantId": {"S": "test"}, "agentName": {"S": "Test"}}'
```

### Issue: API Gateway 403 Forbidden
**Symptoms:** Forge webhook fails with 403
**Causes:**
- API Gateway resource policy blocking requests
- CORS not configured
- Invalid API key (if using API key auth)

**Resolution:**
```bash
# Check API Gateway deployment
serverless info --stage dev

# Test endpoint directly
curl -X POST https://{api-id}.execute-api.us-east-1.amazonaws.com/dev/webhook \
  -H "Content-Type: application/json" \
  -d '{"eventType": "EPIC_CREATED", "tenantId": "test"}'
```

---

## Performance Benchmarks (Target)

| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| **Orchestrator latency (p95)** | < 200ms | ~150ms | ✅ On target |
| **TaskSmith latency (p95)** | < 5s | ~2s (without AI) | ✅ On target |
| **DynamoDB query time (p95)** | < 100ms | ~20ms | ✅ Excellent |
| **Lambda cold start (p95)** | < 3s | ~2.5s | ✅ Acceptable |
| **API Gateway 4xx rate** | < 1% | Unknown | ❌ No monitoring |
| **Lambda error rate** | < 0.1% | Unknown | ❌ No monitoring |

**Note:** Current metrics are estimates from manual testing. Phase 1 (Sentry) will provide accurate metrics.

---

## Team Knowledge & Expertise Gaps

### Current Strengths
- Python development
- AWS serverless basics (Lambda, DynamoDB)
- Atlassian Forge fundamentals
- Healthcare domain knowledge

### Knowledge Gaps
- **Sentry integration** - Need to learn SDK setup and best practices
- **AI prompt engineering** - Claude API integration, token optimization
- **HIPAA compliance** - Legal requirements, audit processes
- **Vector embeddings** - Semantic search, similarity algorithms
- **CI/CD with GitHub Actions** - Workflow design, secrets management

### Recommended Training
1. **Sentry University:** Free online courses for error tracking
2. **Anthropic Documentation:** Claude API best practices
3. **AWS Well-Architected Framework:** Serverless best practices
4. **HIPAA Compliance Training:** Healthcare data handling certification

---

## Future Considerations

### Scalability
- **Current:** Single AWS region, no multi-region
- **Future:** Multi-region for disaster recovery, global users
- **Trigger:** > 1000 tenants or international expansion

### Multi-Cloud
- **Current:** AWS-only
- **Future:** Azure or GCP for customer requirements
- **Preparation:** Serverless Framework already supports multi-cloud

### Advanced AI
- **Current:** Planned Claude API integration
- **Future:** Fine-tuned models specific to healthcare
- **Trigger:** > 10,000 epics processed (sufficient training data)

### Real-Time Features
- **Current:** Polling-based updates in Forge UI
- **Future:** WebSocket connections for real-time agent status
- **Limitation:** Forge doesn't support WebSockets yet (as of 2025)

---

## Document Maintenance

**Update Frequency:** After each phase completion, or when major architectural changes occur

**Owners:**
- Backend architecture: Backend lead engineer
- Security/compliance: Compliance specialist
- Frontend integration: Frontend engineer

**Next Review:** After Phase 1 (Monitoring) completion

---

**Last Updated:** 2025-11-11
**Document Version:** 1.0
**Status:** Living document - update as project evolves
