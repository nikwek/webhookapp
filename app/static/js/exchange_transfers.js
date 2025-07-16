// JavaScript for asset transfer modal on the exchange page
document.addEventListener('DOMContentLoaded', function () {
    console.log('Exchange transfers JS loaded');

    const assetTransferModal = new bootstrap.Modal(document.getElementById('assetTransferModal'));
    const transferForm = document.getElementById('assetTransferForm');
    const sourceAccountSelect = document.getElementById('transferSourceAccount');
    const destinationAccountSelect = document.getElementById('transferDestinationAccount');
    const assetSelect = document.getElementById('transferAssetSelect');
    const assetSymbolHiddenInput = document.getElementById('transferAssetSymbolHidden');
    const amountInput = document.getElementById('transferAmount');
    const maxButton = document.getElementById('transferMaxButton');
    const modalTitle = document.getElementById('assetTransferModalLabel');
    const availableToTransferSpan = document.getElementById('availableToTransfer');
    const transferingAssetSymbolDisplaySpan = document.getElementById('transferingAssetSymbolDisplay');
    const submitTransferButton = document.getElementById('submitTransferButton');

    // Store all strategies data passed from the template
    let allStrategiesOnPage = [];
    let allMainAccountAssetsOnPage = [];
    let currentCredentialId = null;

    // Listen for clicks on the new consolidated strategy transfer buttons
    document.querySelectorAll('.strategy-transfer-button').forEach(button => {
        button.addEventListener('click', function() {
            console.log('Strategy transfer button clicked. Dataset:', JSON.parse(JSON.stringify(this.dataset)));
            
            const transferType = this.dataset.transferType;
            const strategyId = this.dataset.strategyId;
            const strategyName = this.dataset.strategyName;
            const baseAssetSymbol = this.dataset.baseAssetSymbol;
            const baseAssetQuantity = parseFloat(this.dataset.baseAssetQuantity || 0);
            const quoteAssetSymbol = this.dataset.quoteAssetSymbol;
            const quoteAssetQuantity = parseFloat(this.dataset.quoteAssetQuantity || 0);
            const credentialId = this.dataset.credentialId;
            
            transferForm.dataset.currentTransferType = transferType;
            
            // Base URL for form action - get current exchange_id from URL
            const currentExchangeId = window.location.pathname.split('/')[2]; // Assumes URL like /exchange/some_id
            transferForm.action = `/exchange/${currentExchangeId}/transfer`;
            
            // Set modal title
            modalTitle.textContent = 'Transfer Assets';
            
            // Clear previous selections
            sourceAccountSelect.innerHTML = '';
            destinationAccountSelect.innerHTML = '';
            
            // Populate source dropdown (Main accounts and all strategies)
            populateSourceDropdown(credentialId);
            
            // Pre-select the source strategy
            sourceAccountSelect.value = `strategy::${strategyId}`;
            
            // Clear and populate asset selection dropdown based on the strategy
            assetSelect.innerHTML = '';
            
            // Add base asset option if available
            if (baseAssetSymbol) {
                const baseQty = isNaN(baseAssetQuantity) ? 0 : baseAssetQuantity;
                const baseOption = new Option(`${baseAssetSymbol} (Bal: ${baseQty.toFixed(8)})`, baseAssetSymbol);
                assetSelect.add(baseOption);
            }
            
            // Add quote asset option if available
            if (quoteAssetSymbol) {
                const quoteQty = isNaN(quoteAssetQuantity) ? 0 : quoteAssetQuantity;
                const quoteOption = new Option(`${quoteAssetSymbol} (Bal: ${quoteQty.toFixed(8)})`, quoteAssetSymbol);
                assetSelect.add(quoteOption);
            }
            
            // Enable the asset dropdown if there are multiple options
            assetSelect.disabled = false;
            
            // Set up asset selection change handler
            assetSelect.onchange = function() {
                handleAssetSelectionChange(strategyId, baseAssetSymbol, baseAssetQuantity, quoteAssetSymbol, quoteAssetQuantity);
            };
            
            // Select first option and trigger change event
            if (assetSelect.options.length > 0) {
                assetSelect.selectedIndex = 0;
                // Manually trigger the change handler since we just set it up
                handleAssetSelectionChange(strategyId, baseAssetSymbol, baseAssetQuantity, quoteAssetSymbol, quoteAssetQuantity);
            }
            
            amountInput.value = '';
            assetTransferModal.show();
        });
    });

    // Also handle the regular transfer buttons (main account to strategy)
    document.querySelectorAll('.transfer-button').forEach(button => {
        button.addEventListener('click', function() {
            console.log('Main account transfer button clicked. Dataset:', JSON.parse(JSON.stringify(this.dataset)));
            
            const transferType = this.dataset.transferType;
            const assetSymbol = this.dataset.assetSymbol;
            const assetName = this.dataset.assetName || assetSymbol;
            const maxTransferable = parseFloat(this.dataset.maxTransferable);
            const credentialId = this.dataset.credentialId;
            
            transferForm.dataset.currentTransferType = transferType;
            
            // Base URL for form action - get current exchange_id from URL
            const currentExchangeId = window.location.pathname.split('/')[2];
            transferForm.action = `/exchange/${currentExchangeId}/transfer`;
            
            // Set modal title
            modalTitle.textContent = 'Transfer Assets';
            
            // Clear previous selections
            sourceAccountSelect.innerHTML = '';
            destinationAccountSelect.innerHTML = '';
            
            // Populate source dropdown (Main accounts and all strategies)
            populateSourceDropdown(credentialId);
            
            // Pre-select the source main account
            sourceAccountSelect.value = `main::${credentialId}::${assetSymbol}`;
            
            // Populate asset dropdown generically based on selected source (main account)
            handleSourceAccountChange(sourceAccountSelect.value);
            
            // Populate destinations (strategies compatible with this asset)
            populateDestinationsForMainToStrategy(assetSymbol, credentialId);
            
            amountInput.value = '';
            assetTransferModal.show();
        });
    });
    
    // Handle source account selection change
    sourceAccountSelect.addEventListener('change', function() {
        handleSourceAccountChange(this.value);
    });
    
    // Handle max button click
    maxButton.addEventListener('click', function() {
        amountInput.value = availableToTransferSpan.textContent;
    });
    
    // Add form validation
    transferForm.addEventListener('submit', function(event) {
        const confirmBtn = document.getElementById('confirmTransferBtn');
        const resetBtnState = () => {
            if (!confirmBtn) return;
            confirmBtn.disabled = false;
            const spinner = confirmBtn.querySelector('.spinner-border');
            const btnText = confirmBtn.querySelector('.btn-text');
            if (spinner) spinner.classList.add('d-none');
            if (btnText) btnText.textContent = 'Confirm Transfer';
        };

        const amountValue = parseFloat(amountInput.value);
        const maxAmount = parseFloat(availableToTransferSpan.textContent);

        if (isNaN(amountValue) || amountValue <= 0) {
            event.preventDefault();
            event.stopImmediatePropagation();
            resetBtnState();
            alert('Please enter a valid amount greater than zero.');
            return false;
        }

        if (amountValue > maxAmount) {
            event.preventDefault();
            event.stopImmediatePropagation();
            resetBtnState();
            alert(`Amount exceeds available balance. Maximum: ${maxAmount}`);
            return false;
        }

        // allow submission to proceed; the separate listener will handle spinner
        return true;
    });

    // Helper Functions
    
    // Populate the source account dropdown
    function populateSourceDropdown(credentialId) {
        // 1. Add Main Account Assets for the current credential
        if (allMainAccountAssetsOnPage && credentialId) {
            allMainAccountAssetsOnPage.forEach(asset => {
                if (String(asset.exchange_credential_id) === String(credentialId)) {
                    const optionId = `main::${asset.exchange_credential_id}::${asset.asset_symbol}`;
                    const optionText = `Main Account - ${asset.asset_symbol} (Bal: ${parseFloat(asset.available_balance).toFixed(8)})`;
                    sourceAccountSelect.add(new Option(optionText, optionId));
                }
            });
        }
        
        // 2. Add Trading Strategies for the current credential (each strategy only once)
        if (allStrategiesOnPage && credentialId) {
            const addedStrategyIds = new Set();
            allStrategiesOnPage.forEach(strategy => {
                if (String(strategy.exchange_credential_id) === String(credentialId)) {
                    // Only add each strategy once
                    if (!addedStrategyIds.has(strategy.id)) {
                        addedStrategyIds.add(strategy.id);
                        
                        // Check if strategy has any assets with balance
                        const hasBaseBalance = !!strategy.base_asset_symbol;
                        const hasQuoteBalance = !!strategy.quote_asset_symbol;
                        
                        const optionId = `strategy::${strategy.id}`;
                        const optionText = `${strategy.name}`;
                        sourceAccountSelect.add(new Option(optionText, optionId));
                    }
                }
            });
        }
    }
    
    // Handle source account change
    function handleSourceAccountChange(selectedOptionValue) {
        console.log('[handleSourceAccountChange] Source value changed to:', selectedOptionValue);
        
        if (!selectedOptionValue) {
            console.warn("Source account selection is empty. Clearing dependent fields.");
            assetSelect.innerHTML = '';
            availableToTransferSpan.textContent = '0.00';
            assetSymbolHiddenInput.value = '';
            transferingAssetSymbolDisplaySpan.textContent = 'N/A';
            return;
        }
        
        // Parse source option value format: [source_type]::[id] or [source_type]::[id]::[asset_symbol]
        const sourceOptionParts = selectedOptionValue.split('::');
        if (sourceOptionParts.length < 2) {
            console.error('Invalid source option value format:', selectedOptionValue);
            return;
        }
        
        const sourceType = sourceOptionParts[0]; // 'main' or 'strategy'
        
        if (sourceType === 'main') {
            // Handle main account source
            const credentialId = sourceOptionParts[1];
            const assetSymbol = sourceOptionParts[2];
            
            // Find the main account asset
            const mainAsset = allMainAccountAssetsOnPage.find(a => 
                a.asset_symbol === assetSymbol && String(a.exchange_credential_id) === String(credentialId)
            );
            
            if (mainAsset) {
                // Populate asset dropdown with ALL main account assets for this exchange
                assetSelect.innerHTML = '';
                allMainAccountAssetsOnPage.filter(a => String(a.exchange_credential_id) === String(credentialId)).forEach(a => {
                    assetSelect.add(new Option(`${a.asset_symbol} (Bal: ${parseFloat(a.available_balance).toFixed(8)})`, a.asset_symbol));
                });
                assetSelect.disabled = false;
                // Ensure the originally selected asset is highlighted
                assetSelect.value = assetSymbol;

                // Attach change handler to update available amount and destinations dynamically
                assetSelect.onchange = function() {
                    const selectedSymbol = assetSelect.value;
                    const selectedAsset = allMainAccountAssetsOnPage.find(a => a.asset_symbol === selectedSymbol && String(a.exchange_credential_id) === String(credentialId));
                    const availAmt = selectedAsset ? parseFloat(selectedAsset.available_balance) : 0;
                    assetSymbolHiddenInput.value = selectedSymbol;
                    availableToTransferSpan.textContent = Number(availAmt).toFixed(8);
                    transferingAssetSymbolDisplaySpan.textContent = selectedSymbol;
                    populateDestinationsForMainToStrategy(selectedSymbol, credentialId);
                };
                
                // Update form fields
                const availableAmount = parseFloat(mainAsset.available_balance);
                assetSymbolHiddenInput.value = assetSymbol;
                availableToTransferSpan.textContent = Number(availableAmount || 0).toFixed(8);
                transferingAssetSymbolDisplaySpan.textContent = assetSymbol;
                
                // Populate destinations
                populateDestinationsForMainToStrategy(assetSymbol, credentialId);
            } else {
                console.error('Main account asset not found:', assetSymbol);
                assetSelect.innerHTML = '';
                assetSelect.add(new Option('Error: Asset not found', ''));
                assetSelect.disabled = false;
            }
        } else if (sourceType === 'strategy') {
            // Handle strategy source
            const strategyId = sourceOptionParts[1];
            
            // Find the strategy
            const strategy = allStrategiesOnPage.find(s => String(s.id) === String(strategyId));
            
            if (strategy) {
                // Update available assets for this strategy
                const hasBaseBalance = !!strategy.base_asset_symbol;
                const hasQuoteBalance = !!strategy.quote_asset_symbol;
                
                // Populate asset dropdown
                assetSelect.innerHTML = '';
                assetSelect.disabled = false;
                
                if (hasBaseBalance) {
                    const baseAmountRaw = parseFloat(strategy.allocated_base_asset_quantity);
                    const baseAmount = isNaN(baseAmountRaw) ? 0 : baseAmountRaw;
                    assetSelect.add(new Option(
                        `${strategy.base_asset_symbol} (Bal: ${baseAmount.toFixed(8)})`,
                        strategy.base_asset_symbol
                    ));
                }
                
                if (hasQuoteBalance && strategy.quote_asset_symbol !== strategy.base_asset_symbol) {
                    const quoteAmountRaw = parseFloat(strategy.allocated_quote_asset_quantity);
                    const quoteAmount = isNaN(quoteAmountRaw) ? 0 : quoteAmountRaw;
                    assetSelect.add(new Option(
                        `${strategy.quote_asset_symbol} (Bal: ${quoteAmount.toFixed(8)})`,
                        strategy.quote_asset_symbol
                    ));
                }
                
                // Enable dropdown if multiple options
                assetSelect.disabled = false;
                
                // Set up asset change handler
                assetSelect.onchange = function() {
                    handleAssetSelectionChange(
                        strategyId, 
                        strategy.base_asset_symbol, 
                        parseFloat(strategy.allocated_base_asset_quantity), 
                        strategy.quote_asset_symbol, 
                        parseFloat(strategy.allocated_quote_asset_quantity)
                    );
                };
                
                // Trigger change for the first option
                if (assetSelect.options.length > 0) {
                    assetSelect.selectedIndex = 0;
                    handleAssetSelectionChange(
                        strategyId, 
                        strategy.base_asset_symbol, 
                        parseFloat(strategy.allocated_base_asset_quantity), 
                        strategy.quote_asset_symbol, 
                        parseFloat(strategy.allocated_quote_asset_quantity)
                    );
                }
            } else {
                console.error('Strategy not found:', strategyId);
                assetSelect.innerHTML = '';
                assetSelect.add(new Option('Error: Strategy not found', ''));
                assetSelect.disabled = false;
            }
        } else {
            console.error('Unknown source type:', sourceType);
            assetSelect.innerHTML = '';
            assetSelect.disabled = false;
        }
    }
    
    // Handle asset selection change for strategy sources
    function handleAssetSelectionChange(strategyId, baseAssetSymbol, baseAssetQuantity, quoteAssetSymbol, quoteAssetQuantity) {
        const selectedAsset = assetSelect.value;
        
        if (!selectedAsset) {
            return;
        }
        
        // Update available amount and form fields based on selected asset
        let availableAmount = 0;
        if (selectedAsset === baseAssetSymbol) {
            availableAmount = baseAssetQuantity;
        } else if (selectedAsset === quoteAssetSymbol) {
            availableAmount = quoteAssetQuantity;
        }
        
        assetSymbolHiddenInput.value = selectedAsset;
        availableToTransferSpan.textContent = Number(availableAmount || 0).toFixed(8);
        transferingAssetSymbolDisplaySpan.textContent = selectedAsset;
        
        // Populate destinations for this strategy and asset
        populateDestinationsForStrategySource(strategyId, selectedAsset);
    }
    
    // Populate destinations for strategy-to-main or strategy-to-strategy transfers
    function populateDestinationsForStrategySource(sourceStrategyId, sourceAssetSymbol) {
        console.log('Populating destinations for strategy source:', sourceStrategyId, 'asset:', sourceAssetSymbol);
        
        destinationAccountSelect.innerHTML = '';
        
        if (!sourceAssetSymbol || !sourceStrategyId) {
            destinationAccountSelect.add(new Option('Select source and asset first', ''));
            return;
        }
        
        // Find the source strategy
        const sourceStrategy = allStrategiesOnPage.find(s => String(s.id) === String(sourceStrategyId));
        if (!sourceStrategy) {
            console.error('Source strategy not found:', sourceStrategyId);
            destinationAccountSelect.add(new Option('Error: Source strategy not found', ''));
            return;
        }
        
        // 1. ALWAYS add Main Account as a destination option
        let mainAccountAdded = false;
        
        // Try to find a matching main account asset first
        if (!mainAccountAdded && sourceStrategy.exchange_credential_id) {
            const optionValue = `main::${sourceStrategy.exchange_credential_id}::${sourceAssetSymbol}`;
            const optionText = `Main Account - ${sourceAssetSymbol}`;
            destinationAccountSelect.add(new Option(optionText, optionValue));
        }
        
        // 2. Add other strategies as destinations (EXCEPT the source strategy)
        allStrategiesOnPage.forEach(destStrategy => {
            // Skip if from different credentials/exchanges or if it's the source strategy
            if (String(destStrategy.exchange_credential_id) !== String(sourceStrategy.exchange_credential_id) ||
                String(destStrategy.id) === String(sourceStrategyId)) {
                return;
            }
            
            // Add as a destination option
            const optionValue = `strategy::${destStrategy.id}`;
            const optionText = destStrategy.name;
            destinationAccountSelect.add(new Option(optionText, optionValue));
        });
        
        // Enable the destination dropdown
        destinationAccountSelect.disabled = false;
    }
    
    // Populate destinations for main-to-strategy transfers
    function populateDestinationsForMainToStrategy(assetSymbol, credentialId) {
        console.log('Populating destinations for main source:', assetSymbol, 'credentialId:', credentialId);
        
        destinationAccountSelect.innerHTML = '';
        
        allStrategiesOnPage.forEach(strategy => {
            if (String(strategy.exchange_credential_id) === String(credentialId)) {
                const optionValue = `strategy::${strategy.id}`;
                const optionText = strategy.name;
                destinationAccountSelect.add(new Option(optionText, optionValue));
            }
        });
        
        if (destinationAccountSelect.options.length === 0) {
            destinationAccountSelect.add(new Option('No strategies found', ''));
            destinationAccountSelect.disabled = true;
        } else {
            destinationAccountSelect.disabled = false;
        }
    }
    
    // Functions to be called from template to pass data
    window.setCurrentCredentialId = function(credId) {
        currentCredentialId = credId;
    };
    
    window.setMainAccountAssetsData = function(assets) {
        allMainAccountAssetsOnPage = assets;
    };
    
    window.setStrategiesData = function(strategies) {
        allStrategiesOnPage = strategies;
    };
});
