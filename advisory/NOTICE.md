This directory, along with the advisory and ghost modes, was initially intended to provide async modules for LLM training and trading insights/experience.

However, the actual vector database and LLM modules were implemented in the core/llm and core/vector_db directories, and are planned to be integrated into these two modules. These were designed for this purpose:

- Advisory mode: to give async, hands-on control over trading.
- Ghost mode: to operate fully silently in the background.

These two modes need to be upgraded into what they were intended to be:

Advisory Mode:
- Should provide trading insights and suggestions based on LLM analysis of market data and trading history.
- Should offer real-time trading suggestions.
- Should provide configuration options to customize behavior and trading strategies.
- Should include logging and reporting features to track performance and trading decisions.

Ghost Mode:
- Should trade silently in the background using LLM analysis and vector DB to make trading decisions without user intervention.
- Should provide configuration options to customize behavior and trading strategies.
- Should include logging and reporting features to track performance and trading decisions.

Integration:
- Both modules need to be integrated with the core/llm and core/vector_db modules to leverage their capabilities.
- This will require significant development effort to implement LLM analysis and vector DB integration.

Benefits:
- Once implemented, these modules will provide powerful tools for traders to leverage LLM and vector DB technology for improved trading performance.
- They will serve as examples of how to integrate LLM and vector DB technology into trading applications.

Testing & Documentation:
- Both modules need to be tested thoroughly to ensure they function as intended and provide accurate trading insights and decisions.
- They should be documented thoroughly to provide guidance on their usage and configuration.