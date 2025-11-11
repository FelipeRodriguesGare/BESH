#!/bin/bash
# Quick start script for BESH with infrastructure services

set -e

echo "🚀 Starting BESH Infrastructure Services..."

# Start PostgreSQL and Redis
docker-compose -f docker-compose.infra.yml up -d

echo "⏳ Waiting for services to be healthy..."
sleep 5

# Check if services are running
docker-compose -f docker-compose.infra.yml ps

echo ""
echo "✅ Infrastructure services are running!"
echo ""
echo "📋 Next steps:"
echo "1. Make sure your .env file is configured with:"
echo "   - NEBIUS_API_BASE"
echo "   - NEBIUS_API_KEY"
echo "   - Database and Redis URLs (see docs/INFRA_SETUP.md)"
echo ""
echo "2. Start BESH application:"
echo "   besh serve --host 0.0.0.0 --port 8080"
echo ""
echo "3. Access the dashboard:"
echo "   http://localhost:8080"
echo ""
echo "To stop infrastructure:"
echo "   docker-compose -f docker-compose.infra.yml down"
echo ""

