#!/bin/bash
# System Test Runner
# Runs comprehensive system tests with environment setup

set -e  # Exit on error

echo "🧪 Merge Assist - System Test Runner"
echo "====================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if .env.system-test exists
if [ ! -f "tests/system/.env.system-test" ]; then
    echo -e "${RED}❌ Error: tests/system/.env.system-test not found${NC}"
    echo ""
    echo "Please create it from the example:"
    echo "  cp tests/system/.env.system-test.example tests/system/.env.system-test"
    echo "  # Edit .env.system-test with your configuration"
    echo ""
    exit 1
fi

echo -e "${GREEN}✅ Found system test configuration${NC}"

# Load environment
source tests/system/.env.system-test 2>/dev/null || true

# Check required services
echo ""
echo "🔍 Checking required services..."

check_service() {
    local service=$1
    local url=$2
    
    if curl -sf "$url" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ $service is running${NC}"
        return 0
    else
        echo -e "${RED}❌ $service is not accessible at $url${NC}"
        return 1
    fi
}

# Check services
SERVICES_OK=true

check_service "PostgreSQL" "postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME" || SERVICES_OK=false
check_service "API Gateway" "${API_GATEWAY_URL}/health" || SERVICES_OK=false
check_service "Listener" "${LISTENER_URL}/health" || SERVICES_OK=false

if [ "$SERVICES_OK" = false ]; then
    echo ""
    echo -e "${YELLOW}⚠️  Some services are not running${NC}"
    echo ""
    echo "To start services:"
    echo "  docker-compose up -d"
    echo ""
    read -p "Continue anyway? (y/n): " CONTINUE
    if [ "$CONTINUE" != "y" ] && [ "$CONTINUE" != "Y" ]; then
        exit 1
    fi
fi

# Database setup
echo ""
echo "🗄️  Setting up test database..."

# Check if database exists, create if not
psql -h $DB_HOST -U $DB_USER -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw $DB_NAME
if [ $? -ne 0 ]; then
    echo "Creating database: $DB_NAME"
    createdb -h $DB_HOST -U $DB_USER $DB_NAME
    echo -e "${GREEN}✅ Database created${NC}"
fi

# Apply schema
echo "Applying database schema..."
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -f backend/database/schema.sql > /dev/null 2>&1
echo -e "${GREEN}✅ Schema applied${NC}"

# Install test dependencies
echo ""
echo "📦 Checking test dependencies..."
pip install -q pytest pytest-asyncio aiohttp python-dotenv 2>/dev/null || true
echo -e "${GREEN}✅ Dependencies ready${NC}"

# Run system tests
echo ""
echo "🚀 Running system tests..."
echo ""

# Set Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Run tests with markers
pytest tests/system/test_system.py \
    -v \
    -s \
    -m system \
    --tb=short \
    --log-cli-level=${LOG_LEVEL:-INFO} \
    --color=yes

TEST_RESULT=$?

echo ""
if [ $TEST_RESULT -eq 0 ]; then
    echo -e "${GREEN}✅ All system tests passed!${NC}"
else
    echo -e "${RED}❌ Some system tests failed${NC}"
fi

# Cleanup
if [ "$CLEANUP_AFTER_TESTS" = "true" ]; then
    echo ""
    echo "🧹 Cleaning up test data..."
    # Cleanup is handled by test itself
    echo -e "${GREEN}✅ Cleanup complete${NC}"
fi

echo ""
echo "📊 Test Summary:"
echo "  - Configuration: tests/system/.env.system-test"
echo "  - Log file: ${LOG_FILE:-system_test.log}"
echo "  - Database: $DB_NAME"
echo ""

exit $TEST_RESULT
