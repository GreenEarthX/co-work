# GreenEarthX Platform - Setup & Deployment Guide

## Prerequisites

- **Docker & Docker Compose**: v20+ (for containerized development)
- **Node.js**: v20+ (for frontend development)
- **Python**: 3.11+ (for backend development)
- **PostgreSQL**: 15+ (or use Docker)
- **Redis**: 7+ (or use Docker)

## Quick Start (Docker - Recommended)

```bash
# 1. Clone the repository
git clone <repository-url>
cd gex-platform

# 2. Start all services
docker-compose up -d

# 3. Wait for services to be healthy (30-60 seconds)
docker-compose ps

# 4. Access the application
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000
# API Docs: http://localhost:8000/docs
```

## Local Development (Without Docker)

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Setup environment variables
cp .env.example .env
# Edit .env with your database credentials

# Run database migrations
alembic upgrade head

# Start development server
uvicorn app.main:app --reload

# Backend will be available at http://localhost:8000
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Setup environment variables
cp .env.example .env
# Edit .env with API URL

# Start development server
npm run dev

# Frontend will be available at http://localhost:3000
```

## Database Migrations

```bash
cd backend

# Create a new migration
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# See migration history
alembic history
```

## Running Tests

### Backend Tests
```bash
cd backend
pytest
pytest --cov=app  # With coverage report
```

### Frontend Tests
```bash
cd frontend
npm test
npm run test:coverage
```

## Production Deployment

### Environment Variables

Create `.env` files in both `backend/` and `frontend/`:

**backend/.env**
```bash
# Application
ENVIRONMENT=production
DEBUG=False

# Security
SECRET_KEY=<generate-strong-secret-key>
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Database (use managed PostgreSQL in production)
DATABASE_URL=postgresql://<user>:<password>@<host>:5432/<database>

# Redis (use managed Redis in production)
REDIS_URL=redis://<host>:6379/0

# CORS (set to your frontend domain)
CORS_ORIGINS=["https://your-domain.com"]
```

**frontend/.env.production**
```bash
VITE_API_URL=https://api.your-domain.com
```

### Docker Production Build

```bash
# Build production images
docker-compose -f docker-compose.prod.yml build

# Push to registry
docker tag gex-backend:latest your-registry/gex-backend:latest
docker push your-registry/gex-backend:latest

docker tag gex-frontend:latest your-registry/gex-frontend:latest
docker push your-registry/gex-frontend:latest
```

### AWS Deployment (Example)

1. **RDS PostgreSQL**
   - Create RDS PostgreSQL instance (db.t3.medium recommended)
   - Enable automated backups
   - Set retention period to 7 days
   - Enable Multi-AZ for production

2. **ElastiCache Redis**
   - Create Redis cluster (cache.t3.small recommended)
   - Enable automatic failover

3. **ECS Fargate** (Recommended) or **EC2**
   - Deploy backend as ECS service
   - Deploy frontend as ECS service
   - Configure Application Load Balancer
   - Set up auto-scaling rules

4. **CloudFront** (Optional but recommended)
   - Create CloudFront distribution
   - Point to frontend S3 bucket or ALB
   - Enable HTTPS with ACM certificate

### Health Checks

The backend exposes a health check endpoint:

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "environment": "production",
  "version": "1.0.0"
}
```

## Monitoring

### Application Performance Monitoring

1. **Datadog** (Recommended)
```bash
# Install Datadog agent
DD_API_KEY=<your-key> DD_SITE="datadoghq.com" bash -c "$(curl -L https://s3.amazonaws.com/dd-agent/scripts/install_script.sh)"

# Configure application
# Add datadog integration to requirements.txt
pip install ddtrace
```

2. **Error Tracking with Sentry**
```bash
# Backend
pip install sentry-sdk

# Frontend
npm install @sentry/react
```

### Logging

Backend uses Python's standard logging:

```python
import logging
logger = logging.getLogger(__name__)
logger.info("Message")
```

View logs:
```bash
# Docker
docker-compose logs -f backend

# Local
tail -f logs/app.log
```

## Security Checklist

- [ ] Change all default passwords
- [ ] Generate strong SECRET_KEY
- [ ] Enable HTTPS in production
- [ ] Configure CORS properly
- [ ] Enable rate limiting
- [ ] Set up database backups
- [ ] Configure firewall rules
- [ ] Enable audit logging
- [ ] Set up monitoring alerts
- [ ] Implement API key rotation
- [ ] Regular dependency updates
- [ ] SQL injection prevention (use ORM)
- [ ] XSS prevention (React escapes by default)
- [ ] CSRF protection (enabled in FastAPI)

## Performance Optimization

### Database Optimization

1. **Indexes** - Already configured in models:
   - Compound indexes on frequently queried columns
   - Index on foreign keys

2. **Connection Pooling**
```python
# In database.py
engine = create_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=10
)
```

3. **Query Optimization**
   - Use `.select_related()` for foreign keys
   - Use `.prefetch_related()` for many-to-many
   - Limit query results with pagination

### Frontend Optimization

1. **Code Splitting**
```typescript
// Lazy load pages
const CapacityPage = lazy(() => import('./features/capacity/CapacityPage'))
```

2. **Bundle Size**
```bash
# Analyze bundle
npm run build
npm run analyze
```

3. **Caching**
   - React Query handles caching automatically
   - Configure staleTime and cacheTime

## Troubleshooting

### Backend won't start
```bash
# Check database connection
psql -h localhost -U gex_user -d gex_platform

# Check logs
docker-compose logs backend

# Verify environment variables
docker-compose exec backend env
```

### Frontend build fails
```bash
# Clear node_modules and reinstall
rm -rf node_modules package-lock.json
npm install

# Check TypeScript errors
npm run type-check
```

### Database migration errors
```bash
# Check current migration state
alembic current

# Reset database (CAUTION: destroys data)
alembic downgrade base
alembic upgrade head
```

## Backup & Recovery

### Database Backup
```bash
# Automated backup (schedule with cron)
pg_dump -h localhost -U gex_user gex_platform > backup_$(date +%Y%m%d).sql

# Restore
psql -h localhost -U gex_user gex_platform < backup_20250120.sql
```

### Application Data Export
```bash
# Use the export endpoints
curl http://localhost:8000/api/v1/export/full > full_export.json
```

## Support & Documentation

- **Architecture**: See [ANALYSIS.md](./ANALYSIS.md)
- **API Documentation**: http://localhost:8000/docs (when running)
- **Matching Algorithm**: See [backend/app/services/matching_engine.py](./backend/app/services/matching_engine.py)
- **Database Schema**: See [backend/app/db/models.py](./backend/app/db/models.py)

## Next Steps

1. ✅ Complete authentication integration (Clerk/Auth0)
2. ✅ Implement all API endpoints (currently stubs)
3. ✅ Add real-time WebSocket support
4. ✅ Build out frontend features
5. ✅ Write comprehensive tests
6. ✅ Set up CI/CD pipeline
7. ✅ Security audit
8. ✅ Load testing
9. ✅ User documentation
10. ✅ Beta testing with real producers
