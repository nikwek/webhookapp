// JavaScript for asset transfer modal on the exchange page
document.addEventListener('DOMContentLoaded', function () {
    console.log('Exchange transfers JS loaded');

    const assetTransferModal = new bootstrap.Modal(document.getElementById('assetTransferModal'));
    const transferForm = document.getElementById('assetTransferForm');
    const sourceAccountSelect = document.getElementById('transferSourceAccount');
    const destinationAccountSelect = document.getElementById('transferDestinationAccount');
    const assetDisplay = document.getElementById('transferAssetDisplay');
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

    document.querySelectorAll('.transfer-button').forEach(button => {
        button.addEventListener('click', function () {
            console.log('JS LOG: .transfer-button clicked. dataset:', JSON.parse(JSON.stringify(this.dataset)));
            const transferType = this.dataset.transferType;
            transferForm.dataset.currentTransferType = transferType; // Store for submit handler
            const assetSymbol = this.dataset.assetSymbol;
            const assetName = this.dataset.assetName; // For main account transfers
            const maxTransferable = parseFloat(this.dataset.maxTransferable);
            const credentialId = this.dataset.credentialId;
            
            // Base URL for form action - get current exchange_id from URL or a data attribute
            const currentExchangeId = window.location.pathname.split('/')[2]; // Assumes URL like /exchange/some_id
            transferForm.action = `/exchange/${currentExchangeId}/transfer`;

            // Clear previous options
            sourceAccountSelect.innerHTML = '';
            destinationAccountSelect.innerHTML = '';

            // Populate Source Account dropdown with all eligible main account assets and strategies
            // 1. Add Main Account Assets for the current credential
            console.log('JS LOG: Populating source dropdown. Current Credential ID:', currentCredentialId);
            console.log('JS LOG: Main account assets available:', JSON.parse(JSON.stringify(allMainAccountAssetsOnPage)));
            if (allMainAccountAssetsOnPage && currentCredentialId) {
                allMainAccountAssetsOnPage.forEach(asset => {
                    // Ensure asset belongs to the current exchange credential
                    if (String(asset.exchange_credential_id) === String(currentCredentialId)) {
                        const optionId = `main::${asset.exchange_credential_id}::${asset.asset_symbol}`;
                        const optionText = `${asset.name} (Bal: ${parseFloat(asset.available_balance).toFixed(8)} ${asset.asset_symbol})`;
                        sourceAccountSelect.add(new Option(optionText, optionId));
                    }
                });
            }
            // 2. Add Trading Strategies (asset-specific) for the current credential
            console.log('JS LOG: Strategies available for source dropdown:', JSON.parse(JSON.stringify(allStrategiesOnPage)));
            if (allStrategiesOnPage && currentCredentialId) {
                allStrategiesOnPage.forEach(strategy => {
                    if (String(strategy.exchange_credential_id) === String(currentCredentialId)) {
                        // Option for base asset if balance > 0
                        if (strategy.base_asset_symbol && parseFloat(strategy.allocated_base_asset_quantity) > 0) {
                            const optionIdBase = `strategy::${strategy.id}::${strategy.base_asset_symbol}`;
                            const optionTextBase = `${strategy.name} - ${strategy.base_asset_symbol} (Bal: ${parseFloat(strategy.allocated_base_asset_quantity).toFixed(8)})`;
                            sourceAccountSelect.add(new Option(optionTextBase, optionIdBase));
                        }
                        // Option for quote asset if balance > 0 and different from base asset
                        if (strategy.quote_asset_symbol && parseFloat(strategy.allocated_quote_asset_quantity) > 0 && strategy.quote_asset_symbol !== strategy.base_asset_symbol) {
                            const optionIdQuote = `strategy::${strategy.id}::${strategy.quote_asset_symbol}`;
                            const optionTextQuote = `${strategy.name} - ${strategy.quote_asset_symbol} (Bal: ${parseFloat(strategy.allocated_quote_asset_quantity).toFixed(8)})`;
                            sourceAccountSelect.add(new Option(optionTextQuote, optionIdQuote));
                        }
                    }
                });
            }
            sourceAccountSelect.disabled = false; // Ensure source is enabled

            if (transferType === 'main_to_strategy') {
                // Pre-select the source based on the clicked button
                const selectedSourceValue = `main::${credentialId}::${assetSymbol}`;
                sourceAccountSelect.value = selectedSourceValue;
                console.log(`JS LOG: Pre-selected source for main_to_strategy: ${selectedSourceValue}`);

                // Set initial modal fields based on the clicked main account asset
                modalTitle.textContent = `Transfer ${assetName || assetSymbol} from Main Account`;
                assetDisplay.innerHTML = `<strong>${assetName || assetSymbol}</strong>`; // This is the asset being transferred
                assetSymbolHiddenInput.value = assetSymbol; // Asset symbol from the button
                availableToTransferSpan.textContent = maxTransferable.toFixed(8); // Max transferable for this asset from button
                transferingAssetSymbolDisplaySpan.textContent = assetSymbol; // Asset symbol from button

                // Populate Destination: Strategies compatible with this assetSymbol and credentialId
                destinationAccountSelect.disabled = false;
                console.log('Transfer Modal Debug: Main to Strategy');
                console.log(' - Asset to transfer:', assetSymbol, '| Credential ID from button:', credentialId);
                console.log(' - All strategies on page:', JSON.parse(JSON.stringify(allStrategiesOnPage))); // Deep copy for logging

                if (allStrategiesOnPage.length === 0) {
                    console.log(' - No strategies found in allStrategiesOnPage array.');
                    let noStrategiesOption = new Option('No strategies available for this exchange (JS: array empty)', '', true, true);
                    noStrategiesOption.disabled = true;
                    destinationAccountSelect.add(noStrategiesOption);
                } else {
                    allStrategiesOnPage.forEach(strategy => {
                        console.log(` -- Checking strategy: ${strategy.name} (ID: ${strategy.id})`);
                        console.log(`    Strategy Cred ID: ${strategy.exchange_credential_id} (type: ${typeof strategy.exchange_credential_id}), Button Cred ID: ${credentialId} (type: ${typeof credentialId})`);
                        console.log(`    Strategy Base: ${strategy.base_asset_symbol}, Strategy Quote: ${strategy.quote_asset_symbol}, Asset to Transfer: ${assetSymbol}`);
                        
                        let credentialMatch = false;
                        // Ensure robust comparison for credential ID (string vs number)
                        if (String(strategy.exchange_credential_id) === String(credentialId)) {
                            credentialMatch = true;
                        } else {
                            console.log(`    Skipping strategy ${strategy.name}: Credential ID mismatch.`);
                        }

                        if (credentialMatch) {
                           if (strategy.base_asset_symbol === assetSymbol || strategy.quote_asset_symbol === assetSymbol) {
                                console.log(`    Compatible: Adding strategy ${strategy.name} to dropdown.`);
                                let strategyOption = new Option(`${strategy.name} (ID: ${strategy.id})`, `strategy::${strategy.id}`);
                                destinationAccountSelect.add(strategyOption);
                           } else {
                                console.log(`    Skipping strategy ${strategy.name}: Asset symbol mismatch (Base: ${strategy.base_asset_symbol}, Quote: ${strategy.quote_asset_symbol} vs Transfer: ${assetSymbol}).`);
                            } // Closes if/else for asset symbol match
                        } // Closes if for credentialMatch
                    }); // Closes allStrategiesOnPage.forEach
                } // Closes else for if (allStrategiesOnPage.length === 0)
            } else if (transferType === 'strategy_to_main') {
                transferForm.dataset.currentTransferType = transferType;

                const strategyId = this.dataset.strategyId;
                const assetSymbolFromButton = this.dataset.assetSymbol; // Get the specific asset from the button
                console.log(`JS LOG: Inside strategy_to_main. strategyId: ${strategyId}, assetSymbolFromButton: ${assetSymbolFromButton}`);
                const strategy = allStrategiesOnPage.find(s => String(s.id) === String(strategyId));

                if (strategy) {
                    modalTitle.textContent = `Transfer ${assetSymbolFromButton} from ${strategy.name}`;
                } else {
                    modalTitle.textContent = `Transfer from Strategy`; // Fallback title
                    console.error(`JS ERROR: Strategy with ID ${strategyId} not found when setting modal title for strategy_to_main transfer.`);
                }

                const selectedSourceValue = `strategy::${strategyId}::${assetSymbolFromButton}`;
                sourceAccountSelect.value = selectedSourceValue;
                
                // Explicitly dispatch change event to trigger UI updates based on new source
                console.log('JS LOG: Dispatching change event for sourceAccountSelect after strategy_to_main pre-selection. Value:', selectedSourceValue);
                sourceAccountSelect.dispatchEvent(new Event('change'));
            } // Closes if/else for transferType
            amountInput.value = '';
            assetTransferModal.show();
            // The console.log that was here for debugging is removed as we restore full functionality.
        }); // Closes the strategyTransferButton click listener and addEventListener call
    }); // Closes the strategyTransferButtons.forEach callback and forEach call

    function populateDestinationsForStrategySource(sourceStrategyId, sourceAssetSymbol) {
        console.log('[populateDestinationsForStrategySource] Called with sourceStrategyId:', sourceStrategyId, 'sourceAssetSymbol:', sourceAssetSymbol);
        const destinationAccountSelect = document.getElementById('transferDestinationAccount');
        destinationAccountSelect.innerHTML = ''; // Clear previous options

        if (!sourceAssetSymbol || sourceAssetSymbol === 'N/A' || !sourceStrategyId) {
            console.warn('[populateDestinationsForStrategySource] Invalid parameters.');
            destinationAccountSelect.add(new Option('Select source first', ''));
            return;
        }

        const sourceStrategy = allStrategiesOnPage.find(s => s.id.toString() === sourceStrategyId.toString());
        if (!sourceStrategy) {
            console.error(`[populateDestinationsForStrategySource] Source strategy with ID ${sourceStrategyId} not found.`);
            destinationAccountSelect.add(new Option('Error: Source strategy not found', ''));
            return;
        }
        console.log('[populateDestinationsForStrategySource] Source strategy object:', sourceStrategy);
        console.log('[populateDestinationsForStrategySource] Main account assets for filtering:', allMainAccountAssetsOnPage);

        // 1. Add Main Account as a destination for the SAME asset type
        allMainAccountAssetsOnPage.forEach(mainAsset => {
            if (mainAsset.asset_symbol === sourceAssetSymbol && 
                String(mainAsset.exchange_credential_id) === String(sourceStrategy.exchange_credential_id)) {
                const optionValue = `main::${mainAsset.exchange_credential_id}::${mainAsset.asset_symbol}`;
                const optionText = `Main Account - ${mainAsset.asset_symbol} (Bal: ${parseFloat(mainAsset.available_balance).toFixed(8)})`;
                destinationAccountSelect.add(new Option(optionText, optionValue));
                console.log('[populateDestinationsForStrategySource] Added main account destination:', optionText);
            }
        });

        // 2. Add Other Strategies (and self, for different asset) as destinations
        console.log('[populateDestinationsForStrategySource] Strategies for filtering:', allStrategiesOnPage);
        allStrategiesOnPage.forEach(destStrategy => {
            if (String(destStrategy.exchange_credential_id) !== String(sourceStrategy.exchange_credential_id)) {
                return; // Skip strategies from different credentials/exchanges
            }

            // Case A: Transferring to a DIFFERENT strategy (for the same asset type)
            if (destStrategy.id.toString() !== sourceStrategyId.toString()) {
                if (destStrategy.base_asset_symbol === sourceAssetSymbol && destStrategy.allocated_base_asset_quantity !== undefined) {
                    const optionValue = `strategy::${destStrategy.id}::${destStrategy.base_asset_symbol}`;
                    const optionText = `${destStrategy.name} - ${destStrategy.base_asset_symbol} (Bal: ${parseFloat(destStrategy.allocated_base_asset_quantity).toFixed(8)})`;
                    destinationAccountSelect.add(new Option(optionText, optionValue));
                    console.log('[populateDestinationsForStrategySource] Added different strategy (base asset) destination:', optionText);
                }
                if (destStrategy.quote_asset_symbol === sourceAssetSymbol && destStrategy.quote_asset_symbol !== destStrategy.base_asset_symbol && destStrategy.allocated_quote_asset_quantity !== undefined) {
                    const optionValue = `strategy::${destStrategy.id}::${destStrategy.quote_asset_symbol}`;
                    const optionText = `${destStrategy.name} - ${destStrategy.quote_asset_symbol} (Bal: ${parseFloat(destStrategy.allocated_quote_asset_quantity).toFixed(8)})`;
                    destinationAccountSelect.add(new Option(optionText, optionValue));
                    console.log('[populateDestinationsForStrategySource] Added different strategy (quote asset) destination:', optionText);
                }
            }
            // Case B: Transferring WITHIN the SAME strategy (to its other asset)
            else { // destStrategy.id.toString() === sourceStrategyId.toString()
                // Source is base, destination is quote
                if (sourceAssetSymbol === destStrategy.base_asset_symbol && destStrategy.quote_asset_symbol && destStrategy.quote_asset_symbol !== sourceAssetSymbol && destStrategy.allocated_quote_asset_quantity !== undefined) {
                    const optionValue = `strategy::${destStrategy.id}::${destStrategy.quote_asset_symbol}`;
                    const optionText = `${destStrategy.name} - ${destStrategy.quote_asset_symbol} (Bal: ${parseFloat(destStrategy.allocated_quote_asset_quantity).toFixed(8)}) (Internal)`;
                    destinationAccountSelect.add(new Option(optionText, optionValue));
                    console.log('[populateDestinationsForStrategySource] Added same strategy (quote asset) destination:', optionText);
                }
                // Source is quote, destination is base
                if (sourceAssetSymbol === destStrategy.quote_asset_symbol && destStrategy.base_asset_symbol && destStrategy.base_asset_symbol !== sourceAssetSymbol && destStrategy.allocated_base_asset_quantity !== undefined) {
                    const optionValue = `strategy::${destStrategy.id}::${destStrategy.base_asset_symbol}`;
                    const optionText = `${destStrategy.name} - ${destStrategy.base_asset_symbol} (Bal: ${parseFloat(destStrategy.allocated_base_asset_quantity).toFixed(8)}) (Internal)`;
                    destinationAccountSelect.add(new Option(optionText, optionValue));
                    console.log('[populateDestinationsForStrategySource] Added same strategy (base asset) destination:', optionText);
                }
            }
        });

        if (destinationAccountSelect.options.length === 0) {
            destinationAccountSelect.add(new Option('No valid destinations found', ''));
            console.log('[populateDestinationsForStrategySource] No valid destinations found overall.');
        }
    }

    sourceAccountSelect.addEventListener('change', function() {
        const selectedOptionValue = this.value;
        console.log('[handleSourceAccountChange] Source value changed to:', selectedOptionValue);
        if (!selectedOptionValue) {
            console.warn("JS WARN: sourceAccountSelect changed to an empty value. Clearing dependent fields.");
            assetDisplay.innerHTML = 'N/A';
            availableToTransferSpan.textContent = '0.00';
            assetSymbolHiddenInput.value = '';
            transferingAssetSymbolDisplaySpan.textContent = 'N/A';
            destinationAccountSelect.innerHTML = '<option value="">Select destination</option>';
            destinationAccountSelect.disabled = true;
            amountInput.value = '';
            return;
        }
        const [sourceType, id1, id2_assetSymbol_or_undefined] = selectedOptionValue.split('::');

        console.log('JS LOG: sourceAccountSelect changed. New value:', selectedOptionValue);
        console.log('JS LOG: Source Type:', sourceType, 'ID1:', id1, 'ID2/Asset:', id2_assetSymbol_or_undefined);
        console.log('JS LOG: Current state - allMainAccountAssetsOnPage:', JSON.parse(JSON.stringify(allMainAccountAssetsOnPage)));
        console.log('JS LOG: Current state - allStrategiesOnPage:', JSON.parse(JSON.stringify(allStrategiesOnPage)));

        let newAssetSymbol = '';
        let newAvailableAmount = 0;

        destinationAccountSelect.innerHTML = '';
        amountInput.value = '';

        if (sourceType === 'main') {
            const selectedCredentialId = id1;
            newAssetSymbol = id2_assetSymbol_or_undefined;
            const mainAsset = allMainAccountAssetsOnPage.find(a => String(a.id) === String(selectedOptionValue));
            
            if (mainAsset) {
                newAvailableAmount = parseFloat(mainAsset.available_balance);
                assetDisplay.innerHTML = `<strong>${mainAsset.asset_symbol}</strong> (from Main Account)`;
                newAssetSymbol = mainAsset.asset_symbol; // Ensure this is set from the found asset
                console.log('[handleSourceAccountChange] Handling main account source. Main asset:', mainAsset);
                populateDestinationsForMainToStrategy(newAssetSymbol, selectedCredentialId);
            } else {
                console.error('JS ERROR: Selected main account asset not found. Value:', selectedOptionValue);
                assetDisplay.innerHTML = 'Error: Asset details not found.';
                destinationAccountSelect.add(new Option('Error loading destinations', '', true, true));
                destinationAccountSelect.disabled = true;
            }
        } else if (sourceType === 'strategy') {
            const selectedStrategyId = id1;
            const selectedAssetFromStrategy = id2_assetSymbol_or_undefined;
            const strategy = allStrategiesOnPage.find(s => String(s.id) === String(selectedStrategyId));

            if (strategy && selectedAssetFromStrategy) {
                newAssetSymbol = selectedAssetFromStrategy;
                if (strategy.base_asset_symbol === selectedAssetFromStrategy) {
                    newAvailableAmount = parseFloat(strategy.allocated_base_asset_quantity);
                } else if (strategy.quote_asset_symbol === selectedAssetFromStrategy) {
                    newAvailableAmount = parseFloat(strategy.allocated_quote_asset_quantity);
                } else {
                    console.error(`JS ERROR: Selected asset ${selectedAssetFromStrategy} does not match base/quote for strategy ${strategy.name}`);
                    newAvailableAmount = 0; // Fallback
                    newAssetSymbol = 'Error';
                }
                assetDisplay.innerHTML = `<strong>${newAssetSymbol}</strong> (from strategy ${strategy.name})`;
                console.log('[handleSourceAccountChange] Handling strategy source. Parsed ID:', selectedStrategyId, 'Asset:', selectedAssetFromStrategy, 'Found strategy:', strategy);
                console.log('[handleSourceAccountChange] About to call populateDestinationsForStrategyToMain with strategyId:', selectedStrategyId, 'assetSymbol:', selectedAssetFromStrategy);
                populateDestinationsForStrategySource(selectedStrategyId, selectedAssetFromStrategy);
            } else {
                console.error('JS ERROR: Selected strategy not found. Value:', selectedOptionValue);
                assetDisplay.innerHTML = 'Error: Strategy details not found.';
                destinationAccountSelect.add(new Option('Error loading destinations', '', true, true));
                destinationAccountSelect.disabled = true;
            }
        } else {
            console.error('JS ERROR: Unknown source type selected:', sourceType, 'from value', selectedOptionValue);
            assetDisplay.innerHTML = 'Error: Unknown source.';
            destinationAccountSelect.add(new Option('Error loading destinations', '', true, true));
            destinationAccountSelect.disabled = true;
            newAssetSymbol = ''; newAvailableAmount = 0;
        }

        console.log('[handleSourceAccountChange] Final check before UI update. newAssetSymbol:', newAssetSymbol, 'newAvailableAmount:', newAvailableAmount);
        assetSymbolHiddenInput.value = newAssetSymbol;
        availableToTransferSpan.textContent = newAvailableAmount.toFixed(8);
        transferingAssetSymbolDisplaySpan.textContent = newAssetSymbol !== 'N/A' && newAssetSymbol !== 'Error' ? newAssetSymbol : '';
        console.log(`JS LOG: Modal updated by source change - Asset: ${newAssetSymbol}, Available: ${newAvailableAmount.toFixed(8)}`);
    });

    maxButton.addEventListener('click', function() {
        amountInput.value = availableToTransferSpan.textContent;
    });

    transferForm.addEventListener('submit', function(event) {
        // event.preventDefault(); // Allow actual form submission
        const transferType = transferForm.dataset.currentTransferType; // Retrieve from form
        console.log('JS LOG: Transfer form submitted. Type:', transferType);

        const source = sourceAccountSelect.value;
        const destination = destinationAccountSelect.value;
        const assetSymbolFromInput = assetSymbolHiddenInput.value; // Asset being transferred
        const amount = amountInput.value;

        if (!source || !destination || !assetSymbolFromInput || assetSymbolFromInput === 'N/A' || !amount) {
            alert('Please ensure all fields (Source, Destination, Asset, Amount) are correctly filled.');
            event.preventDefault(); // Prevent submission if validation fails
            return;
        }

        const numericAmount = parseFloat(amount);
        if (isNaN(numericAmount) || numericAmount <= 0) {
            alert('Amount must be a positive number.');
            event.preventDefault(); // Prevent submission if validation fails
            return;
        }

        const availableText = availableToTransferSpan.textContent;
        const available = parseFloat(availableText);
        if (isNaN(available)) {
            console.error('JS ERROR: Could not parse available amount for validation:', availableText);
            alert('Error validating available amount. Please try refreshing.');
            event.preventDefault(); // Prevent submission if validation fails
            return;
        }

        if (numericAmount > available) {
            alert(`Transfer amount (${numericAmount.toFixed(8)}) cannot exceed available balance (${available.toFixed(8)}).`);
            event.preventDefault(); // Prevent submission if validation fails
            return;
        }

        assetTransferModal.hide();
    });

    // Function to be called from template to pass strategies data
    window.setCurrentCredentialId = function(credId) {
        console.log('JS LOG: window.setCurrentCredentialId CALLED with:', credId);
        currentCredentialId = credId;
        console.log('JS LOG: currentCredentialId is now:', currentCredentialId);
    };

    window.setMainAccountAssetsData = function(assets) {
        console.log('JS LOG: window.setMainAccountAssetsData CALLED with:', JSON.parse(JSON.stringify(assets || null)));
        allMainAccountAssetsOnPage = assets || [];
        console.log('JS LOG: allMainAccountAssetsOnPage in setMainAccountAssetsData is now:', JSON.parse(JSON.stringify(allMainAccountAssetsOnPage)));
    };

    window.setStrategiesData = function(strategies) {
        console.log('JS LOG: window.setStrategiesData CALLED with:', JSON.parse(JSON.stringify(strategies || null)));
        allStrategiesOnPage = strategies || []; // Ensure it's an array, defaulting to empty if strategies is null/undefined
        console.log('JS LOG: allStrategiesOnPage in setStrategiesData is now:', JSON.parse(JSON.stringify(allStrategiesOnPage)));
    };
});
