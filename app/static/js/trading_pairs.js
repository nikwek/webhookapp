// app/static/js/trading_pairs.js
document.addEventListener('DOMContentLoaded', function() {
    // Trading Pair Manager
    const TradingPairManager = {
        init() {
            this.section = document.getElementById('tradingPairSection');
            if (!this.section) return;
            
            this.form = document.getElementById('tradingPairForm');
            this.input = document.getElementById('trading-pair-input');
            this.hiddenField = document.getElementById('trading-pair');
            this.suggestions = document.getElementById('trading-pair-suggestions');
            this.automationId = this.section.dataset.automationId;
            
            this.allTradingPairs = [];
            this.isLoading = true;
            
            this.setupEventListeners();
            this.loadTradingPairs();
            this.checkTradingPairStatus();
        },
        
        async checkTradingPairStatus() {
            try {
                const response = await fetch(`/automation/${this.automationId}/trading-pair`);
                const data = await response.json();
                
                if (response.ok && data.trading_pair) {
                    // Trading pair already set, show it
                    this.showCurrentTradingPair(data.trading_pair, data.display_name);
                } else if (document.querySelector('.delete-credential')) {
                    // No trading pair yet, but portfolio is connected, show the form
                    this.section.style.display = 'block';
                }
            } catch (error) {
                console.error('Error checking trading pair status:', error);
            }
        },
        
        showCurrentTradingPair(pairId, displayName) {
            // Replace the form with the current trading pair display
            this.section.innerHTML = `
                <h5 class="mt-4">Trading Pair</h5>
                <div class="border rounded p-3 mb-2">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <strong>${displayName || pairId}</strong>
                        </div>
                        <div>
                            <button class="btn btn-sm btn-secondary edit-trading-pair">
                                <i class="fas fa-pencil-alt"></i> Change
                            </button>
                        </div>
                    </div>
                </div>
            `;
            
            this.section.style.display = 'block';
            
            // Add event listener for edit button
            const editBtn = this.section.querySelector('.edit-trading-pair');
            if (editBtn) {
                editBtn.addEventListener('click', () => {
                    this.section.innerHTML = this.createTradingPairForm();
                    this.init(); // Reinitialize manager
                });
            }
        },
        
        createTradingPairForm() {
            return `
                <h5 class="mt-4">Trading Pair</h5>
                <div class="mb-4">
                    <form id="tradingPairForm">
                        <div class="mb-3">
                            <label for="trading-pair-input" class="form-label">Select Trading Pair</label>
                            <div class="trading-pair-container">
                                <input type="text" class="form-control" id="trading-pair-input" 
                                       placeholder="Enter trading pair (e.g., BTC-USD)" required>
                                <input type="hidden" id="trading-pair" name="trading_pair">
                                <div id="trading-pair-suggestions" class="trading-pair-suggestions"></div>
                            </div>
                            <div class="form-text">
                                This is the cryptocurrency pair you want to trade (e.g., BTC-USD for Bitcoin/US Dollar)
                            </div>
                        </div>
                        <button type="submit" class="btn btn-primary">
                            Save Trading Pair
                        </button>
                    </form>
                </div>
            `;
        },
        
        async loadTradingPairs() {
            try {
                this.input.placeholder = "Loading trading pairs...";
                this.isLoading = true;
                
                const response = await fetch('/portfolio/api/trading-pairs');
                if (!response.ok) {
                    throw new Error('Failed to fetch trading pairs');
                }
                
                this.allTradingPairs = await response.json();
                this.isLoading = false;
                this.input.placeholder = "Enter trading pair (e.g., BTC-USD)";
                console.log(`Loaded ${this.allTradingPairs.length} trading pairs`);
            } catch (error) {
                console.error('Error fetching trading pairs:', error);
                this.isLoading = false;
                this.input.placeholder = "Error loading pairs. Try again later.";
            }
        },
        
        setupEventListeners() {
            // Handle input in the trading pair field
            this.input.addEventListener('input', () => {
                if (this.isLoading) return;
                
                const query = this.input.value.toUpperCase();
                
                // Clear suggestions if input is empty
                if (!query) {
                    this.suggestions.innerHTML = '';
                    this.suggestions.style.display = 'none';
                    return;
                }
                
                // Filter trading pairs based on the query
                const filteredPairs = this.allTradingPairs.filter(pair => {
                    return pair.id.toUpperCase().includes(query) || 
                          pair.display_name.toUpperCase().includes(query) ||
                          pair.base_name.toUpperCase().includes(query) ||
                          pair.quote_name.toUpperCase().includes(query);
                }).slice(0, 10); // Limit to 10 suggestions
                
                // Create and display suggestions
                this.suggestions.innerHTML = '';
                
                if (filteredPairs.length > 0) {
                    filteredPairs.forEach(pair => {
                        const div = document.createElement('div');
                        div.className = 'suggestion-item';
                        div.innerHTML = `<strong>${pair.display_name}</strong> (${pair.base_name}/${pair.quote_name})`;
                        div.dataset.pairId = pair.id;
                        
                        div.addEventListener('click', () => {
                            this.input.value = pair.display_name;
                            this.hiddenField.value = pair.id;
                            this.suggestions.innerHTML = '';
                            this.suggestions.style.display = 'none';
                        });
                        
                        this.suggestions.appendChild(div);
                    });
                    
                    this.suggestions.style.display = 'block';
                } else {
                    this.suggestions.style.display = 'none';
                }
            });
            
            // Hide suggestions when clicking outside
            document.addEventListener('click', (e) => {
                if (e.target !== this.input && e.target !== this.suggestions) {
                    this.suggestions.innerHTML = '';
                    this.suggestions.style.display = 'none';
                }
            });
            
            // Handle form submission
            if (this.form) {
                this.form.addEventListener('submit', async (e) => {
                    e.preventDefault();
                    
                    if (!this.hiddenField.value) {
                        alert('Please select a trading pair');
                        return;
                    }
                    
                    const submitButton = this.form.querySelector('button[type="submit"]');
                    submitButton.disabled = true;
                    
                    try {
                        const tradingPair = this.hiddenField.value;
                        const displayName = this.input.value;
                        
                        const response = await fetch(`/automation/${this.automationId}/trading-pair`, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({
                                trading_pair: tradingPair
                            })
                        });
                        
                        const data = await response.json();
                        
                        if (!response.ok) {
                            throw new Error(data.error || 'Failed to save trading pair');
                        }
                        
                        // Show success alert
                        const alert = document.createElement('div');
                        alert.className = 'alert alert-success alert-dismissible fade show mt-3';
                        alert.innerHTML = `
                            Trading pair saved successfully!
                            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                        `;
                        this.section.appendChild(alert);
                        
                        // Replace form with current trading pair display
                        setTimeout(() => {
                            this.showCurrentTradingPair(tradingPair, displayName);
                        }, 1500);
                        
                    } catch (error) {
                        console.error('Error saving trading pair:', error);
                        alert(`Error saving trading pair: ${error.message}`);
                    } finally {
                        submitButton.disabled = false;
                    }
                });
            }
        }
    };
    
    // Check if we're on the automation page and initialize if needed
    const tradingPairSection = document.getElementById('tradingPairSection');
    if (tradingPairSection) {
        // Initialize manager after credentials are loaded
        // This ensures the section is only shown if a portfolio is connected
        const checkCredentials = setInterval(() => {
            const credentialsContainer = document.getElementById('credentialsContainer');
            if (credentialsContainer && credentialsContainer.querySelector('.delete-credential')) {
                TradingPairManager.init();
                clearInterval(checkCredentials);
            }
        }, 500);
    }
});
