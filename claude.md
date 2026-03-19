# WebhookApp - Project Documentation for Claude

## Project Overview

**WebhookApp** is a sophisticated Flask-based cryptocurrency trading automation platform that enables users to:
- Connect multiple cryptocurrency exchanges (Coinbase, Binance, Kraken, Crypto.com)
- Create virtual trading strategies with allocated assets
- Execute trades via webhook triggers from TradingView
- Track portfolio performance with time-weighted rate of return (TWRR)
- Manage two-factor authentication and bot protection

**Tech Stack:**
- Backend: Flask 3.1.0, SQLAlchemy 2.0.36, Flask-Security-Too 5.6.0
- Exchange Integration: CCXT 4.4.86 (cryptocurrency exchange connector)
- Authentication: Flask-Security-Too with 2FA (TOTP), reCAPTCHA v2
- Database: SQLite (development and production)
- Task Scheduling: APScheduler 3.11.0
- Testing: pytest 8.3.5 with 100% passing test suite (111 tests)
- Deployment: Raspberry Pi with Gunicorn + Nginx + SSL

---

## Core Architecture

### Database Models (`app/models/`)

#### User Authentication
- **User** (`user.py`): Flask-Security user model with 2FA fields (tf_totp_secret, tf_primary_method, tf_recovery_codes)
- **Role**: User role management (admin, user)

#### Exchange & Credentials
- **ExchangeCredentials** (`exchange_credentials.py`): Stores encrypted API keys for exchanges (Coinbase, Binance, Kraken, Crypto.com)
  - Fields: user_id, exchange, api_key, api_secret, passphrase (optional)
  - Encrypted at rest using Fernet

#### Trading Strategies
- **TradingStrategy** (`trading.py`): Virtual portfolio configuration
  - Fields: user_id, name, exchange_credential_id, trading_pair, base_asset_symbol, quote_asset_symbol
  - Allocated quantities: allocated_base_asset_quantity, allocated_quote_asset_quantity
  - Webhook integration: webhook_id, webhook_template
  
- **StrategyValueHistory** (`trading.py`): Daily snapshots for performance tracking
  - Fields: strategy_id, date, value_usd, base_asset_quantity_snapshot, quote_asset_quantity_snapshot

#### Portfolio & Account
- **Portfolio** (`portfolio.py`): User's main account portfolio
  - Tracks total holdings across all exchanges
  
- **AccountCache** (`account_cache.py`): Cached exchange balances
  - Fields: user_id, exchange, asset_symbol, quantity, last_updated
  - 10-minute cache timeout

#### Webhooks & Logging
- **Webhook** (`webhook.py`): Webhook configuration for strategies
  - Fields: user_id, strategy_id, webhook_url, webhook_secret, is_active
  
- **WebhookLog** (`webhook.py`): Audit trail of all webhook executions
  - Fields: webhook_id, strategy_id, timestamp, payload, status, response, error_message

#### Legacy (Deprecated)
- **Automation** (`automation.py`): Legacy automation model (to be removed in Phase 6)

---

### Exchange Adapters (`app/exchanges/`)

All adapters inherit from `BaseAdapter` and implement standardized interface for exchange operations.

#### CCXT-Based Adapters (Primary)
- **CcxtBaseAdapter** (`ccxt_base_adapter.py`): Base class for all CCXT exchanges
  - Methods: get_client(), get_portfolio_value(), fetch_balance(), fetch_ticker()
  - Caching: 10-minute cache for client instances and portfolio values
  - Supports: Binance, Kraken, Crypto.com, Coinbase-CCXT
  
- **CcxtCoinbaseAdapter** (`ccxt_coinbase_adapter.py`): Coinbase-specific CCXT implementation
  - Handles Coinbase Advanced Trading API via CCXT
  - Passphrase support for API authentication

#### Native Adapters (Legacy)
- **CoinbaseAdapter** (`coinbase_adapter.py`): Legacy Coinbase REST API (deprecated in favor of CCXT)

#### Registry & Initialization
- **ExchangeRegistry** (`registry.py`): Singleton registry of available exchanges
- **init_exchanges.py**: Dynamically creates adapter classes for DEFAULT_CCXT_EXCHANGES
  - Supported exchanges: binance, kraken, cryptocom, coinbase-ccxt

---

### Services (`app/services/`)

#### Core Business Logic

**AllocationService** (`allocation_service.py`): Virtual portfolio asset management
- `allocate_assets()`: Transfer assets from main account to strategy
- `deallocate_assets()`: Transfer assets from strategy back to main account
- `transfer_between_strategies()`: Direct strategy-to-strategy transfers
- Validation: Prevents over-allocation, validates available balances
- Precision: Uses Decimal arithmetic with 18 decimal places, ROUND_HALF_EVEN rounding
- Max Transfer: Explicit `is_max_transfer` flag for exact balance transfers

**WebhookProcessor** (`webhook_processor.py`): Webhook execution engine
- `process_webhook()`: Main entry point for webhook handling
- Validates webhook signature, strategy state, trading pair
- Executes trades: Buys/sells 100% of allocated assets (capped by available balance)
- Updates strategy asset quantities post-trade
- Logs all webhook activity with timestamps and outcomes
- Pause/unpause support: Paused strategies reject webhooks with 403 status

**ExchangeService** (`exchange_service.py`): Exchange credential management
- `add_exchange_credentials()`: Validates and stores encrypted API keys
- `remove_exchange_credentials()`: Deletes credentials and associated strategies
- `get_portfolio_value()`: Aggregates portfolio across all exchanges
- Adapter selection: Automatically selects appropriate adapter for exchange

**StrategyValueService** (`strategy_value_service.py`): Performance tracking
- `calculate_daily_strategy_value()`: Computes daily strategy USD value
- `record_strategy_value_snapshot()`: Stores daily snapshots in strategy_value_history
- Cron job: Runs daily at 00:00 UTC via APScheduler
- Robustness: Retry logic with exponential backoff, price validation, zero-value protection

**PriceService** (`price_service.py`): Asset price fetching
- `get_price()`: Fetches current asset prices from CoinGecko
- Caching: Prices cached for 5 minutes
- Fallback: Returns None if price unavailable

**NotificationService** (`notification_service.py`): User notifications
- Email notifications for trade execution, errors, alerts
- Flask-Mail integration

---

### Routes (`app/routes/`)

#### Authentication & User Management
- **auth.py**: Login, logout, registration, password reset
  - Custom login form with rate limiting
  - reCAPTCHA integration for registration
  - Email verification enforcement

- **two_factor.py**: 2FA setup, verification, recovery
  - TOTP (Google Authenticator) setup with QR codes
  - Recovery codes generation and email delivery
  - Endpoints: /auth/setup-2fa, /auth/verify-2fa, /auth/recovery-2fa

#### Dashboard & Portfolio
- **dashboard.py**: Main dashboard, exchange page, settings
  - GET /dashboard: Main dashboard with portfolio summary
  - GET /exchange/<exchange_id>: Exchange-specific page with strategies
  - POST /settings: API key management, 2FA settings
  - GET /login-redirect: Post-login redirect logic

#### Trading Strategies
- **exchange.py**: Strategy creation, management, asset transfers
  - POST /exchange/<exchange_id>/strategy: Create new strategy
  - DELETE /exchange/<exchange_id>/strategy/<strategy_id>: Delete strategy
  - GET /exchange/<exchange_id>/strategy/<strategy_id>: Strategy details page
  - POST /api/transfer-assets: Asset transfer between accounts/strategies
  - GET /api/strategy/<strategy_id>/logs: Webhook logs for strategy

#### Webhooks
- **webhook.py**: Webhook reception and processing
  - POST /webhook/<webhook_id>: Receive and process webhook
  - Validates signature, delegates to WebhookProcessor
  - Returns 200 (success), 403 (paused), 404 (not found), 400 (invalid)

#### API Endpoints
- **api.py**: RESTful API for frontend
  - GET /api/portfolio: Portfolio summary
  - GET /api/exchange/<exchange_id>/portfolio: Exchange-specific portfolio
  - GET /api/strategy/<strategy_id>/performance: TWRR and performance metrics
  - GET /api/strategy/<strategy_id>/logs: Webhook logs
  - POST /api/transfer-assets: Asset transfers
  - GET /api/account-cache: Cached account balances

#### Admin
- **admin.py**: Admin dashboard and user management
  - GET /admin/strategies: List all strategies (admin only)
  - User suspension/unsuspension
  - System statistics

#### Debug Routes
- **debug.py**: Development debugging endpoints
- **template_debug.py**: Template testing utilities

---

### Frontend Templates (`app/templates/`)

#### Core Pages
- **base.html**: Base template with navigation, Google Analytics, reCAPTCHA script
- **dashboard.html**: Main dashboard with portfolio summary and exchange list
- **exchange.html**: Exchange page with strategy list and asset display
- **strategy_details.html**: Strategy details with performance chart and logs

#### Authentication
- **security/login_user.html**: Login form with custom styling
- **security/register_user.html**: Registration with reCAPTCHA widget
- **security/forgot_password.html**: Password reset request
- **security/reset_password.html**: Password reset form

#### 2FA
- **security/two_factor_setup.html**: TOTP setup with QR code
- **security/two_factor_verify_code.html**: TOTP verification during login
- **security/two_factor_recovery.html**: Recovery code display
- **security/two_factor_rescue.html**: Email recovery template

#### Settings
- **settings.html**: User settings, API key management, 2FA configuration
  - Dynamic exchange forms (Binance, Kraken, Crypto.com, Coinbase-CCXT)
  - Add/delete API keys modals
  - Password change form

#### Modals & Components
- **exchange_transfers.html**: Asset transfer modal (Main ↔ Strategy ↔ Strategy)
- **strategy_creation_modal.html**: Create new strategy form
- **strategy_deletion_modal.html**: Confirm strategy deletion

---

## Key Features & Implementation Details

### 1. Virtual Portfolio System

**Concept:** Each trading strategy is a virtual portfolio with allocated base and quote assets.

**Allocation Flow:**
1. User transfers assets from main account to strategy (via AllocationService)
2. Strategy receives allocated_base_asset_quantity and allocated_quote_asset_quantity
3. Trades execute using only allocated assets (100% of one asset, capped by available)
4. Strategy asset quantities update post-trade
5. User can transfer assets back to main account or to other strategies

**Precision Handling:**
- All amounts use Python Decimal with 18 decimal places
- Consistent rounding: ROUND_HALF_EVEN (mathematical standard)
- Max transfer flag: `is_max_transfer=true` bypasses all precision comparisons
- Quantization: Both transfer amount and available balance quantized before comparison

### 2. Webhook Processing

**Flow:**
1. TradingView sends webhook to `/webhook/<webhook_id>`
2. Signature validation (HMAC-SHA256)
3. Strategy lookup and state validation (not paused, exists)
4. Webhook payload parsing (expects "ticker" field matching strategy trading_pair)
5. Trade execution via exchange adapter
6. Strategy asset quantities updated
7. WebhookLog entry created for audit trail

**Trade Logic:**
- Buy: Sell quote asset, buy base asset (100% of quote, capped by available)
- Sell: Sell base asset, buy quote asset (100% of base, capped by available)
- All trades are market orders (100% of allocated asset)

**Pause/Unpause:**
- Paused strategies reject webhooks with 403 Forbidden
- Pause state stored in TradingStrategy model
- Immediate effect on webhook processing

### 3. Performance Tracking (TWRR)

**Time-Weighted Rate of Return (TWRR):**
- Measures trading performance independent of deposits/withdrawals
- Formula: (ending_value - cash_flows) / beginning_value - 1
- Cash flows (transfers) are completely excluded from calculations
- Daily snapshots stored in StrategyValueHistory

**Implementation:**
- Cron job runs daily at 00:00 UTC
- Fetches current portfolio value via exchange adapter
- Stores: value_usd, base_asset_quantity_snapshot, quote_asset_quantity_snapshot
- Robustness: Retry logic, price validation, zero-value protection
- Inclusive interval logic: `start_time <= timestamp <= end_time` (handles boundary cases)

**Sanity Checks:**
- Warning if value changes >$100 but no cash flow detected
- Helps identify data integrity issues early

### 4. Authentication & Security

**Flask-Security-Too Integration:**
- User registration with email verification
- Password requirements: 8+ chars, uppercase, lowercase, numbers, special chars
- Session management: 24-hour persistent sessions

**Two-Factor Authentication (2FA):**
- TOTP (Google Authenticator) support
- QR code generation for setup
- Recovery codes (10 codes, 8 characters each)
- Email-based recovery option
- Optional (user opt-in)

**Bot Protection:**
- reCAPTCHA v2 on registration (optional, graceful fallback)
- Rate limiting: 3/minute, 10/hour per IP on /register
- User agent detection: Blocks obvious bot agents
- Email verification enforcement

**API Key Security:**
- Encrypted at rest using Fernet (symmetric encryption)
- Stored in ExchangeCredentials table
- Passphrase support for exchanges requiring it (e.g., Coinbase)

### 5. Exchange Adapter System

**Adapter Pattern:**
- All adapters implement BaseAdapter interface
- CCXT adapters wrap CCXT library for standardized API
- Registry pattern for dynamic adapter selection

**Supported Exchanges:**
- Binance (CCXT)
- Kraken (CCXT)
- Crypto.com (CCXT)
- Coinbase (CCXT via coinbase-ccxt, legacy native adapter deprecated)

**Caching:**
- CCXT client instances: 10-minute cache
- Portfolio values: 10-minute cache
- Reduces external API calls during dashboard loads

**Key Methods:**
- `get_client()`: Returns CCXT exchange client with loaded markets
- `get_portfolio_value()`: Returns dict with total_usd, assets (symbol: quantity)
- `fetch_balance()`: Returns account balances
- `fetch_ticker()`: Returns current price for trading pair

---

## Development Workflow

### Running the Application

```bash
# Activate virtual environment
source venv/bin/activate

# Development server
python run.py  # Runs on http://localhost:5000

# Production server (Raspberry Pi)
./deploy.sh  # Deploys to production with SSL
```

### Database Migrations

```bash
# Create new migration
flask db migrate -m "Description of change"

# Apply migrations
flask db upgrade

# View current revision
flask db current

# Stamp database with current head (if out of sync)
flask db stamp head
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_webhook_processor.py

# Run specific test
pytest tests/test_webhook_processor.py::test_webhook_pause_logic
```

**Test Suite Status:** 111 passing tests (100% pass rate), 40% code coverage

### Configuration

**Environment Variables** (`.env`):
```
FLASK_ENV=development
SECRET_KEY=<generated-or-set>
SECURITY_PASSWORD_SALT=<random-string>
DATABASE_URL=sqlite:///instance/webhook.db
APPLICATION_URL=http://localhost:5000

# Email
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_DEFAULT_SENDER=noreply@webhookapp.com

# reCAPTCHA
RECAPTCHA_SITE_KEY=<google-recaptcha-site-key>
RECAPTCHA_SECRET_KEY=<google-recaptcha-secret-key>

# 2FA
SECURITY_TWO_FACTOR_SECRET_KEY=<random-string>
```

---

## Common Tasks & Patterns

### Adding a New Exchange

1. **Verify CCXT Support:** Check if exchange is in CCXT library
2. **Add to DEFAULT_CCXT_EXCHANGES** in `app/exchanges/init_exchanges.py`
3. **Create SVG Logo:** Add `static/images/exchanges/<exchange-name>.svg`
4. **Update Settings Template:** Add form section in `app/templates/settings.html`
5. **Test:** Verify API key validation and portfolio fetching

### Creating a Trading Strategy

1. User navigates to exchange page (`/exchange/<exchange_id>`)
2. Clicks "Create Strategy" button
3. Fills form: Name, Trading Pair (e.g., "BTC/USD")
4. Backend validates pair exists on exchange
5. TradingStrategy record created with webhook_id
6. Webhook URL provided to user for TradingView

### Executing a Trade via Webhook

1. TradingView sends POST to `/webhook/<webhook_id>`
2. WebhookProcessor validates signature and strategy state
3. Fetches strategy's allocated assets
4. Executes trade (buy/sell 100% of one asset)
5. Updates strategy's allocated quantities
6. WebhookLog created for audit trail
7. Returns 200 with trade details

### Transferring Assets Between Accounts

1. User clicks "Transfer" on main account or strategy
2. Modal opens with source/destination/asset/amount fields
3. "Max" button sets amount to available balance
4. User submits form via AJAX
5. AllocationService validates and executes transfer
6. AccountCache updated
7. Modal closes, UI refreshes

---

## Deployment

### Raspberry Pi Production Setup

**Server Stack:**
- Gunicorn: WSGI application server
- Nginx: Reverse proxy with SSL
- Systemd: Service management
- APScheduler: Scheduled tasks (daily value snapshots)

**Deployment Process:**
```bash
# On development machine
git push origin main
./deploy.sh
# Deploys to Raspberry Pi: git pull, flask db upgrade, systemctl restart webhookapp
```

**SSL Certificates:**
- Let's Encrypt via Certbot
- Auto-renewal via systemd timer
- Paths: `/etc/letsencrypt/live/app.wekwerth.services/`

**Monitoring:**
- Google Analytics: Tracks page views, user sessions, traffic
- Nginx logs: Bot traffic analysis via `scripts/monitor_bot_traffic.py`
- Application logs: Flask debug logging

---

## Known Issues & Limitations

### TWRR Edge Cases
- Transfers occurring after last snapshot assigned to final interval
- Inclusive interval logic handles microsecond-level timing precision
- Sanity check warns if value changes >$100 without cash flow

### Decimal Precision
- All amounts use 18 decimal places (cryptocurrency standard)
- Consistent ROUND_HALF_EVEN rounding across all services
- Max transfer flag bypasses precision comparisons for exact balance transfers

### Exchange API Limitations
- CCXT rate limits: Varies by exchange (typically 10-100 requests/minute)
- Portfolio value caching: 10 minutes to reduce API calls
- Price fetching: CoinGecko API with 5-minute cache

---

## Testing Strategy

### Test Categories

1. **Core Business Logic** (9 tests): Asset allocation, trade validation, conservation rules
2. **Webhook Processing** (8 tests): Pause/unpause, deletion, edge cases
3. **Route-Level Management** (3 tests): Toggle, delete, unauthorized access
4. **Exchange Credentials** (4 tests): Add/remove, validation, protection
5. **Authentication & Admin** (21 tests): Login, registration, 2FA, admin access
6. **Integration Tests** (14 tests): Webhook processor, asset transfers, portfolio math
7. **Other Coverage** (12 tests): Adapters, templates, utilities

### Test Isolation
- In-memory SQLite database for each test
- Mock exchange adapters (DummyBalanceAdapter)
- Proper session management to prevent DetachedInstanceError
- Fixtures for users, strategies, credentials

### Running Tests
```bash
# All tests
pytest

# With coverage report
pytest --cov=app --cov-report=html

# Specific test file
pytest tests/test_allocation_service.py -v

# Specific test
pytest tests/test_allocation_service.py::test_allocate_assets -v
```

---

## Future Roadmap (Phase 6+)

- **Automations Cleanup:** Migrate/archive legacy automations table
- **Dashboard Trading Strategies Table:** Replace automations with strategies summary
- **Advanced Charts:** Enhanced performance visualization
- **Strategy Templates:** Pre-built strategy configurations
- **Backtesting:** Historical performance analysis
- **Multi-Account Support:** Multiple main accounts per user

---

## Useful References

- **CCXT Documentation:** https://docs.ccxt.com/
- **Flask-Security-Too:** https://flask-security-too.readthedocs.io/
- **SQLAlchemy:** https://docs.sqlalchemy.org/
- **APScheduler:** https://apscheduler.readthedocs.io/
- **CoinGecko API:** https://www.coingecko.com/en/api/documentation

---

## Maintenance & Updates

This file should be updated when:

**Architecture Changes:**
- New models added to `app/models/`
- New routes or blueprints created in `app/routes/`
- New services added to `app/services/`
- Exchange adapters added or removed from `app/exchanges/`
- Major refactoring of core business logic

**Dependency Updates:**
- Major version bumps in `requirements.txt` (Flask, SQLAlchemy, CCXT, etc.)
- New critical dependencies added
- Python version changes

**Test Suite Changes:**
- Test count changes significantly (>10 tests added/removed)
- Code coverage percentage changes by >1%
- Major test suite restructuring

**Deployment Changes:**
- Database migration strategy changes
- Deployment process or infrastructure changes
- New environment variables required
- SSL/security configuration changes

**Documentation Gaps:**
- New features not documented in this file
- Unclear or outdated sections identified during development
- New API endpoints or webhook formats

---

## Contact & Support

For questions about specific components, refer to:
- Route logic: `app/routes/`
- Business logic: `app/services/`
- Database models: `app/models/`
- Exchange integration: `app/exchanges/`
- Tests: `tests/`


## Commit Message and PR Description Format

Use only the AI attribution trailer in commit messages and PR descriptions (no Claude Code signature or Co-Authored-By):

```
Assisted-by: Claude <noreply@anthropic.com>
```

Do not include the `🤖 Generated with Claude Code` signature or `Co-Authored-By: Claude` line in commit messages or PR descriptions.