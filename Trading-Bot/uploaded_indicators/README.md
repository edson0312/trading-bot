# Custom Indicators Directory

This directory stores custom TradingView Pine Script indicators uploaded through the web interface.

## Supported Pine Script Versions

- **Pine Script v4** - Original/Legacy support
- **Pine Script v5** - Full support for modern Pine Script syntax
- **Pine Script v6** - Support for the latest Pine Script features

## Supported Indicators

Currently, the following indicator types are supported:

1. **HWR (High Wave Ratio)** - Identifies entry points based on candle patterns
   - Filename must contain "HWR" in the name

2. **Generic Technical Indicators** - Basic support for most common Pine Script technical indicators
   - Any Pine Script v5 or v6 indicator can be uploaded and will be automatically interpreted

## How to Use

1. Export your indicator from TradingView as a Pine Script file (.pine)
2. Upload through the web interface in the "Custom Indicators" tab
3. Select your indicator from the dropdown list
4. Start the trading bot

## Example Format (HWR v5)

```pine
//@version=5
indicator("High Wave Ratio (HWR)", shorttitle="HWR")

length = input.int(21, "Length")

// Calculate True Range and ATR
tr = math.max(high - low, math.abs(high - close[1]), math.abs(low - close[1]))
atr = ta.sma(tr, length)

// Calculate wave height and HWR
wave_height = high - low
hwr = wave_height / atr

// Define buy and sell conditions
buy = hwr < 0.5 and close > open
sell = hwr < 0.5 and close < open

// Plot signals
plotshape(buy, title="Buy Signal", location=location.belowbar, color=color.green, style=shape.labelup, size=size.small)
plotshape(sell, title="Sell Signal", location=location.abovebar, color=color.red, style=shape.labeldown, size=size.small)
```

## Notes

- Uploaded indicators automatically become available in the dropdown list
- The bot will use the selected indicator for entry signals
- The selected Risk Management Strategy will be used for exit signals regardless of the indicator used for entry
- Make sure to specify the version using `//@version=X` at the top of your script for best compatibility
- In Pine Script v5/v6, use `indicator()` instead of `study()` function
- Full support for variable types introduced in Pine Script v5/v6 (arrays, matrices, maps, etc.) 