document.addEventListener('DOMContentLoaded', function() {
    const tradingPairInput = document.getElementById('trading_pair');
    const editBtn = document.getElementById('editPairBtn');
    const cancelBtn = document.getElementById('cancelPairEdit');
    const saveBtn = document.getElementById('savePairBtn');
    const viewMode = document.getElementById('pairViewMode');
    const editMode = document.getElementById('pairEditMode');
    
    if (!tradingPairInput) return;
    
    console.log('Initializing trading pair selector');
    
    let tradingPairsLoaded = false;
    let tradingPairsData = [];

    // For new automations, load trading pairs immediately
    if (!viewMode || document.querySelector('form#createAutomationForm')) {
        console.log('New automation - loading trading pairs');
        initializeTradingPairs();
    }

    // Edit button handler
    if (editBtn) {
        console.log('Adding edit button handler');
        editBtn.addEventListener('click', function() {
            console.log('Edit button clicked');
            if (viewMode) viewMode.classList.add('d-none');
            if (editMode) editMode.classList.remove('d-none');
            if (!tradingPairsLoaded) {
                initializeTradingPairs();
            }
        });
    }

    // Save button handler
    if (saveBtn) {
        saveBtn.addEventListener('click', async function() {
            const automationId = document.querySelector('[data-automation-id]')?.dataset.automationId;
            if (!automationId) return;

            try {
                const response = await fetch(`/automation/${automationId}/trading-pair`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                    },
                    body: JSON.stringify({ trading_pair: tradingPairInput.value })
                });

                if (!response.ok) throw new Error('Failed to save trading pair');
                
                window.location.reload();
            } catch (error) {
                console.error('Error saving trading pair:', error);
                alert('Error saving trading pair. Please try again.');
            }
        });
    }

    // Cancel button handler
    if (cancelBtn) {
        cancelBtn.addEventListener('click', function() {
            viewMode.classList.remove('d-none');
            editMode.classList.add('d-none');
            tradingPairInput.value = tradingPairInput.defaultValue;
        });
    }

    async function initializeTradingPairs() {
        if (tradingPairsLoaded) return;

        // Add loading indicator
        const loadingIndicator = document.createElement('div');
        loadingIndicator.className = 'mt-2 text-muted';
        loadingIndicator.innerHTML = '<small>Loading trading pairs...</small>';
        tradingPairInput.parentNode.appendChild(loadingIndicator);

        try {
            const response = await fetch('/api/coinbase/trading-pairs', {
                method: 'GET',
                headers: {
                    'Accept': 'application/json'
                },
                credentials: 'same-origin'
            });

            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }

            const data = await response.json();
            
            if (!data.trading_pairs) {
                throw new Error('No trading pairs in response');
            }

            tradingPairsData = data.trading_pairs;
            tradingPairsLoaded = true;

            // Initialize autocomplete after data is loaded
            initializeAutocomplete();

            // Show success message
            const successElement = document.createElement('div');
            successElement.className = 'text-success mt-1';
            successElement.innerHTML = `<small>${tradingPairsData.length} trading pairs available</small>`;
            tradingPairInput.parentNode.appendChild(successElement);

        } catch (error) {
            console.error('Error fetching trading pairs:', error);
            const errorElement = document.createElement('div');
            errorElement.className = 'alert alert-danger mt-2';
            errorElement.textContent = 'Failed to fetch trading pairs: ' + error.message;
            tradingPairInput.parentNode.appendChild(errorElement);
        } finally {
            loadingIndicator.remove();
        }
    }

    function initializeAutocomplete() {
        $(tradingPairInput).autocomplete({
            source: function(request, response) {
                const term = request.term.toLowerCase();
                const matches = tradingPairsData.filter(pair => {
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
        });

        // Custom rendering for autocomplete dropdown
        $(tradingPairInput).autocomplete("instance")._renderItem = function(ul, item) {
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
    }
});