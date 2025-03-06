// trading-pair-selector.js

document.addEventListener('DOMContentLoaded', function() {
    const tradingPairInput = document.getElementById('trading_pair');
    if (!tradingPairInput) return;
    
    console.log('Initializing trading pair selector');
    
    // Add loading indicator
    const loadingIndicator = document.createElement('div');
    loadingIndicator.className = 'mt-2 text-muted';
    loadingIndicator.innerHTML = '<small>Loading trading pairs...</small>';
    tradingPairInput.parentNode.appendChild(loadingIndicator);
    
    // Function to fetch trading pairs
    function fetchTradingPairs() {
        console.log('Fetching trading pairs...');
        
        // Fetch trading pairs
        return fetch('/api/coinbase/trading-pairs', {
            method: 'GET',
            headers: {
                'Accept': 'application/json'
            },
            credentials: 'same-origin'
        })
        .then(response => {
            if (!response.ok) {
                console.error('Response not OK:', response.status, response.statusText);
                return response.text().then(text => {
                    console.error('Response body:', text);
                    throw new Error(`HTTP error! Status: ${response.status}`);
                });
            }
            return response.json();
        })
        .then(data => {
            console.log('Trading pairs response received:', data);
            
            // Remove loading indicator
            loadingIndicator.remove();
            
            if (!data.success) {
                console.error('API reported error:', data.message);
                throw new Error(data.message || 'Unknown error');
            }
            
            const tradingPairs = data.trading_pairs || [];
            console.log(`Trading pairs loaded: ${tradingPairs.length}`);
            
            if (tradingPairs.length === 0) {
                console.warn('No trading pairs were returned');
                const warningElement = document.createElement('div');
                warningElement.className = 'alert alert-warning mt-2';
                warningElement.textContent = 'No trading pairs available. Please check your Coinbase API connection.';
                tradingPairInput.parentNode.appendChild(warningElement);
                return [];
            }
            
            return tradingPairs;
        })
        .catch(error => {
            // Remove loading indicator
            loadingIndicator.remove();
            
            console.error('Error fetching trading pairs:', error);
            const errorElement = document.createElement('div');
            errorElement.className = 'alert alert-danger mt-2';
            errorElement.textContent = 'Failed to fetch trading pairs: ' + error.message;
            tradingPairInput.parentNode.appendChild(errorElement);
            return [];
        });
    }
    
    // Initialize autocomplete with trading pairs
    fetchTradingPairs().then(tradingPairs => {
        if (tradingPairs.length === 0) return;
        
        // Log sample data for debugging
        console.log('Sample trading pair:', tradingPairs[0]);
        
        // Initialize jQuery UI autocomplete
        $(tradingPairInput).autocomplete({
            source: function(request, response) {
                const term = request.term.toLowerCase();
                const matches = tradingPairs.filter(pair => {
                    const displayName = pair.display_name || '';
                    const baseCurrency = pair.base_currency || '';
                    const quoteCurrency = pair.quote_currency || '';
                    
                    return displayName.toLowerCase().includes(term) || 
                           baseCurrency.toLowerCase().includes(term) || 
                           quoteCurrency.toLowerCase().includes(term);
                });
                
                // Limit to 15 results for better UI
                response(matches.slice(0, 15));
            },
            minLength: 2,
            select: function(event, ui) {
                event.preventDefault();
                
                // Update the visible input field with the display name
                $(this).val(ui.item.display_name);
                
                // Store the product ID in a hidden field
                const hiddenField = document.getElementById('trading_pair_id');
                if (hiddenField) {
                    hiddenField.value = ui.item.id || ui.item.product_id;
                } else {
                    // Create hidden field if it doesn't exist
                    const newHiddenField = document.createElement('input');
                    newHiddenField.type = 'hidden';
                    newHiddenField.id = 'trading_pair_id';
                    newHiddenField.name = 'trading_pair_id';
                    newHiddenField.value = ui.item.id || ui.item.product_id;
                    tradingPairInput.parentNode.appendChild(newHiddenField);
                }
                
                return false; // Prevent default behavior
            }

        .autocomplete("instance")._renderItem = function(ul, item) {
            // Ensure item has all required properties
            const displayName = item.display_name || item.product_id || '';
            const baseCurrency = item.base_currency || '';
            const quoteCurrency = item.quote_currency || '';
            
            // Custom rendering with better styling for dropdown items
            return $("<li>")
                .append(`<div class="ui-menu-item-wrapper" style="padding: 5px;">
                    <strong>${displayName}</strong>
                    <span class="text-muted ms-2">${baseCurrency}/${quoteCurrency}</span>
                </div>`)
                .appendTo(ul);
        };
        
        // Show success message
        const successElement = document.createElement('div');
        successElement.className = 'text-success mt-1';
        successElement.innerHTML = `<small>${tradingPairs.length} trading pairs available</small>`;
        tradingPairInput.parentNode.appendChild(successElement);
    });
});
