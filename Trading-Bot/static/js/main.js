// Add the trailing strategy checkbox to the strategy checkboxes list
document.addEventListener('DOMContentLoaded', function() {
    // Get all strategy checkboxes
    const progressiveCheckbox = document.getElementById('enable-progressive');
    const drawdownCheckbox = document.getElementById('enable-drawdown');
    const trailingCheckbox = document.getElementById('enable-trailing');
    
    // Add event listeners for strategy checkboxes
    if (progressiveCheckbox) {
        progressiveCheckbox.addEventListener('change', function() {
            updateStrategyState();
        });
    }
    
    if (drawdownCheckbox) {
        drawdownCheckbox.addEventListener('change', function() {
            updateStrategyState();
        });
    }
    
    if (trailingCheckbox) {
        trailingCheckbox.addEventListener('change', function() {
            updateStrategyState();
        });
    }
    
    // Function to update strategy state
    function updateStrategyState() {
        // If trailing is enabled, disable other strategies
        if (trailingCheckbox && trailingCheckbox.checked) {
            if (progressiveCheckbox) progressiveCheckbox.checked = false;
            if (drawdownCheckbox) drawdownCheckbox.checked = false;
            
            // Disable other strategy checkboxes
            if (progressiveCheckbox) progressiveCheckbox.disabled = true;
            if (drawdownCheckbox) drawdownCheckbox.disabled = true;
            
            // Show warning about single position
            document.querySelectorAll('.trailing-warning').forEach(el => {
                el.style.display = 'block';
            });
        } else {
            // Re-enable other strategy checkboxes
            if (progressiveCheckbox) progressiveCheckbox.disabled = false;
            if (drawdownCheckbox) drawdownCheckbox.disabled = false;
            
            // Hide warning
            document.querySelectorAll('.trailing-warning').forEach(el => {
                el.style.display = 'none';
            });
        }
        
        // If progressive is enabled, update its UI elements
        if (progressiveCheckbox) {
            const progressiveInputs = document.querySelectorAll('#progressive input:not(#enable-progressive)');
            progressiveInputs.forEach(input => {
                input.disabled = !progressiveCheckbox.checked;
            });
        }
        
        // If drawdown is enabled, update its UI elements
        if (drawdownCheckbox) {
            const drawdownInputs = document.querySelectorAll('#drawdown input:not(#enable-drawdown)');
            drawdownInputs.forEach(input => {
                input.disabled = !drawdownCheckbox.checked;
            });
        }
        
        // If trailing is enabled, update its UI elements
        if (trailingCheckbox) {
            const trailingInputs = document.querySelectorAll('#trailing input:not(#enable-trailing)');
            trailingInputs.forEach(input => {
                input.disabled = !trailingCheckbox.checked;
            });
        }
    }
    
    // Initialize the UI state
    updateStrategyState();
});

// Main functionality for MT5 Multi-Instance Trading Bot
document.addEventListener('DOMContentLoaded', function() {
    // Function to handle risk management strategy display
    function handleStrategyDisplay() {
        const containers = document.querySelectorAll('.mt5-instance');
        
        containers.forEach(container => {
            const strategySelect = container.querySelector('.mt5-strategy');
            if (!strategySelect) return;
            
            // Hide all strategy-specific settings
            const settingsContainers = container.querySelectorAll('.strategy-specific-settings > div');
            settingsContainers.forEach(settingsContainer => {
                settingsContainer.style.display = 'none';
            });
            
            // Show the appropriate settings based on selected strategy
            const strategy = strategySelect.value;
            switch(strategy) {
                case 'exit_signal_or_max_tp':
                    container.querySelector('.exit-signal-settings').style.display = 'block';
                    break;
                case 'progressive':
                    container.querySelector('.progressive-settings').style.display = 'block';
                    break;
                case 'drawdown':
                    container.querySelector('.drawdown-settings').style.display = 'block';
                    break;
                case 'trailing_stop':
                    container.querySelector('.trailing-settings').style.display = 'block';
                    break;
                case 'hybrid_progressive_drawdown':
                    container.querySelector('.hybrid-progressive-drawdown-settings').style.display = 'block';
                    break;
                case 'hybrid_trailing_drawdown':
                    container.querySelector('.trailing-drawdown-settings').style.display = 'block';
                    break;
            }
        });
    }
    
    // Set up event listeners for strategy selection
    document.addEventListener('change', function(event) {
        if (event.target.classList.contains('mt5-strategy')) {
            handleStrategyDisplay();
        }
    });
    
    // Set up event listeners for High Impact News toggle
    document.addEventListener('change', function(event) {
        if (event.target.classList.contains('hin-toggle')) {
            const container = event.target.closest('.mt5-instance');
            const settings = container.querySelector('.hin-settings');
            settings.style.display = event.target.checked ? 'block' : 'none';
        }
    });
    
    // Set up event listeners for Prop Firm Mode toggle
    document.addEventListener('change', function(event) {
        if (event.target.classList.contains('pfm-toggle')) {
            const container = event.target.closest('.mt5-instance');
            const settings = container.querySelector('.pfm-settings');
            settings.style.display = event.target.checked ? 'block' : 'none';
        }
    });
    
    // Set up event listeners for Multi-Symbol toggle
    document.addEventListener('change', function(event) {
        if (event.target.classList.contains('mt5-multi-symbol-enabled')) {
            const container = event.target.closest('.mt5-instance');
            const singleContainer = container.querySelector('.mt5-single-symbol-container');
            const multiContainer = container.querySelector('.mt5-multi-symbol-container');
            
            singleContainer.style.display = event.target.checked ? 'none' : 'block';
            multiContainer.style.display = event.target.checked ? 'block' : 'none';
            
            if (event.target.checked) {
                const selectedSymbols = container.querySelector('.mt5-selected-symbols');
                const currentSymbol = container.querySelector('.mt5-symbol').value;
                
                // Add current symbol if it doesn't exist
                if (currentSymbol && selectedSymbols.querySelectorAll(`[data-symbol="${currentSymbol}"]`).length === 0) {
                    addSymbolTag(selectedSymbols, currentSymbol);
                }
                
                // Add default symbols if there aren't many symbols
                if (selectedSymbols.children.length < 2) {
                    ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'AUDUSD', 'NZDUSD', 'AUDCAD', 'NZDCAD', 'EURCAD', 'USDCAD'].forEach(symbol => {
                        if (symbol !== currentSymbol && selectedSymbols.querySelectorAll(`[data-symbol="${symbol}"]`).length === 0) {
                            addSymbolTag(selectedSymbols, symbol);
                        }
                    });
                }
            }
        }
    });
    
    // Initialize displays
    handleStrategyDisplay();
    
    // Function to add a symbol tag
    function addSymbolTag(container, symbol) {
        const tag = document.createElement('div');
        tag.className = 'symbol-tag';
        tag.textContent = symbol;
        tag.dataset.symbol = symbol;
        
        const deleteBtn = document.createElement('span');
        deleteBtn.className = 'symbol-delete';
        deleteBtn.textContent = '×';
        deleteBtn.addEventListener('click', function() {
            tag.remove();
        });
        
        tag.appendChild(deleteBtn);
        container.appendChild(tag);
    }
}); 