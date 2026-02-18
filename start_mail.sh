#!/bin/bash

# --- Configuration ---
APP_NAME="CrossMailer"
MAIN_SCRIPT="run_crossmailer.py"
VENV_PYTHON="venv/bin/python"
TRACKING_PORT=5000

# --- Visual Colors ---
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# --- Animations ---
spinner() {
    local pid=$1
    local delay=0.1
    local spinstr='|/-'
    echo -n " "
    while [ "$(ps a | awk '{print $1}' | grep $pid)" ]; do
        local temp=${spinstr#?}
        printf " [%c]  " "$spinstr"
        local spinstr=$temp${spinstr%"$temp"}
        sleep $delay
        printf "\b\b\b\b\b\b"
    done
    printf "    \b\b\b\b"
}

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# --- Execution ---

clear
echo -e "${BOLD}${BLUE}"
echo "  🚀 $APP_NAME - Deployment Initialized"
echo "  ======================================"
echo -e "${NC}"

# 1. Cleanup existing instances
print_status "Closing existing $APP_NAME instances..."
pkill -f "$MAIN_SCRIPT" 2>/dev/null &
spinner $!
print_success "Old instances terminated."

# 2. Clearing Port
print_status "Checking Tracking Port ($TRACKING_PORT)..."
PORT_PID=$(lsof -t -i:$TRACKING_PORT)
if [ ! -z "$PORT_PID" ]; then
    echo -e "${YELLOW}[!]${NC} Port $TRACKING_PORT occupied by PID $PORT_PID. Killing..."
    kill -9 $PORT_PID 2>/dev/null
    sleep 1
fi
print_success "Port $TRACKING_PORT is clear."

# 3. Environment Check
print_status "Verifying Virtual Environment..."
if [ ! -f "$VENV_PYTHON" ]; then
    print_error "Virtual environment not found at $VENV_PYTHON"
    exit 1
fi
print_success "Environment verified."

# 4. Dependency Check
print_status "Checking core dependencies..."
$VENV_PYTHON -c "import PyQt5, flask, llama_cpp" 2>/dev/null &
spinner $!
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}[!]${NC} Some dependencies might be missing. Attempting startup anyway..."
fi

# 5. Launch
echo -e "
${BOLD}${GREEN}  ==> DEPLOYING $APP_NAME BRAIN...${NC}
"

# We run in the background but redirect output to a log file for "verbose" observation
# Use setsid to ensure it doesn't die when the terminal closes if desired, 
# but here we keep it simple for the user to see the logs.

$VENV_PYTHON -u "$MAIN_SCRIPT" > app_startup.log 2>&1 &
APP_PID=$!

# Brief wait to see if it crashes immediately
sleep 2
if ps -p $APP_PID > /dev/null; then
    print_success "$APP_NAME is now running (PID: $APP_PID)."
    echo -e "${BLUE}[VERBOSE]${NC} Monitoring startup logs..."
    head -n 20 app_startup.log
    echo -e "
${YELLOW}Note: Check your desktop for the Master Passphrase prompt!${NC}"
else
    print_error "Application failed to start. Check 'app_startup.log' for details."
    cat app_startup.log
    exit 1
fi

echo -e "
${BOLD}${BLUE}  ======================================${NC}"
echo -e "  🌟 System Operational. Happy Mailing."
echo -e "${BOLD}${BLUE}  ======================================${NC}
"
