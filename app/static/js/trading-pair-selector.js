// app/static/js/trading-pair-selector.js
document.addEventListener('DOMContentLoaded', function() {
    initTradingPairSelector();
});

function initTradingPairSelector() {
    const tradingPairContainer = document.getElementById('trading-pair-container');
    if (!tradingPairContainer) return;
    
    // Create and add the trading pair selector components
    const selectorHtml = `
        <div class="form-group mt-3">
            <label for="trading-pair-input" class="form-label">Trading Pair</label>
            <div class="trading-pair-select" id="trading-pair-select">
                <input type="text" class="form-control" id="trading-pair-input" 
                       placeholder="Start typing (e.g. BTC-USD, ETH-USDT)" autocomplete="off">
                <input type="hidden" id="trading_pair" name="trading_pair">
                <div class="trading-pair-results" id="trading-pair-results"></div>
            </div>
            <small class="form-text text-muted">
                Select the trading pair for this automation. This determines which assets will be traded.
            </small>
        </div>
    `;
    
    tradingPairContainer.innerHTML = selectorHtml;
    
    // Now that the elements are in the DOM, set up the functionality
    const tradingPairInput = document.getElementById('trading-pair-input');
    const tradingPairSelect = document.getElementById('trading-pair-select');
    const tradingPairResults = document.getElementById('trading-pair-results');
    const tradingPairHiddenInput = document.getElementById('trading_pair');
    let tradingPairs = [];

    // Fetch trading pairs from the API
    fetchTradingPairs().then(pairs => {
        tradingPairs = pairs;
        console.log(`Loaded ${tradingPairs.length} trading pairs`);
        
        // If there's a pre-selected value, make sure it's in the hidden input
        if (tradingPairInput.value) {
            tradingPairHiddenInput.value = tradingPairInput.value;
        }
    });

    // Set up input event listeners
    tradingPairInput.addEventListener('input', function() {
        const results = filterTradingPairs(this.value);
        displayResults(results);
    });
    
    tradingPairInput.addEventListener('focus', function() {
        if (this.value) {
            const results = filterTradingPairs(this.value);
            displayResults(results);
        }
    });
    
    // Close dropdown when clicking outside
    document.addEventListener('click', function(event) {
        if (!tradingPairSelect.contains(event.target)) {
            tradingPairResults.style.display = 'none';
        }
    });
}

// Fetch trading pairs from the API
async function fetchTradingPairs() {
    try {
        console.log('Fetching trading pairs...');
        const response = await fetch('/api/coinbase/trading-pairs');
        const data = await response.json();
        
        if (data.success) {
            console.log(`Retrieved ${data.trading_pairs.length} trading pairs`);
            return data.trading_pairs;
        } else {
            console.error('Failed to fetch trading pairs:', data.message);
            // Show error to user
            const tradingPairSelect = document.getElementById('trading-pair-select');
            if (tradingPairSelect) {
                const errorDiv = document.createElement('div');
                errorDiv.className = 'alert alert-danger mt-2';
                errorDiv.textContent = 'Error loading trading pairs. Please check your API credentials.';
                tradingPairSelect.appendChild(errorDiv);
            }
            return [];
        }
    } catch (error) {
        console.error('Error fetching trading pairs:', error);
        return [];
    }
}

// Filter trading pairs based on search input
function filterTradingPairs(searchTerm) {
    if (!searchTerm) return [];
    
    const term = searchTerm.toUpperCase();
    const tradingPairs = window.tradingPairs || [];
    
    return tradingPairs.filter(pair => 
        pair.product_id.toUpperCase().includes(term) ||
        pair.base_currency.toUpperCase().includes(term) ||
        pair.quote_currency.toUpperCase().includes(term)
    ).slice(0, 10); // Limit to 10 results for performance
}

// Display trading pair search results
function displayResults(results) {
    const tradingPairResults = document.getElementById('trading-pair-results');
    if (!tradingPairResults) return;
    
    // Clear previous results
    tradingPairResults.innerHTML = '';
    tradingPairResults.style.display = results.length ? 'block' : 'none';
    
    // Create result items
    results.forEach(pair => {
        const item = document.createElement('div');
        item.className = 'dropdown-item';
        item.textContent = pair.product_id;
        item.addEventListener('click', () => {
            selectTradingPair(pair);
        });
        tradingPairResults.appendChild(item);
    });
}

// Handle trading pair selection
function selectTradingPair(pair) {
    const tradingPairInput = document.getElementById('trading-pair-input');
    const tradingPairHiddenInput = document.getElementById('trading_pair');
    const tradingPairResults = document.getElementById('trading-pair-results');
    
    if (tradingPairInput && tradingPairHiddenInput) {
        tradingPairInput.value = pair.product_id;
        tradingPairHiddenInput.value = pair.product_id;
        if (tradingPairResults) {
            tradingPairResults.style.display = 'none';
        }
    }
}

// Set global trading pairs variable so it can be accessed by filtering function
window.tradingPairs = [];